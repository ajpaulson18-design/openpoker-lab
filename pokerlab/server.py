"""Loopback-only stdlib web app. No external services, telemetry, or API key."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs
import uuid
from .analysis import analyze
from .equity import simulate
from .game import Game
from .models import Store, PROFILES
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
                return self.respond({"ok": True, "version": "0.1.0"})
            filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(url.path)
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
                    return {"id": identity, **games[identity].state()}
            if path == "/api/act":
                with game_lock:
                    identity = data["id"]
                    if identity not in games:
                        raise ValueError("Hand expired; deal a new hand.")
                    return {"id": identity, **games[identity].act(data["action"], data.get("amount"))}
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
