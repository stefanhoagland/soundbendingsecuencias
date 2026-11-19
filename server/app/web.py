"""Server-rendered pages for managing the library in a browser."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import section_jobs, services
from .deps import (
    can_add_songs,
    can_edit,
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
from .models import CHURCH_ROLES, TRACK_ROLES, ApiToken, Church, Song, User
from .security import new_api_token, verify_password
from .storage import track_path

router = APIRouter(include_in_schema=False)


def render(request: Request, name: str, user: User | None, status_code: int = 200, **ctx) -> HTMLResponse:
    templates = request.app.state.templates
    flash = request.session.pop("flash", None)
    nav_church = None
    if user is not None:
        if user.church is not None:
            nav_church = {"slug": user.church.slug, "name": user.church.name, "leader": user.is_leader}
        elif user.is_admin and request.session.get("church"):
            nav_church = {**request.session["church"], "leader": True}
    return templates.TemplateResponse(
        request,
        name,
        {"user": user, "csrf": csrf_token(request), "flash": flash, "nav_church": nav_church, **ctx},
        status_code=status_code,
    )


def redirect(url: str, flash: tuple[str, str] | None = None, request: Request | None = None) -> RedirectResponse:
    if flash and request is not None:
        request.session["flash"] = {"kind": flash[0], "text": flash[1]}
    return RedirectResponse(url, status_code=303)


def current_church(request: Request, user: User, db: Session) -> Church | None:
    """The church whose library this person is working in (admins pick one by opening /c/<slug>)."""
    if not user.is_admin:
        return user.church
    picked = request.session.get("church")
    church = db.get(Church, picked["id"]) if picked else None
    if picked and church is None:
        request.session.pop("church", None)
    return church


def library_url(church: Church | None) -> str:
    return f"/c/{church.slug}" if church else "/"


def require_adder(user: User) -> None:
    if not can_add_songs(user):
        raise HTTPException(403, "Only church leaders can add songs")


def church_for_manager(slug: str, user: User, db: Session) -> Church:
    church = db.scalar(select(Church).where(Church.slug == slug))
    if church is None or not (user.is_admin or (user.church_id == church.id and user.is_leader)):
        raise HTTPException(404, "Church not found")
    return church


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
    if user.church is not None:
        return redirect(library_url(user.church) + (f"?q={q}" if q else ""))
    request.session.pop("church", None)
    songs = services.list_songs(db, user, q)
    return render(request, "library.html", user, songs=songs, q=q, church=None, can_add=can_add_songs(user))


@router.get("/c/{slug}")
def church_library(slug: str, request: Request, q: str = "", user: User = Depends(web_user), db: Session = Depends(get_db)):
    church = db.scalar(select(Church).where(Church.slug == slug))
    if church is None or not (user.is_admin or user.church_id == church.id):
        raise HTTPException(404, "Church not found")
    if user.is_admin:
        request.session["church"] = {"id": church.id, "slug": church.slug, "name": church.name}
    songs = services.list_songs(db, user, q, church)
    return render(request, "library.html", user, songs=songs, q=q, church=church, can_add=can_add_songs(user))


@router.get("/songs/new")
def new_song_page(request: Request, user: User = Depends(web_user)):
    require_adder(user)
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
    require_adder(user)
    form = dict(title=title, artist=artist, bpm=bpm, key=key, time_signature=time_signature, notes=notes)
    church = current_church(request, user, db)
    song = Song(owner_id=user.id, church_id=church.id if church else None, title="")
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
    require_adder(user)
    fetch = request.headers.get("x-requested-with") == "fetch"
    library_dir = get_settings(request).library_dir
    church = current_church(request, user, db)
    made, errors = [], []
    for upload in files:
        name = upload.filename or "Untitled.zip"
        if not services.is_zip_upload(upload):
            errors.append(f"{name}: not a ZIP file")
            continue
        fields = services.song_fields_from_filename(name)
        song = Song(owner_id=user.id, church_id=church.id if church else None, title="")
        services.apply_song_fields(song, artist="", time_signature="4/4", notes="", **fields)
        db.add(song)
        db.commit()
        created, errs = await services.add_tracks(db, library_dir, song, [upload])
        errors += errs
        if not created:
            services.delete_song(db, library_dir, song)
            continue
        section_jobs.maybe_queue_after_upload(request.app.state, db, song)
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
    return redirect(library_url(church), ("error" if errors else "ok", msg), request)


@router.get("/songs/{song_id}")
def song_page(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db, edit=False)
    church = song.church
    return render(
        request,
        "song.html",
        user,
        song=song,
        editable=can_edit(user, song),
        back_url=library_url(church),
        roles=TRACK_ROLES,
        fmt=services.format_timestamp,
        has_guide=section_jobs.has_guide(song),
        name_options=services.track_name_options(db, user),
        suggest_name=lambda t: services.clean_name(t.original_filename, song.title),
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
    title, church = song.title, song.church
    services.delete_song(db, get_settings(request).library_dir, song)
    return redirect(library_url(church), ("ok", f"Deleted “{title}”."), request)


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
    if created:
        section_jobs.maybe_queue_after_upload(request.app.state, db, song)
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
    if not song.sections_status:
        section_jobs.maybe_queue_after_upload(request.app.state, db, song)  # e.g. a track was just marked Guide
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
    track = owned_track(track_id, user, db, edit=False)
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


@router.post("/songs/{song_id}/sections/detect", dependencies=[Depends(check_csrf)])
def detect_sections(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db)
    if not section_jobs.has_guide(song):
        return redirect(f"/songs/{song.id}#sections", ("error", "Mark one track as Guide first."), request)
    section_jobs.queue(request.app.state, db, song)
    return redirect(f"/songs/{song.id}#sections")


@router.get("/songs/{song_id}/sections/status")
def sections_status(song_id: int, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db, edit=False)
    return {"status": song.sections_status, "note": song.sections_note, "count": len(song.sections)}


@router.post("/songs/{song_id}/sections/clear-auto", dependencies=[Depends(check_csrf)])
def clear_auto_sections(song_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    song = owned_song(song_id, user, db)
    for sec in [s for s in song.sections if s.source == "auto"]:
        db.delete(sec)
    song.sections_status, song.sections_note = "", ""
    db.commit()
    return redirect(f"/songs/{song.id}#sections")


@router.post("/sections/{section_id}/delete", dependencies=[Depends(check_csrf)])
def delete_section(section_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    from .models import Section

    section = db.get(Section, section_id)
    if section is None:
        raise HTTPException(404, "Section not found")
    owned_song(section.song_id, user, db)
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


# ---- churches ---------------------------------------------------------------


@router.get("/admin/churches")
def churches_page(request: Request, user: User = Depends(web_admin), db: Session = Depends(get_db)):
    churches = list(db.scalars(select(Church).order_by(Church.name)))
    return render(request, "churches.html", user, churches=churches)


@router.post("/admin/churches", dependencies=[Depends(check_csrf)])
def create_church(
    request: Request,
    name: str = Form(""),
    slug: str = Form(""),
    leader_username: str = Form(""),
    leader_name: str = Form(""),
    leader_password: str = Form(""),
    user: User = Depends(web_admin),
    db: Session = Depends(get_db),
):
    try:
        if leader_username.strip():
            # Check the leader's details before creating anything.
            services.validate_new_user(db, leader_username, leader_password)
        church = services.create_church(db, name, slug)
        if leader_username.strip():
            services.create_user(
                db, leader_username, leader_password, display_name=leader_name, church=church, church_role="leader"
            )
    except services.ValidationError as exc:
        return redirect("/admin/churches", ("error", str(exc)), request)
    return redirect("/admin/churches", ("ok", f"Added {church.name}. Its page is /c/{church.slug}."), request)


@router.post("/admin/churches/{church_id}/delete", dependencies=[Depends(check_csrf)])
def delete_church(church_id: int, request: Request, user: User = Depends(web_admin), db: Session = Depends(get_db)):
    church = db.get(Church, church_id)
    if church is None:
        raise HTTPException(404, "Church not found")
    name = church.name
    if (request.session.get("church") or {}).get("id") == church.id:
        request.session.pop("church", None)
    services.delete_church(db, get_settings(request).library_dir, church)
    return redirect("/admin/churches", ("ok", f"Deleted {name}."), request)


@router.get("/c/{slug}/members")
def members_page(slug: str, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)):
    church = church_for_manager(slug, user, db)
    return render(request, "members.html", user, church=church, roles=CHURCH_ROLES)


@router.post("/c/{slug}/members", dependencies=[Depends(check_csrf)])
def add_member(
    slug: str,
    request: Request,
    username: str = Form(""),
    display_name: str = Form(""),
    password: str = Form(""),
    role: str = Form("member"),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    church = church_for_manager(slug, user, db)
    url = f"/c/{church.slug}/members"
    try:
        new = services.create_user(db, username, password, display_name=display_name, church=church, church_role=role)
    except services.ValidationError as exc:
        return redirect(url, ("error", str(exc)), request)
    return redirect(url, ("ok", f"Added {new.username}. They sign in at this site and land on {church.name}."), request)


def _member(church: Church, user_id: int, db: Session) -> User:
    member = db.get(User, user_id)
    if member is None or member.church_id != church.id:
        raise HTTPException(404, "Member not found")
    return member


@router.post("/c/{slug}/members/{user_id}/role", dependencies=[Depends(check_csrf)])
def change_member_role(
    slug: str,
    user_id: int,
    request: Request,
    role: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    church = church_for_manager(slug, user, db)
    member = _member(church, user_id, db)
    url = f"/c/{church.slug}/members"
    if member.id == user.id and role != "leader":
        return redirect(url, ("error", "You can't take away your own leader role."), request)
    try:
        services.set_church_role(db, member, role)
    except services.ValidationError as exc:
        return redirect(url, ("error", str(exc)), request)
    return redirect(url, ("ok", f"{member.username} is now a {role}."), request)


@router.post("/c/{slug}/members/{user_id}/password", dependencies=[Depends(check_csrf)])
def reset_member_password(
    slug: str,
    user_id: int,
    request: Request,
    password: str = Form(""),
    user: User = Depends(web_user),
    db: Session = Depends(get_db),
):
    church = church_for_manager(slug, user, db)
    member = _member(church, user_id, db)
    url = f"/c/{church.slug}/members"
    try:
        services.set_password(db, member, password)
    except services.ValidationError as exc:
        return redirect(url, ("error", str(exc)), request)
    return redirect(url, ("ok", f"Password reset for {member.username}."), request)


@router.post("/c/{slug}/members/{user_id}/delete", dependencies=[Depends(check_csrf)])
def remove_member(
    slug: str, user_id: int, request: Request, user: User = Depends(web_user), db: Session = Depends(get_db)
):
    church = church_for_manager(slug, user, db)
    member = _member(church, user_id, db)
    url = f"/c/{church.slug}/members"
    if member.id == user.id:
        return redirect(url, ("error", "You can't remove yourself."), request)
    # The church keeps the songs this person added; they move to whoever removed them.
    for song in list(member.songs):
        song.owner_id = user.id
    db.delete(member)
    db.commit()
    return redirect(url, ("ok", f"Removed {member.username}."), request)
