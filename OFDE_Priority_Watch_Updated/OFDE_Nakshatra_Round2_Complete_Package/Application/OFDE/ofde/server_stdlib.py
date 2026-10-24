"""Dependency-free HTTP server over the shared route table (fallback if FastAPI cannot be installed).
Run: python -m ofde.server_stdlib [--port 8000]
"""
from __future__ import annotations

import argparse
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qsl

from .service import ROUTES, OfdeService

_COMPILED = [(r, re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", r.path) + "$")) for r in ROUTES]
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}


def make_handler(service: OfdeService):
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status, ctype, data, headers):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in {**CORS, **headers}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, method):
            url = urlparse(self.path)
            query = dict(parse_qsl(url.query))
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            path_found = False
            for route, rx in _COMPILED:
                m = rx.match(url.path)
                if m:
                    path_found = True
                    if route.method == method:
                        return self._respond(*service.handle(route, m.groupdict(), query, raw))
            msg = b'{"error":{"code":"METHOD_NOT_ALLOWED","message":"Method not allowed"}}' if path_found else \
                  b'{"error":{"code":"NOT_FOUND","message":"No such endpoint"}}'
            self._respond(405 if path_found else 404, "application/json", msg, {})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_OPTIONS(self):
            self._respond(204, "text/plain", b"", {})

        def log_message(self, fmt, *args):
            pass

    return Handler


def serve(host="127.0.0.1", port=8000, service: OfdeService | None = None):
    service = service or OfdeService()
    httpd = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"OFDE (stdlib server) listening on http://{host}:{port}  - Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    serve(a.host, a.port)
