"""Loopback-only stdlib web app. No external services, telemetry, or API key."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs
import uuid
from . import __version__
from .analysis import analyze
from .equity import simulate
from .explanations import ExplanationLevel, analysis_from_dict, explain
from .exploit import solve_exploitative_river
from .game import Game
from .models import OPPONENT_MODEL_VERSION, Store, PROFILES
from .practice import (advance_to_hero, analyze_decision, build_coach_explanation,
                       decision_event, render_coach_personality, visible_state)
from .personalities import CoachPersonality
from .solver import solve

WEB = Path(__file__).parent / "web"


def make_server(port=8765, database="data/pokerlab.sqlite3"):
    store = Store(database)
    games = {}
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
                opponent_id = inputs.pop("opponent_id", None)
                if not isinstance(opponent_id, str) or not opponent_id:
                    raise ValueError("Choose an existing opponent profile for river analysis.")
                snapshot = store.opponent_snapshot(opponent_id, "river")
                return solve_exploitative_river(snapshot=snapshot, **inputs).to_dict()
            if path == "/api/explain":
                analysis_data = data.get("analysis")
                if not isinstance(analysis_data, dict):
                    raise ValueError("Provide analysis as a JSON object.")
                recommended_action = data.get("recommended_action")
                if not isinstance(recommended_action, str) or not recommended_action:
                    raise ValueError("Provide a recommended_action.")
                level = data.get("level", ExplanationLevel.NORMAL.value)
                if not isinstance(level, str) or level not in {
                        item.value for item in ExplanationLevel}:
                    raise ValueError("Level must be short, normal, or beginner.")
                try:
                    analysis = analysis_from_dict(analysis_data)
                except (KeyError, TypeError) as error:
                    raise ValueError("Analysis contract is incomplete or malformed.") from error
                return explain(analysis, recommended_action, level).to_dict()
            if path == "/api/opponents":
                return store.add_opponent(**data)
            if path == "/api/observe":
                return store.observe(**data)
            if path == "/api/game":
                with game_lock:
                    if len(games) >= 100:
                        games.pop(next(iter(games)))
                    identity = uuid.uuid4().hex
                    games[identity] = Game(**data)
                    advance_to_hero(games[identity])
                    store.start_session(identity)
                    if games[identity].done:
                        store.complete_session(identity)
                    return {"id": identity, **visible_state(games[identity])}
            if path == "/api/act":
                with game_lock:
                    identity = data["id"]
                    if identity not in games:
                        raise ValueError("Hand expired; deal a new hand.")
                    game = games[identity]
                    if game.done or game.actor != 0:
                        raise ValueError("The hero is not awaiting a decision.")
                    personality = CoachPersonality(data.get("personality", "grinder"))
                    opponent = None
                    if data.get("opponent_id"):
                        opponent = store.get_opponent(data["opponent_id"], game.street)
                        opponent["model_version"] = OPPONENT_MODEL_VERSION
                    analysis = analyze_decision(game, opponent)
                    event = decision_event(game, analysis, data["action"], opponent)
                    game.act(data["action"], data.get("amount"))
                    stored = store.save_decision(identity, event)
                    advance_to_hero(game)
                    if game.done:
                        store.complete_session(identity)
                    response = {"id": identity, **visible_state(game), "decision_order": stored["decision_order"]}
                    if data.get("coach_visible", False):
                        response["coach"] = analysis
                        response["coach"]["explanation_payload"] = build_coach_explanation(
                            analysis).to_dict()
                        response["coach"]["personality"] = render_coach_personality(
                            analysis, personality)
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
