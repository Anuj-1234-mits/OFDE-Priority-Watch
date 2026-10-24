"""Single start command:  python -m ofde   (FastAPI + uvicorn if installed, else the stdlib server)."""
import argparse
import os
import sys

from . import config


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m ofde", description="Start the OFDE backend and dashboard")
    ap.add_argument("--host", default=os.environ.get("OFDE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("OFDE_PORT", "8000")))
    ap.add_argument("--stdlib", action="store_true", help="force the dependency-free server")
    a = ap.parse_args()
    url = f"http://{a.host}:{a.port}"
    if not a.stdlib:
        try:
            import fastapi  # noqa: F401
            import uvicorn
        except ImportError as exc:
            print(f"[ofde] FastAPI/uvicorn not available ({exc}); falling back to the stdlib server.")
        else:
            print(f"[ofde] FastAPI server: open {url}  (Ctrl+C to stop)")
            uvicorn.run("ofde.server_fastapi:app", host=a.host, port=a.port, log_level="info")
            return 0
    from .server_stdlib import serve
    print(f"[ofde] stdlib server: open {url}")
    serve(a.host, a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
