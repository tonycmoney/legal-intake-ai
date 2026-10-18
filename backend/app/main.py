"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.routers import public, staff
from app.security import get_or_create_secret
from app.services import purge_declined, seed_conflicts

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        get_or_create_secret(db, "session_key")
        if settings.seed_conflicts:
            seed_conflicts(db)
        purge_declined(db, settings.declined_retention_days)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Legal Intake AI",
        version="1.0.0",
        description="AI assisted client intake with conflict checks and staff triage.",
        lifespan=lifespan,
    )
    app.include_router(public.router)
    app.include_router(staff.router)

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            candidate = (STATIC_DIR / full_path).resolve()
            if full_path and candidate.is_file() and STATIC_DIR in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
