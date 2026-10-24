"""WIRING test of ofde/server_fastapi.py with a FAKE `fastapi` package. NOT FastAPI verification.
Checks that every route in the shared table is registered with the right method/path, that an endpoint turns a request into
service.handle(...) and a Response with the right status/content-type/headers, and that POST bodies and query params flow through.
Real FastAPI behaviour is covered by tests/test_fastapi_app.py (skipped unless fastapi and httpx are installed)."""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest

from ofde import service as service_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeRequest:
    def __init__(self, method, body=b"", path_params=None, query=None):
        self.method, self._body, self.path_params, self.query_params = method, body, path_params or {}, query or {}

    async def body(self):
        return self._body


class FakeResponse:
    def __init__(self, content=b"", status_code=200, media_type=None, headers=None):
        self.content, self.status_code, self.media_type, self.headers = content, status_code, media_type, headers or {}


class FakeApp:
    def __init__(self, **kw):
        self.kw, self.routes, self.middleware = kw, [], []

    def add_middleware(self, cls, **kw):
        self.middleware.append((cls, kw))

    def add_api_route(self, path, endpoint, methods=None, name=None, include_in_schema=True):
        self.routes.append({"path": path, "endpoint": endpoint, "methods": methods, "name": name, "schema": include_in_schema})


def load_with_fake_fastapi(db):
    saved = {k: sys.modules.get(k) for k in ("fastapi", "fastapi.middleware", "fastapi.middleware.cors", "fastapi.responses")}
    fa = types.ModuleType("fastapi"); fa.FastAPI, fa.Request = FakeApp, FakeRequest
    mw = types.ModuleType("fastapi.middleware"); cors = types.ModuleType("fastapi.middleware.cors"); cors.CORSMiddleware = type("CORS", (), {})
    resp = types.ModuleType("fastapi.responses"); resp.Response = FakeResponse
    sys.modules.update({"fastapi": fa, "fastapi.middleware": mw, "fastapi.middleware.cors": cors, "fastapi.responses": resp})
    old_db = service_mod.DEFAULT_DB
    service_mod.DEFAULT_DB = db
    try:
        spec = importlib.util.spec_from_file_location("ofde.server_fastapi_fake", os.path.join(ROOT, "ofde", "server_fastapi.py"),
                                                      submodule_search_locations=None)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "ofde"
        spec.loader.exec_module(mod)
    finally:
        service_mod.DEFAULT_DB = old_db
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return mod


class TestWrapper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = load_with_fake_fastapi(os.path.join(self.tmp.name, "f.sqlite3"))
        self.by_name = {r["name"]: r for r in self.mod.app.routes}

    def tearDown(self):
        self.mod.service.store.close()
        self.tmp.cleanup()

    def call(self, name, req):
        return asyncio.run(self.by_name[name]["endpoint"](req))

    def test_every_route_registered_once_with_matching_method(self):
        self.assertEqual(len(self.mod.app.routes), len(service_mod.ROUTES))
        for r in service_mod.ROUTES:
            reg = self.by_name[r.name]
            self.assertEqual((reg["path"], reg["methods"]), (r.path, [r.method]))
        self.assertFalse(self.by_name["index"]["schema"])
        self.assertEqual(self.mod.app.middleware[0][1]["allow_origins"], ["*"])

    def test_status_endpoint_returns_json_response(self):
        r = self.call("status", FakeRequest("GET"))
        self.assertEqual((r.status_code, r.media_type), (200, "application/json"))
        self.assertIn("ofde_version", json.loads(r.content))
        self.assertEqual(r.headers["Content-Type"], "application/json")

    def test_post_body_query_and_path_params_flow_through(self):
        r = self.call("validate_tle", FakeRequest("POST", body=b'{"text": ""}'))
        self.assertEqual(r.status_code, 400)                             # empty text rejected by the service
        r = self.call("validate_tle", FakeRequest("POST", body=b"{bad"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("INVALID_JSON", r.content.decode())
        r = self.call("get_analysis", FakeRequest("GET", path_params={"analysis_id": "42"}))
        self.assertEqual(r.status_code, 404)
        r = self.call("dashboard", FakeRequest("GET", query={"dataset_id": "999"}))
        self.assertEqual(r.status_code, 404)

    def test_attachment_headers_and_charset_preserved(self):
        self.call("load_demo", FakeRequest("POST", body=b"{}"))
        r = self.call("index", FakeRequest("GET"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.media_type, "text/html")
        self.assertIn("charset=utf-8", r.headers["Content-Type"])
        self.assertIn(b"Orbital Future Decision Engine", r.content)


if __name__ == "__main__":
    unittest.main()
