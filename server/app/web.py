"""Server-rendered pages for managing the library in a browser."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services
from .deps import (
    check_csrf,
    csrf_token,
    get_db,
    get_settings,
    optional_user,
    owned_song,
    owned_track,
    web_admin,
    web_user,
)
from .models import TRACK_ROLES, ApiToken, Song, User
from .security import new_api_token, verify_password
from .storage import track_path

router = APIRouter(include_in_schema=False)


def render(request: Request, name: str, user: User | None, status_code: int = 200, **ctx) -> HTMLResponse:
    templates = request.app.state.templates
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        request,
        name,
        {"user": user, "csrf": csrf_token(request), "flash": flash, **ctx},
        status_code=status_code,
    )


def redirect(url: str, flash: tuple[str, str] | None = None, request: Request | None = None) -> RedirectResponse:
    if flash and request is not None:
        request.session["flash"] = {"kind": flash[0], "text": flash[1]}
    return RedirectResponse(url, status_code=303)


# ---- auth -----------------------------------------------------------------


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(optional_user)):
    if user:
        return redirect("/")
    return render(request, "login.html", None)


@router.post("/login", dependencies=[Depends(check_csrf)])
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        return render(request, "login.html", None, status_code=401, error="Wrong username or password", username=username)
    request.session.clear()
    request.session["uid"] = user.id
    return redirect("/")


@router.post("/logout", dependencies=[Depends(check_csrf)])
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


# ---- songs ----------------------------------------------------------------


@router.get("/")
def library(request: Request, q: str = "", user: User = Depends(web_user), db: Session = Depends(get_db)):
    songs = services.list_songs(db, user, q)
    return render(request, "library.html", user, songs=songs, q=q)


@router.get("/songs/new")
def new_song_page(request: Request, user: User = Depends(web_user)):
    return render(request, "song_form.html", user, song=None, keys=services.KEY_OPTIONS, form={})


@router.post("/songs", dependencies=[Depends(check_csrf)])
def create_song(
    request: Request,
    title: str = Form(""),
    artist: str = Form(""),
    bpm: str = Form(""),
    key: str = Form(""),
    time_signature: str = Form("4/4"),
    notes: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    form = dict(title=title, artist=artist, bpm=bpm, key=key, time_signature=time_signature, notes=notes)
    song = Song(owner_id=user.id, title="")
    try:
        services.apply_song_fields(song, **form)
    except services.ValidationError as exc:
        return render(
            request, "song_form.html", user, status_code=422, song=None, keys=services.KEY_OPTIONS, form=form, error=str(exc)
        )
    db.add(song)
    db.commit()
    return redirect(f"/songs/{song.id}", ("ok", "Song created. Now add its stems."), request)


@router.post("/songs/from-zip", dependencies=[Depends(check_csrf)])
async def create_song_from_zip(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    """Create one song per uploaded ZIP, named from the file (title, key and BPM if present)."""
    fetch = request.headers.get("x-requested-with") == "fetch"
    library_dir = get_settings(request).library_dir
    made, errors = [], []
    for upload in files:
        name = upload.filename or "Untitled.zip"
        if not services.is_zip_upload(upload):
            errors.append(f"{name}: not a ZIP file")
            continue
        fields = services.song_fields_from_filename(name)
        song = Song(owner_id=user.id, title="")
        services.apply_song_fields(song, artist="", time_signature="4/4", notes="", **fields)
        db.add(song)
        db.commit()
        created, errs = await services.add_tracks(db, library_dir, song, [upload])
        errors += errs
        if not created:
            services.delete_song(db, library_dir, song)
            continue
        made.append(song)
    if fetch:
        status = 422 if errors and not made else 200
        return JSONResponse(
            {"songs": [{"id": s.id, "title": s.title, "url": f"/songs/{s.id}"} for s in made], "errors": errors},
            status_code=status,
        )
    if len(made) == 1 and not errors:
        return redirect(f"/songs/{made[0].id}", ("ok", f"Created “{made[0].title}” with {len(made[0].tracks)} tracks."), request)
    msg = f"Created {len(made)} song(s)." + (" " + " ".join(errors) if errors else "")
    return redirect("/", ("error" if errors else "ok", msg), request)


@router.get("/songs/{song_id}")
def song_page(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db)
    return render(
        request,
        "song.html",
        user,
        song=song,
        roles=TRACK_ROLES,
        fmt=services.format_timestamp,
        tab="chart" if request.query_params.get("tab") == "chart" else "mix",
        transpose_options=[
            (n, services.transpose_key(song.key, n)) for n in range(-services.MAX_TRANSPOSE, services.MAX_TRANSPOSE + 1)
        ],
    )


@router.get("/songs/{song_id}/edit")
def edit_song_page(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db)
    form = dict(
        title=song.title,
        artist=song.artist,
        bpm="" if song.bpm is None else f"{song.bpm:g}",
        key=song.key,
        time_signature=song.time_signature,
        notes=song.notes,
    )
    return render(request, "song_form.html", user, song=song, keys=services.KEY_OPTIONS, form=form)


@router.post("/songs/{song_id}/edit", dependencies=[Depends(check_csrf)])
def update_song(
    song_id: int,
    request: Request,
    title: str = Form(""),
    artist: str = Form(""),
    bpm: str = Form(""),
    key: str = Form(""),
    time_signature: str = Form("4/4"),
    notes: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    song = owned_song(song_id, user, db)
    form = dict(title=title, artist=artist, bpm=bpm, key=key, time_signature=time_signature, notes=notes)
    try:
        services.apply_song_fields(song, **form)
    except services.ValidationError as exc:
        db.rollback()
        return render(
            request, "song_form.html", user, status_code=422, song=song, keys=services.KEY_OPTIONS, form=form, error=str(exc)
        )
    db.commit()
    return redirect(f"/songs/{song.id}", ("ok", "Saved."), request)


@router.post("/songs/{song_id}/delete", dependencies=[Depends(check_csrf)])
def delete_song(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db)
    title = song.title
    services.delete_song(db, get_settings(request).library_dir, song)
    return redirect("/", ("ok", f"Deleted “{title}”."), request)


# ---- tracks ---------------------------------------------------------------


@router.post("/songs/{song_id}/tracks", dependencies=[Depends(check_csrf)])
async def upload_tracks(
    song_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    song = owned_song(song_id, user, db)
    created, errors = await services.add_tracks(db, get_settings(request).library_dir, song, files)
    if request.headers.get("x-requested-with") == "fetch":
        status = 422 if errors and not created else 200
        return JSONResponse({"created": [t.id for t in created], "errors": errors}, status_code=status)
    if errors:
        return redirect(f"/songs/{song.id}", ("error", " ".join(errors)), request)
    return redirect(f"/songs/{song.id}", ("ok", f"Added {len(created)} track(s)."), request)


@router.post("/songs/{song_id}/tracks/save", dependencies=[Depends(check_csrf)])
async def save_tracks(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db)
    form = await request.form()
    try:
        removed = services.save_tracks(db, get_settings(request).library_dir, song, form)
    except services.ValidationError as exc:
        return redirect(f"/songs/{song.id}#tracks", ("error", f"Nothing was saved: {exc}"), request)
    msg = "Tracks saved." + (f" Removed {removed}." if removed else "")
    return redirect(f"/songs/{song.id}#tracks", ("ok", msg), request)


@router.post("/tracks/{track_id}", dependencies=[Depends(check_csrf)])
def update_track(
    track_id: int,
    request: Request,
    name: str = Form(...),
    role: str = Form(...),
    gain_db: str = Form("0"),
    pan: str = Form("0"),
    muted: str | None = Form(None),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    track = owned_track(track_id, user, db)
    try:
        services.update_track(track, name=name, role=role, gain_db=gain_db, pan=pan, muted=muted is not None)
    except services.ValidationError as exc:
        db.rollback()
        return redirect(f"/songs/{track.song_id}", ("error", str(exc)), request)
    db.commit()
    return redirect(f"/songs/{track.song_id}#track-{track.id}", ("ok", f"Saved {track.name}."), request)


@router.post("/tracks/{track_id}/move", dependencies=[Depends(check_csrf)])
def move_track(
    track_id: int,
    request: Request,
    direction: int = Form(...),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    track = owned_track(track_id, user, db)
    services.move_track(db, track, -1 if direction < 0 else 1)
    return redirect(f"/songs/{track.song_id}#tracks")


@router.post("/tracks/{track_id}/delete", dependencies=[Depends(check_csrf)])
def delete_track(track_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    track = owned_track(track_id, user, db)
    song_id, name = track.song_id, track.name
    services.delete_track(db, get_settings(request).library_dir, track)
    return redirect(f"/songs/{song_id}#tracks", ("ok", f"Removed {name}."), request)


@router.get("/tracks/{track_id}/audio")
def track_audio(track_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    track = owned_track(track_id, user, db)
    path = track_path(get_settings(request).library_dir, track.song_id, track.stored_filename)
    if not path.exists():
        raise HTTPException(404, "Audio file is missing on the server")
    return FileResponse(path, media_type="audio/wav", filename=track.original_filename)


# ---- key & chord chart ----------------------------------------------------


@router.post("/songs/{song_id}/transpose", dependencies=[Depends(check_csrf)])
def set_transpose(
    song_id: int,
    request: Request,
    semitones: str = Form("0"),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    song = owned_song(song_id, user, db)
    try:
        song.transpose = services.parse_transpose(semitones)
    except services.ValidationError as exc:
        if request.headers.get("x-requested-with") == "fetch":
            return JSONResponse({"error": str(exc)}, status_code=422)
        return redirect(f"/songs/{song.id}", ("error", str(exc)), request)
    db.commit()
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"transpose": song.transpose, "play_key": song.play_key})
    return redirect(f"/songs/{song.id}")


@router.post("/songs/{song_id}/chart", dependencies=[Depends(check_csrf)])
def save_chart(
    song_id: int,
    request: Request,
    chart: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    song = owned_song(song_id, user, db)
    song.chart = chart.replace("\r\n", "\n").strip("\n")
    db.commit()
    return redirect(f"/songs/{song.id}?tab=chart", ("ok", "Chord chart saved."), request)


# ---- sections -------------------------------------------------------------


@router.post("/songs/{song_id}/sections", dependencies=[Depends(check_csrf)])
def add_section(
    song_id: int,
    request: Request,
    name: str = Form(""),
    start: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    song = owned_song(song_id, user, db)
    try:
        services.add_section(db, song, name, start)
    except services.ValidationError as exc:
        return redirect(f"/songs/{song.id}#sections", ("error", str(exc)), request)
    return redirect(f"/songs/{song.id}#sections")


@router.post("/sections/{section_id}/delete", dependencies=[Depends(check_csrf)])
def delete_section(section_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    from .models import Section

    section = db.get(Section, section_id)
    if section is None or section.song.owner_id != user.id:
        raise HTTPException(404, "Section not found")
    song_id = section.song_id
    db.delete(section)
    db.commit()
    return redirect(f"/songs/{song_id}#sections")


# ---- account & admin ------------------------------------------------------


@router.get("/account")
def account_page(request: Request, user: User = Depends(web_user)):
    new_token = request.session.pop("new_token", None)
    return render(request, "account.html", user, tokens=user.tokens, new_token=new_token)


@router.post("/account/password", dependencies=[Depends(check_csrf)])
def change_password(
    request: Request,
    current: str = Form(...),
    new: str = Form(...),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    if not verify_password(current, user.password_hash):
        return redirect("/account", ("error", "Current password is wrong."), request)
    try:
        services.set_password(db, user, new)
    except services.ValidationError as exc:
        return redirect("/account", ("error", str(exc)), request)
    return redirect("/account", ("ok", "Password changed."), request)


@router.post("/account/tokens", dependencies=[Depends(check_csrf)])
def create_token(
    request: Request, name: str = Form("Playback app"), user: User = Depends(web_user), db: Session = Depends(get_db)
):
    token, token_hash = new_api_token()
    db.add(ApiToken(user_id=user.id, name=(name.strip() or "Playback app")[:128], token_hash=token_hash))
    db.commit()
    request.session["new_token"] = token
    return redirect("/account")


@router.post("/account/tokens/{token_id}/delete", dependencies=[Depends(check_csrf)])
def revoke_token(token_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    token = db.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(404, "Token not found")
    db.delete(token)
    db.commit()
    return redirect("/account", ("ok", "Token revoked."), request)


@router.get("/admin/users")
def users_page(request: Request, user: User = Depends(web_admin), db: Session = Depends(get_db)):
    users = list(db.scalars(select(User).order_by(User.username)))
    return render(request, "users.html", user, users=users)


@router.post("/admin/users", dependencies=[Depends(check_csrf)])
def create_user(
    request: Request,
    username: str = Form(""),
    display_name: str = Form(""),
    password: str = Form(""),
    is_admin: str | None = Form(None),
    user: User = Depends(web_admin),
    db: Session = Depends(get_db),
):
    try:
        new = services.create_user(db, username, password, display_name=display_name, is_admin=is_admin is not None)
    except services.ValidationError as exc:
        return redirect("/admin/users", ("error", str(exc)), request)
    return redirect("/admin/users", ("ok", f"Added {new.username}."), request)


@router.post("/admin/users/{user_id}/password", dependencies=[Depends(check_csrf)])
def reset_password(
    user_id: int,
    request: Request,
    password: str = Form(""),
    user: User = Depends(web_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    try:
        services.set_password(db, target, password)
    except services.ValidationError as exc:
        return redirect("/admin/users", ("error", str(exc)), request)
    return redirect("/admin/users", ("ok", f"Password reset for {target.username}."), request)


@router.post("/admin/users/{user_id}/delete", dependencies=[Depends(check_csrf)])
def delete_user(user_id: int, request: Request, user: User = Depends(web_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if target.id == user.id:
        return redirect("/admin/users", ("error", "You can't delete your own account."), request)
    library_dir = get_settings(request).library_dir
    for song in list(target.songs):
        services.delete_song(db, library_dir, song)
    db.delete(target)
    db.commit()
    return redirect("/admin/users", ("ok", f"Deleted {target.username}."), request)
