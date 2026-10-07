"""Loopback-only stdlib web app. No external services, telemetry, or API key."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs
import uuid
from . import __version__
from .analysis import analyze
from .coach_analysis import adapt_practice_analysis
from .contracts import CoachAnalysisError, CoachDecisionAnalysis, CoachDecisionRef
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


def make_server(port=8765, database="data/pokerlab.sqlite3"):
    store = Store(database)
    games = {}
    hand_revisions = {}
    accepted_actions = {}
    game_lock = threading.Lock()
    work_lock = threading.BoundedSemaphore(2)

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
                return self.respond({"ok": True, "version": __version__})
            prefix, suffix = "/api/v1/decisions/", "/analysis"
            if url.path.startswith(prefix) and url.path.endswith(suffix):
                decision_id = url.path[len(prefix):-len(suffix)]
                if not decision_id or "/" in decision_id:
                    return self.respond({"error": "Not found."}, 404)
                record = store.decision_record(decision_id)
                if record is None:
                    return self.respond({"error": "Not found."}, 404)
                if record["envelope"] is None:
                    return self.respond({
                        "status": "unavailable",
                        "reason": "Versioned coach evidence was not captured for this decision.",
                    })
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
                    expected_modeled_id = ("raise:min" if action_name == "raise" else action_name)
                    legal_action = next((item for item in analysis.legal_actions
                                         if item.name == action_name), None)
                    if legal_action is None:
                        raise ValueError("Stored choice is malformed.")
                    if detail["amount_semantics"] != expected_semantics:
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
                        action_values = {item.action_id: item.value
                                         for item in analysis.action_evs}
                        recommended_id = analysis.recommended_action_id
                        if (recommended_id is None or modeled_id not in action_values
                                or recommended_id not in action_values):
                            raise ValueError("Stored choice is malformed.")
                        expected_loss = max(0.0, action_values[recommended_id]
                                            - action_values[modeled_id])
                        if ev_loss != expected_loss:
                            raise ValueError("Stored choice is malformed.")
                    choice = {
                        "name": detail["name"], "amount": amount,
                        "amount_semantics": detail["amount_semantics"],
                        "assessed_modeled_action_id": modeled_id,
                        "assessment_status": status, "ev_loss": ev_loss,
                    }
                    return self.respond({"status": "ready", "analysis": analysis.to_dict(),
                                         "choice": choice})
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
