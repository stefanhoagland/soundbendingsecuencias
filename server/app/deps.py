from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import ApiToken, Song, Track, User
from .security import hash_token, new_csrf_token


class LoginRequired(Exception):
    """Raised by web routes; turned into a redirect to /login."""


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def _user_from_session(request: Request, db: Session) -> User | None:
    uid = request.session.get("uid")
    if uid is None:
        return None
    return db.get(User, uid)


def _user_from_bearer(request: Request, db: Session) -> User | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(header[7:].strip())))
    if token is None:
        return None
    token.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return token.user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return _user_from_session(request, db)


def web_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_session(request, db)
    if user is None:
        raise LoginRequired()
    return user


def web_admin(user: User = Depends(web_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user


def api_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_bearer(request, db) or _user_from_session(request, db)
    if user is None:
        raise HTTPException(401, "Not signed in", headers={"WWW-Authenticate": "Bearer"})
    return user


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = new_csrf_token()
        request.session["csrf"] = token
    return token


async def check_csrf(request: Request) -> None:
    """Reject form posts that don't carry this session's CSRF token."""
    expected = request.session.get("csrf")
    sent = request.headers.get("x-csrf-token")
    if sent is None:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/x-www-form-urlencoded") or content_type.startswith(
            "multipart/form-data"
        ):
            form = await request.form()
            sent = form.get("csrf")
    if not expected or sent != expected:
        raise HTTPException(400, "Form expired, please go back and try again")


def owned_song(song_id: int, user: User, db: Session) -> Song:
    song = db.get(Song, song_id)
    if song is None or song.owner_id != user.id:
        raise HTTPException(404, "Song not found")
    return song


def owned_track(track_id: int, user: User, db: Session) -> Track:
    track = db.get(Track, track_id)
    if track is None or track.song.owner_id != user.id:
        raise HTTPException(404, "Track not found")
    return track
