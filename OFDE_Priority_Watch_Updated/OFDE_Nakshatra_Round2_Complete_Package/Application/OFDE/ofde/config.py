"""Minimal configuration: reads an optional .env file (KEY=VALUE lines) from the project root into os.environ.
Real environment variables always win. Supported keys: OFDE_DB_PATH, OFDE_HOST, OFDE_PORT."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_dotenv(path=None) -> dict:
    path = path or os.path.join(ROOT, ".env")
    loaded = {}
    if not os.path.isfile(path):
        return loaded
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
                loaded[k] = v
    return loaded


def resolve_path(p: str) -> str:
    """Relative paths are resolved against the project root (never a machine-specific absolute path)."""
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


load_dotenv()
