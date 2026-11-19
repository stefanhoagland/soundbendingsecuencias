"""Song/track operations shared by the web pages and the JSON API."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audio import InvalidWav, guess_role, track_name_from_filename
from .music import transpose_key  # noqa: F401  (re-exported)
from .models import TRACK_ROLES, Section, Song, Track, User
from .security import hash_password
from .storage import delete_song_dir, delete_track_file, save_fileobj, save_upload

KEYS = [
    "C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B",
]
KEY_OPTIONS = [""] + KEYS + [k + "m" for k in KEYS]


MAX_TRANSPOSE = 11


class ValidationError(ValueError):
    pass


def parse_transpose(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Transpose must be a whole number of semitones") from exc
    if not -MAX_TRANSPOSE <= n <= MAX_TRANSPOSE:
        raise ValidationError(f"Transpose must be between -{MAX_TRANSPOSE} and +{MAX_TRANSPOSE} semitones")
    return n


def parse_bpm(value: str | float | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        bpm = float(value)
    except ValueError as exc:
        raise ValidationError("BPM must be a number") from exc
    if not 20 <= bpm <= 400:
        raise ValidationError("BPM must be between 20 and 400")
    return round(bpm, 3)


def parse_time_signature(value: str | None) -> str:
    value = (value or "4/4").strip()
    if not re.fullmatch(r"\d{1,2}/(1|2|4|8|16|32)", value):
        raise ValidationError("Time signature should look like 4/4 or 6/8")
    return value


def parse_timestamp(value: str | float) -> float:
    """Accept seconds ("83.5") or m:ss(.ms) ("1:23.5") or h:mm:ss."""
    text = str(value).strip()
    if not text:
        raise ValidationError("Enter a start time")
    parts = text.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ValidationError("Time should look like 1:23 or 83.5") from exc
    if len(nums) > 3 or any(n < 0 for n in nums):
        raise ValidationError("Time should look like 1:23 or 83.5")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return round(seconds, 3)


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return ""
    total = max(0.0, float(seconds))
    whole = int(total)
    frac = round(total - whole, 3)
    if frac >= 1:
        whole, frac = whole + 1, 0.0
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    sec = f"{s:02d}"
    if frac:
        sec += f"{frac:.3f}"[1:].rstrip("0")
    return f"{h}:{m:02d}:{sec}" if h else f"{m}:{sec}"


def apply_song_fields(song: Song, *, title, artist, bpm, key, time_signature, notes) -> None:
    title = (title or "").strip()
    if not title:
        raise ValidationError("Title is required")
    key = (key or "").strip()
    if key not in KEY_OPTIONS:
        raise ValidationError("Unknown key")
    song.title = title[:255]
    song.artist = (artist or "").strip()[:255]
    song.bpm = parse_bpm(bpm)
    song.key = key
    song.time_signature = parse_time_signature(time_signature)
    song.notes = (notes or "").strip()


def list_songs(db: Session, user: User, q: str = "") -> list[Song]:
    stmt = select(Song).where(Song.owner_id == user.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Song.title.ilike(like) | Song.artist.ilike(like))
    return list(db.scalars(stmt.order_by(func.lower(Song.title))))


def _natural_key(name: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def wav_entries(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """WAV files in a ZIP, skipping folders and macOS metadata, in natural name order."""
    out = []
    for info in zf.infolist():
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if info.is_dir() or "__MACOSX" in path.parts or path.name.startswith("."):
            continue
        if path.suffix.lower() in (".wav", ".wave"):
            out.append(info)
    return sorted(out, key=lambda i: _natural_key(PurePosixPath(i.filename).name))


def _new_track(song: Song, filename: str, position: int, saved) -> Track:
    stored, size, sha, info = saved
    return Track(
        song=song,
        name=track_name_from_filename(filename)[:255],
        role=guess_role(filename),
        position=position,
        stored_filename=stored,
        original_filename=filename[:255],
        size_bytes=size,
        sha256=sha,
        sample_rate=info.sample_rate,
        channels=info.channels,
        bit_depth=info.bit_depth,
        sample_format=info.sample_format,
        duration_seconds=info.duration_seconds,
    )


def is_zip_upload(upload: UploadFile) -> bool:
    name = (upload.filename or "").lower()
    if name.endswith(".zip"):
        return True
    try:
        pos = upload.file.tell()
        magic = upload.file.read(4)
        upload.file.seek(pos)
        return magic == b"PK\x03\x04"
    except (OSError, ValueError):
        return False


async def add_tracks(
    db: Session, library_dir: Path, song: Song, uploads: list[UploadFile]
) -> tuple[list[Track], list[str]]:
    """Save each upload as a track; ZIPs are unpacked and each WAV inside becomes a track.
    Returns (created tracks, error messages)."""
    created: list[Track] = []
    errors: list[str] = []
    next_pos = max((t.position for t in song.tracks), default=-1) + 1
    for upload in uploads:
        filename = Path(upload.filename or "track.wav").name
        if not filename:
            continue
        if is_zip_upload(upload):
            try:
                upload.file.seek(0)
                zf = zipfile.ZipFile(upload.file)
            except zipfile.BadZipFile:
                errors.append(f"{filename}: not a valid ZIP file")
                continue
            with zf:
                entries = wav_entries(zf)
                if not entries:
                    errors.append(f"{filename}: no WAV files inside")
                for entry in entries:
                    inner = PurePosixPath(entry.filename.replace("\\", "/")).name
                    try:
                        with zf.open(entry) as fh:
                            saved = save_fileobj(library_dir, song.id, fh)
                    except (InvalidWav, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                        errors.append(f"{inner}: {exc}")
                        continue
                    track = _new_track(song, inner, next_pos, saved)
                    db.add(track)
                    created.append(track)
                    next_pos += 1
            continue
        try:
            saved = await save_upload(library_dir, song.id, upload)
        except InvalidWav as exc:
            errors.append(f"{filename}: {exc}")
            continue
        track = _new_track(song, filename, next_pos, saved)
        db.add(track)
        created.append(track)
        next_pos += 1
    db.commit()
    return created, errors


_BPM_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*bpm", re.I)


def song_fields_from_filename(filename: str) -> dict:
    """'Way Maker - E - 68bpm.zip' -> title 'Way Maker', key 'E', bpm 68."""
    stem = re.sub(r"\.zip$", "", Path(filename).name, flags=re.I)
    fields: dict = {"title": stem.strip() or "Untitled", "bpm": None, "key": ""}
    if m := _BPM_RE.search(stem):
        bpm = float(m.group(1))
        if 20 <= bpm <= 400:
            fields["bpm"] = bpm
        stem = stem[: m.start()] + stem[m.end():]
    parts = [p.strip() for p in re.split(r"\s+-\s+|_-_|\s*\|\s*", stem) if p.strip()]
    rest = []
    for part in parts:
        km = re.fullmatch(r"(?:key(?: of)?\s*)?([A-G][b#]?m?)", part, re.I)
        if km and not fields["key"] and km.group(1)[0].isupper() and km.group(1) in KEY_OPTIONS:
            fields["key"] = km.group(1)
        else:
            rest.append(part)
    title = " - ".join(rest).replace("_", " ").strip(" -")
    if not fields["key"] and "_" in stem:
        # Underscore names like Goodness_of_God_Ab: a trailing key token.
        words = title.split()
        if len(words) > 1 and words[-1] in KEY_OPTIONS and words[-1][0].isupper():
            fields["key"] = words.pop()
            title = " ".join(words)
    fields["title"] = re.sub(r"\s{2,}", " ", title) or "Untitled"
    return fields


def update_track(track: Track, *, name=None, role=None, gain_db=None, pan=None, muted=None) -> None:
    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Track name is required")
        track.name = name[:255]
    if role is not None:
        if role not in TRACK_ROLES:
            raise ValidationError("Unknown track role")
        track.role = role
    if gain_db is not None:
        try:
            g = float(gain_db)
        except ValueError as exc:
            raise ValidationError("Gain must be a number") from exc
        track.gain_db = max(-60.0, min(12.0, g))
    if pan is not None:
        try:
            p = float(pan)
        except ValueError as exc:
            raise ValidationError("Pan must be a number") from exc
        track.pan = max(-1.0, min(1.0, p))
    if muted is not None:
        track.muted = bool(muted)


def save_tracks(db: Session, library_dir: Path, song: Song, form) -> int:
    """Apply the whole track list from the song page in one go: edits, order and removals.
    Validates everything first so a bad value changes nothing. Returns tracks removed."""
    by_id = {t.id: t for t in song.tracks}
    order = [int(x) for x in form.getlist("order") if str(x).isdigit() and int(x) in by_id]
    order += [tid for tid in by_id if tid not in order]
    removing = [by_id[tid] for tid in order if form.get(f"delete-{tid}")]
    try:
        for tid in order:
            if by_id[tid] in removing:
                continue
            update_track(
                by_id[tid],
                name=form.get(f"name-{tid}", by_id[tid].name),
                role=form.get(f"role-{tid}", by_id[tid].role),
                gain_db=form.get(f"gain-{tid}", by_id[tid].gain_db),
                pan=form.get(f"pan-{tid}", by_id[tid].pan),
                muted=bool(form.get(f"muted-{tid}")),
            )
    except ValidationError:
        db.rollback()
        raise
    keep = [tid for tid in order if by_id[tid] not in removing]
    for pos, tid in enumerate(keep):
        by_id[tid].position = pos
    files = [(t.song_id, t.stored_filename) for t in removing]
    for t in removing:
        db.delete(t)
    db.commit()
    for song_id, stored in files:
        delete_track_file(library_dir, song_id, stored)
    return len(removing)


def move_track(db: Session, track: Track, direction: int) -> None:
    tracks = list(track.song.tracks)
    idx = tracks.index(track)
    swap = idx + direction
    if 0 <= swap < len(tracks):
        tracks[idx], tracks[swap] = tracks[swap], tracks[idx]
    for pos, t in enumerate(tracks):
        t.position = pos
    db.commit()


def delete_track(db: Session, library_dir: Path, track: Track) -> None:
    song_id, stored = track.song_id, track.stored_filename
    db.delete(track)
    db.commit()
    delete_track_file(library_dir, song_id, stored)


def delete_song(db: Session, library_dir: Path, song: Song) -> None:
    song_id = song.id
    db.delete(song)
    db.commit()
    delete_song_dir(library_dir, song_id)


def add_section(db: Session, song: Song, name: str, start) -> Section:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Section name is required")
    section = Section(song=song, name=name[:128], start_seconds=parse_timestamp(start))
    db.add(section)
    db.commit()
    return section


def create_user(db: Session, username: str, password: str, *, display_name: str = "", is_admin=False) -> User:
    username = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{2,64}", username):
        raise ValidationError("Username must be 2-64 letters, numbers, dots, dashes or underscores")
    if len(password or "") < 8:
        raise ValidationError("Password must be at least 8 characters")
    if db.scalar(select(User).where(User.username == username)):
        raise ValidationError("That username is taken")
    user = User(
        username=username,
        display_name=(display_name or "").strip() or username,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    return user


def set_password(db: Session, user: User, password: str) -> None:
    if len(password or "") < 8:
        raise ValidationError("Password must be at least 8 characters")
    user.password_hash = hash_password(password)
    db.commit()
