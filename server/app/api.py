"""JSON API used by the Mac playback app (and anything else).

Authenticate with POST /api/auth/token, then send
`Authorization: Bearer <token>` on every request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import section_jobs, services
from .deps import api_user, can_add_songs, get_db, get_settings, owned_song, owned_track
from .models import ApiToken, Song, Track, User
from .security import new_api_token, verify_password
from .storage import track_path

router = APIRouter(prefix="/api", tags=["api"])

MANIFEST_VERSION = 1


class TokenRequest(BaseModel):
    username: str
    password: str
    device_name: str = Field(default="Playback app", max_length=128)


class SongIn(BaseModel):
    title: str
    artist: str = ""
    bpm: float | None = None
    key: str = ""
    time_signature: str = "4/4"
    notes: str = ""
    chart: str | None = None
    transpose: int | None = None


class TrackPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    gain_db: float | None = None
    pan: float | None = None
    muted: bool | None = None


class SectionIn(BaseModel):
    name: str
    start_seconds: float = Field(ge=0)


def track_json(request: Request, t: Track) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "role": t.role,
        "position": t.position,
        "filename": t.original_filename,
        "size_bytes": t.size_bytes,
        "sha256": t.sha256,
        "sample_rate": t.sample_rate,
        "channels": t.channels,
        "bit_depth": t.bit_depth,
        "sample_format": t.sample_format,
        "duration_seconds": round(t.duration_seconds, 3),
        "gain_db": t.gain_db,
        "pan": t.pan,
        "muted": t.muted,
        "audio_url": str(request.url_for("api_track_audio", track_id=t.id)),
    }


def song_summary(s: Song) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "artist": s.artist,
        "bpm": s.bpm,
        "key": s.key,
        "transpose": s.transpose,
        "play_key": s.play_key,
        "time_signature": s.time_signature,
        "duration_seconds": round(s.duration_seconds, 3),
        "track_count": len(s.tracks),
        "total_bytes": s.total_bytes,
        "updated_at": s.updated_at.isoformat(),
        "church_id": s.church_id,
    }


def song_manifest(request: Request, s: Song) -> dict:
    """Everything the player needs to rebuild the session."""
    return {
        "manifest_version": MANIFEST_VERSION,
        **song_summary(s),
        "notes": s.notes,
        "chart": s.chart,
        "sections_status": s.sections_status,
        "sections": [
            {"id": sec.id, "name": sec.name, "start_seconds": sec.start_seconds, "color": sec.color, "source": sec.source}
            for sec in s.sections
        ],
        "tracks": [track_json(request, t) for t in s.tracks],
    }


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


def _apply(song: Song, body: SongIn) -> None:
    fields = body.model_dump()
    chart, transpose = fields.pop("chart"), fields.pop("transpose")
    services.apply_song_fields(song, **fields)
    if chart is not None:
        song.chart = chart
    if transpose is not None:
        song.transpose = services.parse_transpose(transpose)


@router.post("/auth/token")
def create_token(body: TokenRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    token, token_hash = new_api_token()
    db.add(ApiToken(user=user, name=body.device_name, token_hash=token_hash))
    db.commit()
    return {"token": token, "user": {"id": user.id, "username": user.username}}


@router.get("/me")
def me(user: User = Depends(api_user)):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "church": {"id": user.church.id, "name": user.church.name, "slug": user.church.slug} if user.church else None,
        "church_role": user.church_role if user.church else None,
    }


@router.get("/songs")
def list_songs(q: str = "", user: User = Depends(api_user), db: Session = Depends(get_db)):
    return {"songs": [song_summary(s) for s in services.list_songs(db, user, q, user.church)]}


@router.post("/songs", status_code=201)
def create_song(body: SongIn, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    if not can_add_songs(user):
        raise HTTPException(403, "Only church leaders can add songs")
    song = Song(owner=user, church_id=user.church_id, title="")
    try:
        _apply(song, body)
    except services.ValidationError as exc:
        raise _bad_request(exc) from exc
    db.add(song)
    db.commit()
    return song_manifest(request, song)


@router.get("/songs/{song_id}")
def get_song(song_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    return song_manifest(request, owned_song(song_id, user, db, edit=False))


@router.put("/songs/{song_id}")
def update_song(
    song_id: int, body: SongIn, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
):
    song = owned_song(song_id, user, db)
    try:
        _apply(song, body)
    except services.ValidationError as exc:
        raise _bad_request(exc) from exc
    db.commit()
    return song_manifest(request, song)


@router.delete("/songs/{song_id}", status_code=204)
def delete_song(song_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    services.delete_song(db, get_settings(request).library_dir, owned_song(song_id, user, db))


@router.post("/songs/{song_id}/tracks", status_code=201)
async def upload_tracks(
    song_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(api_user),
    db: Session = Depends(get_db),
):
    song = owned_song(song_id, user, db)
    created, errors = await services.add_tracks(db, get_settings(request).library_dir, song, files)
    if created:
        request.app.state.previews.kick()
        section_jobs.maybe_queue_after_upload(request.app.state, db, song)
    if errors and not created:
        raise HTTPException(422, "; ".join(errors))
    return {"tracks": [track_json(request, t) for t in created], "errors": errors}


@router.patch("/tracks/{track_id}")
def patch_track(
    track_id: int, body: TrackPatch, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
):
    track = owned_track(track_id, user, db)
    try:
        services.update_track(track, **body.model_dump())
    except services.ValidationError as exc:
        raise _bad_request(exc) from exc
    db.commit()
    return track_json(request, track)


@router.delete("/tracks/{track_id}", status_code=204)
def delete_track(track_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    services.delete_track(db, get_settings(request).library_dir, owned_track(track_id, user, db))


@router.get("/tracks/{track_id}/audio", name="api_track_audio")
def track_audio(track_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    track = owned_track(track_id, user, db, edit=False)
    path = track_path(get_settings(request).library_dir, track.song_id, track.stored_filename)
    if not path.exists():
        raise HTTPException(404, "Audio file is missing on the server")
    return FileResponse(path, media_type="audio/wav", filename=track.original_filename)


@router.post("/songs/{song_id}/sections", status_code=201)
def add_section(
    song_id: int, body: SectionIn, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
):
    song = owned_song(song_id, user, db)
    try:
        services.add_section(db, song, body.name, body.start_seconds)
    except services.ValidationError as exc:
        raise _bad_request(exc) from exc
    return song_manifest(request, song)



# ---- setlists ---------------------------------------------------------------


def setlist_json(sl) -> dict:
    return {
        "id": sl.id,
        "name": sl.name,
        "service_date": sl.service_date.isoformat() if sl.service_date else None,
        "notes": sl.notes,
        "shared": sl.shared,
        "songs": [song_summary(i.song) for i in sl.items],
    }


@router.get("/setlists")
def list_setlists(user: User = Depends(api_user), db: Session = Depends(get_db)):
    """The church's setlists (members get only shared ones), soonest first then past."""
    if user.church is None:
        return {"setlists": []}
    upcoming, past = services.church_setlists(db, user.church, shared_only=user.practice_only)
    return {"setlists": [setlist_json(sl) for sl in upcoming + past]}


@router.get("/setlists/{setlist_id}")
def get_setlist(setlist_id: int, user: User = Depends(api_user), db: Session = Depends(get_db)):
    from .web import setlist_for

    return setlist_json(setlist_for(setlist_id, user, db, manage=False))
