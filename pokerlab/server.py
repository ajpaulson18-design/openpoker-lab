"""Loopback-only stdlib web app. No external services, telemetry, or API key."""
import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlparse, parse_qs, unquote
import uuid
from . import __version__
from .analysis import analyze
from .coach_analysis import adapt_practice_analysis
from .coach_grounding import (CoachGroundingError, CoachReplyPlan,
                              build_grounding_bundle, render_coach_reply,
                              validate_coach_reply_plan)
from .coach_conversation import ConversationError, ConversationLedger
from .current_study import CurrentStudyPreviewCache, build_current_study_view
from .coach_provider import CoachProviderError, OpenAIPlanSelector
from .coach_teaching import build_teaching_note
from .contracts import CoachAnalysisError, CoachDecisionAnalysis, CoachDecisionRef
from .decision_study import build_decision_study
from .equity import simulate
from .explanations import analysis_from_dict, explain
from .exploit import solve_exploitative_river
from .game import Game
from .models import OPPONENT_MODEL_VERSION, Store, PROFILES
from .practice import (advance_to_hero, analyze_decision, build_coach_explanation,
                       decision_event, render_coach_personality, visible_state)
from .personalities import CoachPersonality
from .solver import solve

WEB = Path(__file__).parent / "web"


class ActionConflict(ValueError):
    """A stale hand revision or reused client action ID conflicts with state."""


def _validated_decision(store, decision_id):
    """Load and validate a saved decision once for every read projection."""
    record = store.decision_record(decision_id)
    if record is None:
        return {"status": "missing"}
    if record["envelope"] is None:
        return {
            "status": "unavailable",
            "reason": "Versioned coach evidence was not captured for this decision.",
        }
    try:
        analysis = CoachDecisionAnalysis.from_json(record["envelope"])
        event = json.loads(record["event"])
        if (analysis.ref.hand_id != record["session_id"]
                or analysis.ref.decision_id != record["id"]):
            raise CoachAnalysisError("invalid_contract", "Stored evidence reference is invalid.")
        detail = event.get("chosen_action_detail")
        status = event.get("assessment_status")
        if (not isinstance(detail, dict)
                or set(detail) != {"name", "amount", "amount_semantics"}
                or detail.get("name") not in ("fold", "check", "call", "raise")
                or event.get("chosen_action") != detail.get("name")
                or detail.get("amount_semantics") not in ("chips_added", "street_total")
                or status not in ("assessed", "unassessed_size")):
            raise ValueError("Stored choice is malformed.")
        amount = detail["amount"]
        if type(amount) is not int or amount < 0:
            raise ValueError("Stored choice is malformed.")
        action_name = detail["name"]
        expected_semantics = "street_total" if action_name == "raise" else "chips_added"
        modeled_id = event.get("assessed_modeled_action_id")
        expected_modeled_id = "raise:min" if action_name == "raise" else action_name
        legal_action = next((item for item in analysis.legal_actions
                             if item.name == action_name), None)
        if legal_action is None or detail["amount_semantics"] != expected_semantics:
            raise ValueError("Stored choice is malformed.")
        if action_name == "raise":
            if not legal_action.minimum_total <= amount <= legal_action.maximum_total:
                raise ValueError("Stored choice is malformed.")
            should_be_assessed = amount == legal_action.minimum_total
        else:
            if amount != legal_action.amount:
                raise ValueError("Stored choice is malformed.")
            should_be_assessed = True
        if (status == "assessed") != should_be_assessed:
            raise ValueError("Stored choice is malformed.")
        if status == "assessed" and modeled_id != expected_modeled_id:
            raise ValueError("Stored choice is malformed.")
        if status == "unassessed_size" and (action_name != "raise" or modeled_id is not None):
            raise ValueError("Stored choice is malformed.")
        ev_loss = event.get("ev_loss")
        if ev_loss is not None and (type(ev_loss) not in (int, float)
                                    or not math.isfinite(ev_loss) or ev_loss < 0):
            raise ValueError("Stored choice is malformed.")
        if ((status == "unassessed_size" and ev_loss is not None)
                or (status == "assessed" and ev_loss is None)):
            raise ValueError("Stored choice is malformed.")
        if status == "assessed":
            action_values = {item.action_id: item.value for item in analysis.action_evs}
            recommended_id = analysis.recommended_action_id
            if (recommended_id is None or modeled_id not in action_values
                    or recommended_id not in action_values
                    or action_values[modeled_id] is None
                    or action_values[recommended_id] is None):
                raise ValueError("Stored choice is malformed.")
            expected_loss = max(0.0, action_values[recommended_id] - action_values[modeled_id])
            if ev_loss != expected_loss:
                raise ValueError("Stored choice is malformed.")
        choice = {
            "name": detail["name"], "amount": amount,
            "amount_semantics": detail["amount_semantics"],
            "assessed_modeled_action_id": modeled_id,
            "assessment_status": status, "ev_loss": ev_loss,
        }
        return {"status": "ready", "analysis": analysis, "choice": choice}
    except Exception:
        return {"status": "failed", "error": "Stored decision evidence is invalid."}


def make_server(port=8765, database="data/pokerlab.sqlite3", *,
                coach_selector=None, coach_enabled=None, coach_timeout=12.0,
                coach_clock=None):
    store = Store(database)
    explicitly_enabled = (os.environ.get("OPENPOKER_AI_COACH_ENABLED") == "1"
                          if coach_enabled is None else coach_enabled is True)
    if coach_selector is None and explicitly_enabled:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        model = os.environ.get("OPENAI_MODEL", "")
        if api_key.strip() and model.strip():
            try:
                coach_selector = OpenAIPlanSelector(api_key, model, coach_timeout)
            except ValueError:
                coach_selector = None
    coach_external_available = explicitly_enabled and coach_selector is not None
    games = {}
    hand_revisions = {}
    accepted_actions = {}
    game_lock = threading.Lock()
    work_lock = threading.BoundedSemaphore(2)
    coach_lock = threading.BoundedSemaphore(1)
    preview_lock = threading.BoundedSemaphore(1)
    preview_cache = CurrentStudyPreviewCache()
    conversation_ledger = (ConversationLedger(clock=coach_clock)
                           if coach_clock is not None else ConversationLedger())

    def coach_fallback(bundle, detail, audience, reason):
        recommendation = next((fact for fact in bundle.facts
                               if fact.kind == "recommendation"), None)
        intent = "recommendation" if recommendation and recommendation.value is not None else "unavailable"
        plan = CoachReplyPlan(bundle.binding, intent, (), None, detail, audience)
        reply = render_coach_reply(bundle, plan)
        teaching_note = build_teaching_note(bundle, reply)
        return {
            "status": "fallback", "source": "local_fallback", "retryable": True,
            "fallback_reason": reason, "binding": bundle.binding.to_dict(),
            "source_label": reply.source_label, "reply": reply.to_dict(),
            "teaching_note": teaching_note.to_dict() if teaching_note else None,
        }

    def resolve_current_study_evidence(binding):
        """Resolve a live-question binding to its retained, immutable preview."""
        if (not isinstance(binding, dict)
                or set(binding) != {"hand_id", "decision_id", "evidence_id", "state_revision"}):
            return None
        if (any(not isinstance(binding.get(name), str) or not binding[name].strip()
                for name in ("hand_id", "decision_id", "evidence_id"))
                or type(binding.get("state_revision")) is not int
                or binding["state_revision"] < 0):
            return None
        return preview_cache.resolve(
            hand_id=binding["hand_id"], decision_id=binding["decision_id"],
            evidence_id=binding["evidence_id"], state_revision=binding["state_revision"])

    def current_study(path, data):
        match = re.fullmatch(r"/api/v1/hands/([^/]+)/current-study", path)
        if not match:
            return {"error": "Not found."}, 404
        hand_id = unquote(match.group(1))
        if not hand_id or len(hand_id) > 128:
            return {"error": "Hand was not found."}, 404
        if set(data) != {"expected_revision", "opponent_id"}:
            return {"error": "Study request must include expected_revision and opponent_id."}, 400
        revision = data["expected_revision"]
        opponent_id = data["opponent_id"]
        if type(revision) is not int or revision < 0:
            return {"error": "Expected revision must be a non-negative integer."}, 400
        if opponent_id is not None and (not isinstance(opponent_id, str)
                                        or not opponent_id or len(opponent_id) > 128):
            return {"error": "Opponent ID must be a non-empty string or null."}, 400

        with game_lock:
            game = games.get(hand_id)
            if game is None:
                return {"error": "Hand was not found or has expired."}, 404
            if (hand_revisions.get(hand_id) != revision or game.done or game.actor != 0):
                return {"error": "Hand changed before the study preview. Refresh and try again."}, 409
            snapshot = copy.deepcopy(game)

        opponent = None
        if opponent_id is not None:
            try:
                opponent = store.get_opponent(opponent_id, snapshot.street)
                opponent["model_version"] = OPPONENT_MODEL_VERSION
            except (ValueError, KeyError):
                return {"error": "Selected opponent model is unavailable."}, 400

        if opponent is None:
            model_identity = "illustrative-default"
        else:
            identity_facts = {key: opponent[key] for key in
                              ("id", "profile", "street", "metrics", "model_version")}
            encoded = json.dumps(identity_facts, sort_keys=True, separators=(",", ":"))
            model_identity = hashlib.sha256(encoded.encode()).hexdigest()
        cache_key = (hand_id, revision, model_identity)
        cached = preview_cache.get(cache_key)

        if cached is None:
            try:
                raw = analyze_decision(snapshot, opponent)
                evidence = adapt_practice_analysis(
                    raw, ref=CoachDecisionRef(hand_id, uuid.uuid4().hex, revision))
                view = build_current_study_view(evidence)
            except Exception:
                return {"error": "Study preview failed safely."}, 500
        else:
            evidence, view = cached

        with game_lock:
            current = games.get(hand_id)
            if (current is None or hand_revisions.get(hand_id) != revision
                    or current.done or current.actor != 0):
                return {"error": "Hand changed while the study preview was calculating."}, 409

        if cached is None:
            preview_cache.put(cache_key, evidence, view)
        return view, 200

    def dispatch_coach(path, data, external_requested):
        prefix = "/api/v1/decisions/"
        parts = path[len(prefix):].split("/") if path.startswith(prefix) else []
        if len(parts) != 2 or parts[1] != "coach" or not parts[0]:
            return {"error": "Not found."}, 404
        decision_id = unquote(parts[0])
        if not decision_id or len(decision_id) > 256 or "/" in decision_id:
            return {"error": "Not found."}, 404
        if not isinstance(data, dict) or set(data) != {"evidence_id", "question", "detail", "audience"}:
            return {"error": "Coach request fields are invalid."}, 400
        evidence_id = data["evidence_id"]
        question = data["question"]
        detail = data["detail"]
        audience = data["audience"]
        if not isinstance(evidence_id, str) or not evidence_id.strip() or len(evidence_id) > 256:
            return {"error": "Evidence ID is invalid."}, 400
        if not isinstance(question, str) or not question.strip() or len(question) > 500:
            return {"error": "Question must contain 1–500 characters."}, 400
        question = question.strip()
        if detail not in ("short", "normal", "technical"):
            return {"error": "Detail setting is invalid."}, 400
        if audience not in ("beginner", "standard"):
            return {"error": "Audience setting is invalid."}, 400

        saved = _validated_decision(store, decision_id)
        if saved["status"] == "missing":
            return {"error": "Not found."}, 404
        if saved["status"] == "unavailable":
            return {"status": "unavailable", "source": "local_fallback",
                    "reason": saved["reason"], "retryable": False}, 200
        if saved["status"] != "ready":
            return {"status": "failed", "error": "Stored decision evidence is invalid."}, 500
        analysis, choice = saved["analysis"], saved["choice"]
        if evidence_id != analysis.evidence_id:
            return {"error": "Selected decision evidence changed; reload the study and retry."}, 409
        try:
            bundle = build_grounding_bundle(analysis, choice)
        except (CoachGroundingError, ValueError, TypeError):
            return {"status": "failed", "error": "Stored decision evidence is invalid."}, 500

        if not external_requested:
            return coach_fallback(bundle, detail, audience, "external_ai_not_selected"), 200
        if not coach_external_available:
            return coach_fallback(bundle, detail, audience, "external_ai_not_configured"), 200

        try:
            candidate = coach_selector.select_plan(bundle, question, detail, audience)
            plan = validate_coach_reply_plan(candidate, bundle)
            if plan.detail != detail or plan.audience != audience:
                raise CoachGroundingError("invalid_reply_plan", "Presentation settings changed.")
            reply = render_coach_reply(bundle, plan)
            teaching_note = build_teaching_note(bundle, reply)
        except CoachProviderError as error:
            return coach_fallback(bundle, detail, audience, error.code), 200
        except (CoachGroundingError, ValueError, TypeError):
            return coach_fallback(bundle, detail, audience, "invalid_plan"), 200
        except Exception:
            # Provider exceptions are intentionally sanitized; never log prompts or response bodies.
            return coach_fallback(bundle, detail, audience, "provider_error"), 200
        return {
            "status": "ready", "source": "openai", "retryable": False,
            "binding": bundle.binding.to_dict(), "source_label": reply.source_label,
            "reply": reply.to_dict(),
            "teaching_note": teaching_note.to_dict() if teaching_note else None,
        }, 200

    def dispatch_coach_turn(data, external_requested):
        required = {"client_turn_id", "target", "question", "detail", "audience"}
        allowed = required | {"conversation_id"}
        if not isinstance(data, dict) or not required <= set(data) or set(data) - allowed:
            return {"error": "Coach turn request fields are invalid.", "code": "invalid_request"}, 400
        client_turn_id = data["client_turn_id"]
        conversation_id = data.get("conversation_id")
        target = data["target"]
        question = data["question"]
        detail = data["detail"]
        audience = data["audience"]
        if (not isinstance(client_turn_id, str) or not client_turn_id.strip()
                or len(client_turn_id) > 128):
            return {"error": "Client turn ID is invalid.", "code": "invalid_request"}, 400
        client_turn_id = client_turn_id.strip()
        if (conversation_id is not None
                and (not isinstance(conversation_id, str) or not conversation_id.strip()
                     or len(conversation_id) > 128)):
            return {"error": "Conversation ID is invalid.", "code": "invalid_request"}, 400
        if (not isinstance(target, dict)
                or set(target) != {"hand_id", "decision_id", "evidence_id", "state_revision"}):
            return {"error": "Decision target is invalid.", "code": "invalid_target"}, 400
        if any(not isinstance(target.get(key), str) or not target[key].strip()
               or len(target[key]) > 256 for key in ("hand_id", "decision_id", "evidence_id")):
            return {"error": "Decision target is invalid.", "code": "invalid_target"}, 400
        revision = target["state_revision"]
        if revision is not None and (type(revision) is not int or revision < 0):
            return {"error": "Decision target is invalid.", "code": "invalid_target"}, 400
        if not isinstance(question, str) or not question.strip() or len(question) > 500:
            return {"error": "Question must contain 1–500 characters.", "code": "invalid_request"}, 400
        question = question.strip()
        if detail not in ("short", "normal", "technical"):
            return {"error": "Detail setting is invalid.", "code": "invalid_request"}, 400
        if audience not in ("beginner", "standard"):
            return {"error": "Audience setting is invalid.", "code": "invalid_request"}, 400

        decision_id = target["decision_id"]
        saved = _validated_decision(store, decision_id)
        if saved["status"] == "missing":
            return {"error": "Not found.", "code": "not_found"}, 404
        if saved["status"] == "unavailable":
            return {"status": "unavailable", "source": "local_fallback",
                    "reason": saved["reason"], "retryable": False}, 200
        if saved["status"] != "ready":
            return {"status": "failed", "error": "Stored decision evidence is invalid."}, 500
        analysis, choice = saved["analysis"], saved["choice"]
        bundle_binding = {
            **analysis.ref.to_dict(), "evidence_id": analysis.evidence_id,
        }
        if target != bundle_binding:
            return {"error": "Selected decision binding changed; reload the study and retry.",
                    "code": "binding_mismatch"}, 409
        try:
            bundle = build_grounding_bundle(analysis, choice)
        except (CoachGroundingError, ValueError, TypeError):
            return {"status": "failed", "error": "Stored decision evidence is invalid."}, 500

        payload = {"question": question, "detail": detail, "audience": audience,
                   "external_ai": external_requested}
        try:
            reservation = conversation_ledger.reserve(
                conversation_id, client_turn_id, bundle.binding.to_dict(), payload)
        except ConversationError as error:
            return {"error": str(error), "code": error.code}, error.status

        conversation_id = reservation["conversation_id"]
        if reservation["cached_result"] is not None:
            return reservation["cached_result"], 200
        if not coach_lock.acquire(blocking=False):
            conversation_ledger.abort(conversation_id, client_turn_id)
            return {"error": "A coach request is already running. Try again shortly.",
                    "code": "coach_busy"}, 429

        plan_metadata = None
        try:
            prior_turns = conversation_ledger.prior_context(conversation_id, client_turn_id)
            if not external_requested:
                result = coach_fallback(bundle, detail, audience, "external_ai_not_selected")
                plan_metadata = {"intent": result["reply"]["intent"],
                                 "target_action_id": result["reply"].get("target_action_id"),
                                 "detail": detail, "audience": audience}
            elif not coach_external_available:
                result = coach_fallback(bundle, detail, audience, "external_ai_not_configured")
                plan_metadata = {"intent": result["reply"]["intent"],
                                 "target_action_id": result["reply"].get("target_action_id"),
                                 "detail": detail, "audience": audience}
            else:
                try:
                    candidate = coach_selector.select_plan(
                        bundle, question, detail, audience, prior_turns=prior_turns)
                    plan = validate_coach_reply_plan(candidate, bundle)
                    if plan.detail != detail or plan.audience != audience:
                        raise CoachGroundingError("invalid_reply_plan", "Presentation settings changed.")
                    reply = render_coach_reply(bundle, plan)
                    teaching_note = build_teaching_note(bundle, reply)
                    result = {
                        "status": "ready", "source": "openai", "retryable": False,
                        "binding": bundle.binding.to_dict(), "source_label": reply.source_label,
                        "reply": reply.to_dict(),
                        "teaching_note": teaching_note.to_dict() if teaching_note else None,
                    }
                    plan_metadata = {"intent": plan.intent,
                                     "target_action_id": plan.target_action_id,
                                     "detail": plan.detail, "audience": plan.audience}
                except CoachProviderError as error:
                    result = coach_fallback(bundle, detail, audience, error.code)
                except (CoachGroundingError, ValueError, TypeError):
                    result = coach_fallback(bundle, detail, audience, "invalid_plan")
                except Exception:
                    result = coach_fallback(bundle, detail, audience, "provider_error")
                if plan_metadata is None:
                    plan_metadata = {"intent": result["reply"]["intent"],
                                     "target_action_id": result["reply"].get("target_action_id"),
                                     "detail": detail, "audience": audience}
            result.update({"conversation_id": conversation_id,
                           "client_turn_id": client_turn_id})
            conversation_ledger.complete(conversation_id, client_turn_id,
                                         plan_metadata, result)
            return result, 200
        except Exception:
            conversation_ledger.abort(conversation_id, client_turn_id)
            return {"error": "Coach turn failed safely.", "code": "coach_failed"}, 500
        finally:
            coach_lock.release()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, status=200, content_type="application/json"):
            raw = json.dumps(value, allow_nan=False).encode() if content_type == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", content_type+"; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            host = self.headers.get("Host", "")
            allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            return host in allowed_hosts and (not origin or origin in {"http://"+h for h in allowed_hosts})

        def do_GET(self):
            if not self.allowed():
                return self.respond({"error": "Local access only."}, 403)
            url = urlparse(self.path)
            if url.path == "/api/opponents":
                return self.respond({"opponents": store.opponents(), "profiles": list(PROFILES)})
            if url.path == "/api/export":
                return self.respond(store.export())
            if url.path == "/api/health":
                return self.respond({"ok": True, "version": __version__,
                                     "external_ai_coach_available": coach_external_available})
            decision_prefix = "/api/v1/decisions/"
            if url.path.startswith(decision_prefix):
                parts = url.path[len(decision_prefix):].split("/")
                if len(parts) != 2 or not parts[0] or parts[1] not in ("analysis", "study"):
                    return self.respond({"error": "Not found."}, 404)
                decision_id, projection = parts
                result = _validated_decision(store, decision_id)
                if result["status"] == "missing":
                    return self.respond({"error": "Not found."}, 404)
                if result["status"] != "ready":
                    return self.respond(result, 500 if result["status"] == "failed" else 200)
                if projection == "analysis":
                    return self.respond({"status": "ready",
                                         "analysis": result["analysis"].to_dict(),
                                         "choice": result["choice"]})
                try:
                    return self.respond(build_decision_study(
                        result["analysis"], result["choice"]))
                except Exception:
                    return self.respond({"status": "failed",
                                         "error": "Stored decision evidence is invalid."}, 500)
            if url.path.startswith("/api/session/"):
                try:
                    return self.respond(store.session(url.path.rsplit("/", 1)[-1], require_complete=True))
                except ValueError as error:
                    return self.respond({"error": str(error)}, 400)
            filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                        "/names.css": "names.css", "/coach.css": "coach.css"}.get(url.path)
            if filename:
                mime = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[filename.split(".")[-1]]
                return self.respond((WEB/filename).read_bytes(), content_type=mime)
            return self.respond({"error": "Not found."}, 404)

        def do_POST(self):
            if not self.allowed():
                return self.respond({"error": "Local access only."}, 403)
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 1_000_000:
                    raise ValueError("Request must contain 1–1,000,000 bytes.")
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Send application/json.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object.")
                request_path = urlparse(self.path).path
                if request_path.startswith("/api/v1/hands/"):
                    if not preview_lock.acquire(blocking=False):
                        return self.respond({"error": "A study preview is already running. Try again shortly."}, 429)
                    try:
                        result, status_code = current_study(request_path, data)
                        return self.respond(result, status_code)
                    finally:
                        preview_lock.release()
                if request_path == "/api/v1/coach/turns":
                    result, status_code = dispatch_coach_turn(
                        data, self.headers.get("X-OpenPoker-External-AI") == "1")
                    return self.respond(result, status_code)
                if request_path.startswith("/api/v1/decisions/") and request_path.endswith("/coach"):
                    if not coach_lock.acquire(blocking=False):
                        return self.respond({"error": "A coach request is already running. Try again shortly."}, 429)
                    try:
                        try:
                            result, status_code = dispatch_coach(
                                request_path, data,
                                self.headers.get("X-OpenPoker-External-AI") == "1")
                        except ActionConflict as error:
                            return self.respond({"error": str(error)}, 409)
                        except (ValueError, TypeError, KeyError, OverflowError):
                            return self.respond({"error": "Coach request is invalid."}, 400)
                        except Exception:
                            return self.respond({"error": "Coach request failed safely."}, 500)
                        return self.respond(result, status_code)
                    finally:
                        coach_lock.release()
                if not work_lock.acquire(blocking=False):
                    return self.respond({"error": "Two calculations are already running. Try again shortly."}, 429)
                try:
                    result = self.dispatch(urlparse(self.path).path, data)
                finally:
                    work_lock.release()
                self.respond(result)
            except ActionConflict as error:
                self.respond({"error": str(error)}, 409)
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                self.respond({"error": str(error)}, 400)
            except Exception:
                self.respond({"error": "Unexpected server error; see the terminal."}, 500)
                import traceback
                traceback.print_exc()

        def dispatch(self, path, data):
            if path == "/api/equity":
                return simulate(**data)
            if path == "/api/analyze":
                opponent = None
                if data.get("opponent_id"):
                    from .cards import cards
                    street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}.get(len(cards(data.get("board", ""))), "all")
                    opponent = store.get_opponent(data["opponent_id"], street)
                result = analyze(data, opponent)
                result["saved_id"] = store.save_analysis(data, result)
                return result
            if path == "/api/solve":
                return solve(**data)
            if path == "/api/exploit":
                inputs = dict(data)
                opponent_id = inputs.pop("opponent_id")
                snapshot = store.opponent_snapshot(opponent_id, "river")
                return solve_exploitative_river(snapshot=snapshot, **inputs).to_dict()
            if path == "/api/explain":
                analysis = analysis_from_dict(data["analysis"])
                return explain(analysis, data["recommended_action"],
                               data.get("level", "normal")).to_dict()
            if path == "/api/opponents":
                return store.add_opponent(**data)
            if path == "/api/observe":
                return store.observe(**data)
            if path == "/api/game":
                with game_lock:
                    identity = uuid.uuid4().hex
                    prepared = Game(**data)
                    advance_to_hero(prepared)
                    store.start_session(identity, complete=prepared.done)
                    if len(games) >= 100:
                        expired = next(iter(games))
                        games.pop(expired)
                        hand_revisions.pop(expired, None)
                        for key in [key for key in accepted_actions if key[0] == expired]:
                            accepted_actions.pop(key, None)
                    games[identity] = prepared
                    hand_revisions[identity] = 0
                    return {"id": identity, **visible_state(prepared), "revision": 0}
            if path == "/api/act":
                with game_lock:
                    identity = data["id"]
                    if identity not in games:
                        raise ValueError("Hand expired; deal a new hand.")
                    game = games[identity]
                    action = data.get("action")
                    if action not in ("fold", "check", "call", "raise"):
                        raise ValueError("That action is not legal here.")
                    amount = data.get("amount") if action == "raise" else None
                    opponent_id = data.get("opponent_id") or None
                    client_action_id = data.get("client_action_id")
                    if client_action_id is not None and (
                            not isinstance(client_action_id, str)
                            or not 1 <= len(client_action_id) <= 128
                            or not client_action_id.strip()):
                        raise ValueError("Client action ID must contain 1–128 characters.")
                    has_expected_revision = "expected_revision" in data
                    expected_revision = data.get("expected_revision")
                    if has_expected_revision and (
                            type(expected_revision) is not int or expected_revision < 0):
                        raise ValueError("Expected revision must be a non-negative integer.")
                    coach_visible = data.get("coach_visible", False)
                    if type(coach_visible) is not bool:
                        raise ValueError("coach_visible must be boolean.")
                    personality = CoachPersonality(data.get("personality", "grinder"))
                    normalized_request = (action, amount, opponent_id,
                                          personality.value, coach_visible)
                    cache_key = (identity, client_action_id) if client_action_id is not None else None
                    if cache_key is not None and cache_key in accepted_actions:
                        cached = accepted_actions[cache_key]
                        if cached["request"] != normalized_request:
                            raise ActionConflict("Client action ID was already used for a different action.")
                        return copy.deepcopy(cached["response"])
                    current_revision = hand_revisions[identity]
                    if has_expected_revision and expected_revision != current_revision:
                        raise ActionConflict("Hand changed before this action. Refresh and try again.")
                    if game.done or game.actor != 0:
                        raise ValueError("The hero is not awaiting a decision.")
                    opponent = None
                    if opponent_id:
                        opponent = store.get_opponent(opponent_id, game.street)
                        opponent["model_version"] = OPPONENT_MODEL_VERSION
                    analysis = analyze_decision(game, opponent)
                    decision_id = uuid.uuid4().hex
                    evidence = adapt_practice_analysis(
                        analysis, ref=CoachDecisionRef(identity, decision_id, current_revision))
                    event = decision_event(game, analysis, action, opponent, amount)
                    event["state_revision"] = current_revision
                    prepared = copy.deepcopy(game)
                    prepared.act(action, amount)
                    advance_to_hero(prepared)
                    coach = None
                    if coach_visible:
                        coach = copy.deepcopy(analysis)
                        coach["explanation_payload"] = build_coach_explanation(coach).to_dict()
                        coach["personality"] = render_coach_personality(coach, personality)
                    post_revision = current_revision + 1
                    response = {"id": identity, **visible_state(prepared),
                                "revision": post_revision,
                                "decision": {
                                    "decision_id": decision_id, "hand_id": identity,
                                    "state_revision": current_revision,
                                    "evidence_id": evidence.evidence_id,
                                    "chosen_action_detail": event["chosen_action_detail"],
                                    "assessed_modeled_action_id": event["assessed_modeled_action_id"],
                                    "assessment_status": event["assessment_status"],
                                    "ev_loss": event["ev_loss"],
                                }}
                    if coach is not None:
                        response["coach"] = coach
                    stored = store.save_decision(
                        identity, event, decision_id=decision_id,
                        coach_analysis=evidence, complete_hand=prepared.done)
                    response["decision_order"] = stored["decision_order"]
                    games[identity] = prepared
                    hand_revisions[identity] = post_revision
                    if cache_key is not None:
                        accepted_actions[cache_key] = {
                            "request": normalized_request,
                            "response": copy.deepcopy(response),
                        }
                    return response
            raise ValueError("Unknown endpoint.")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="OpenPoker Lab — local poker research")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", default="data/pokerlab.sqlite3")
    args = parser.parse_args()
    server = make_server(args.port, args.database)
    print(f"OpenPoker Lab is ready at http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

