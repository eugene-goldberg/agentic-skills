"""FastAPI entrypoint."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _autoload_env() -> str | None:
    """Best-effort load of retrieval env vars from common .env locations.

    Checks (in order):
      1. WEBAPP_ENV_FILE if set
      2. webapp/.env
      3. agentic-skills/.env.kimi  (chat=kimi, embeddings=Azure)
      4. agentic-skills/.env.gpt54 (chat=Azure gpt-5.4, embeddings=Azure)
    First file found wins. Existing env vars are NOT overwritten.
    """
    explicit = os.environ.get("WEBAPP_ENV_FILE")
    here = Path(__file__).resolve().parents[2]  # webapp/
    candidates = [
        Path(explicit) if explicit else None,
        here / ".env",
        here.parent / ".env.kimi",
        here.parent / ".env.gpt54",
    ]
    for p in candidates:
        if p and p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                os.environ.setdefault(k, v)
            return str(p)
    return None


_LOADED_ENV = _autoload_env()

from app.routers import projects, tasks  # noqa: E402  (after env load)

app = FastAPI(title="Claude Code Agent Runner", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(projects.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "env_file": _LOADED_ENV,
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER"),
        "milvus": os.environ.get("MILVUS_ADDRESS"),
    }


# Serve the built React bundle at the FastAPI root so the UI is reachable
# at http://127.0.0.1:8000/ without a second process. Falls back gracefully
# when the dist/ has not been built yet — devs running `npm run dev` on
# :5173 continue to work via the CORS middleware above.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    @app.get("/{path:path}")
    def _serve_spa(path: str = "") -> FileResponse:
        # SPA fallback: any non-/api/* path returns index.html so the
        # client-side router (TanStack / hash params) takes over.
        if path.startswith("api/") or path.startswith("assets/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
