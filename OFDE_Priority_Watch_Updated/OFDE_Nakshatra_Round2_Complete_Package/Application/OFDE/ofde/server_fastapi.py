"""FastAPI transport over the shared route table. Run from the project root:
    uvicorn ofde.server_fastapi:app --host 127.0.0.1 --port 8000
Interactive endpoint list: http://127.0.0.1:8000/docs
NOTE: this module could not be executed in the build sandbox (FastAPI not installable there).
Its behaviour is a thin wrapper over OfdeService.handle(), which IS tested via the stdlib server.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import __version__
from .service import ROUTES, OfdeService

app = FastAPI(title="Orbital Future Decision Engine (OFDE)", version=__version__,
              description="Research/educational prototype. Not a certified collision-avoidance system.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])
service = OfdeService()


def _make_endpoint(route):
    async def endpoint(request: Request):
        raw = await request.body() if route.method == "POST" else None
        status, ctype, data, headers = service.handle(route, dict(request.path_params), dict(request.query_params), raw)
        return Response(content=data, status_code=status, media_type=ctype.split(";")[0],
                        headers={**headers, "Content-Type": ctype})
    endpoint.__name__ = route.name
    return endpoint


for _r in ROUTES:
    app.add_api_route(_r.path, _make_endpoint(_r), methods=[_r.method], name=_r.name, include_in_schema=_r.path != "/")
