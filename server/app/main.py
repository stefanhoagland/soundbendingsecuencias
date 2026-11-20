from __future__ import annotations

import logging
import secrets
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from . import api, web
from .config import Settings, load_settings
from .db import Base, add_missing_columns, make_engine, make_session_factory
from .deps import LoginRequired
from .guide import WhisperTranscriber
from .models import Song, User
from .previews import PreviewMaker
from .section_jobs import JobRunner
from .services import create_user

log = logging.getLogger("soundbending")
HERE = Path(__file__).parent


def _filesize(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _ensure_admin(settings: Settings, factory) -> None:
    with factory() as db:
        if db.scalar(select(func.count(User.id))):
            return
        password = settings.admin_password
        generated = password is None
        if generated:
            password = secrets.token_urlsafe(12)
        create_user(db, settings.admin_username, password, display_name="Admin", is_admin=True)
        if generated:
            log.warning(
                "Created admin user %r with generated password: %s  (change it under Account after signing in)",
                settings.admin_username,
                password,
            )
        else:
            log.warning("Created admin user %r from SBS_ADMIN_PASSWORD", settings.admin_username)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    # Large uploads are spooled to disk; keep that on the data volume, not in the container.
    tempfile.tempdir = str(settings.tmp_dir)

    engine = make_engine(settings.db_path)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    factory = make_session_factory(engine)
    _ensure_admin(settings, factory)

    app = FastAPI(title="Soundbending Secuencias", version="0.1.0", docs_url="/api/docs", redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.jobs = JobRunner()
    app.state.transcriber = WhisperTranscriber(settings.whisper_model, settings.models_dir)
    # Small playback copies for the browser player; makes any that are missing (e.g. after an upgrade).
    app.state.previews = PreviewMaker(settings.library_dir, factory)
    app.state.previews.kick()
    # A restart interrupts any detection in flight; don't leave songs stuck on "running".
    with factory() as db:
        for song in db.query(Song).filter(Song.sections_status.in_(("queued", "running"))):
            song.sections_status, song.sections_note = "failed", "Server restarted during detection. Click Detect to try again."
        db.commit()

    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["filesize"] = _filesize
    templates.env.filters["duration"] = lambda s: (
        f"{int(s // 60)}:{int(s % 60):02d}" if s else "–"
    )
    app.state.templates = templates

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="sbs_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=False,
    )
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.include_router(api.router)
    app.include_router(web.router)

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, _exc: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True}

    return app
