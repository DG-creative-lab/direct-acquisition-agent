"""Loopback-only, same-origin transport for the trusted local workspace."""

import argparse
import fcntl
import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from acquisition.contracts import Conflict, NotFound
from acquisition.reasoning import ModelError
from acquisition.workspace import Workspace


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, workspace, assets):
        self.workspace, self.assets = workspace, Path(assets).resolve()
        self.token = secrets.token_urlsafe(32)
        self.root_lock = (workspace.root / "server.lock").open("a+")
        try:
            fcntl.flock(self.root_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            super().__init__(("127.0.0.1", port), Handler)
        except BaseException:
            self.root_lock.close()
            raise

    def server_close(self):
        super().server_close()
        self.root_lock.close()


class Handler(BaseHTTPRequestHandler):
    server: WorkspaceServer

    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json", filename=None):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, mutation=False):
        try:
            self.parsed_target = urlsplit(self.path)
        except ValueError:
            self._send(400, {"error": "Use an origin-form workspace request target"})
            return False
        if (self.parsed_target.scheme or self.parsed_target.netloc or self.parsed_target.fragment
                or not self.path.startswith("/")):
            self._send(400, {"error": "Use an origin-form workspace request target"})
            return False
        host = self.headers.get("Host", "")
        hosts = {"127.0.0.1:" + str(self.server.server_port), "localhost:" + str(self.server.server_port)}
        if host not in hosts:
            self._send(403, {"error": "Use the local workspace origin"})
            return False
        if self.parsed_target.path.startswith("/api/"):
            token = self.headers.get("X-Workspace-Token", "")
            if not secrets.compare_digest(token, self.server.token):
                self._send(403, {"error": "Reload the workspace to establish a local session"})
                return False
            if mutation and self.headers.get("Origin") != "http://" + host:
                self._send(403, {"error": "Workspace actions require the same local origin"})
                return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        try:
            path = self.parsed_target.path
            if path == "/api/sessions":
                return self._send(200, self.server.workspace.listing())
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
                return self._send(200, self.server.workspace.view(parts[2]))
            if len(parts) == 5 and parts[:2] == ["api", "sessions"] and parts[3] == "artifacts":
                query = parse_qs(self.parsed_target.query)
                if set(query) != {"subject_id"} or len(query["subject_id"]) != 1:
                    raise ValueError("Download requires the exact displayed subject")
                body, content_type, filename = self.server.workspace.artifact(parts[2], parts[4], query["subject_id"][0])
                return self._send(200, body, content_type, filename)
            if path.startswith("/api/"):
                raise NotFound("Unknown workspace route")
            target = self.server.assets / ("index.html" if path == "/" else path.lstrip("/"))
            target = target.resolve()
            if not target.is_relative_to(self.server.assets) or not target.is_file():
                raise NotFound("Workspace asset not found")
            body = target.read_bytes()
            if target.name == "index.html":
                body = body.replace(b"__WORKSPACE_TOKEN__", self.server.token.encode())
            self._send(200, body, mimetypes.guess_type(target)[0] or "application/octet-stream")
        except (NotFound, ValueError, Conflict, ModelError) as error:
            self._send(404 if isinstance(error, NotFound) else 409, {"error": str(error)})
        except Exception:
            self._send(500, {"error": "The workspace could not load this state. Retry or inspect the local database."})

    def do_POST(self):
        if not self._guard(mutation=True):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._send(400, {"error": "Use a bounded JSON request"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Use a JSON object")
            path = self.parsed_target.path
            if path == "/api/sessions":
                if set(data) - {"request_id", "mode", "parent_id"}:
                    raise ValueError("Unknown campaign creation fields")
                return self._send(200, self.server.workspace.create(data["request_id"], data["mode"], data.get("parent_id")))
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "sessions"]:
                if parts[3] == "prepare":
                    return self._send(200, self.server.workspace.prepare(parts[2]))
                return self._send(200, self.server.workspace.action(parts[2], parts[3], data))
            raise NotFound("Unknown workspace route")
        except (NotFound, ValueError, Conflict, ModelError, KeyError) as error:
            self._send(404 if isinstance(error, NotFound) else 409 if isinstance(error, Conflict) else 400,
                {"error": str(error) if not isinstance(error, KeyError) else "Missing required workspace field"})
        except Exception:
            self._send(500, {"error": "The action did not return a confirmed result. Refresh before retrying; existing domain receipts prevent duplicate effects."})


def main():
    parser = argparse.ArgumentParser(description="Local synthetic React workspace. No hosted authentication or delivery.")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--root", type=Path, default=Path(".local/workspace"))
    args = parser.parse_args()
    assets = Path(__file__).resolve().parents[2] / "frontend/dist"
    if not (assets / "index.html").exists():
        parser.error(
            "Build the interface first: pnpm --dir frontend install --frozen-lockfile "
            "&& pnpm --dir frontend run build"
        )
    server = WorkspaceServer(args.port, Workspace(args.root), assets)
    print(f"Synthetic workspace: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
