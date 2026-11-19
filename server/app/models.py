from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .music import transpose_key


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


TRACK_ROLES = ("stem", "click", "guide", "cue")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    songs: Mapped[list[Song]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    tokens: Mapped[list[ApiToken]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ApiToken(Base):
    """Long-lived token for the playback app (sent as a Bearer header)."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="tokens")


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255), default="")
    bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    key: Mapped[str] = mapped_column(String(16), default="")
    time_signature: Mapped[str] = mapped_column(String(8), default="4/4")
    notes: Mapped[str] = mapped_column(Text, default="")
    # Chord chart in ChordPro-style text: chords in [brackets] inline, or chord lines over lyrics.
    chart: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Semitones to shift the song by when playing (chart and audio); key stays the original key.
    transpose: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="songs")
    tracks: Mapped[list[Track]] = relationship(
        back_populates="song", cascade="all, delete-orphan", order_by="Track.position"
    )
    sections: Mapped[list[Section]] = relationship(
        back_populates="song", cascade="all, delete-orphan", order_by="Section.start_seconds"
    )

    @property
    def duration_seconds(self) -> float:
        return max((t.duration_seconds or 0.0 for t in self.tracks), default=0.0)

    @property
    def play_key(self) -> str:
        return transpose_key(self.key, self.transpose or 0)

    @property
    def total_bytes(self) -> int:
        return sum(t.size_bytes for t in self.tracks)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="stem")
    position: Mapped[int] = mapped_column(Integer, default=0)

    stored_filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")

    sample_rate: Mapped[int] = mapped_column(Integer, default=0)
    channels: Mapped[int] = mapped_column(Integer, default=0)
    bit_depth: Mapped[int] = mapped_column(Integer, default=0)
    sample_format: Mapped[str] = mapped_column(String(8), default="pcm")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Mix defaults the playback app starts from.
    gain_db: Mapped[float] = mapped_column(Float, default=0.0)
    pan: Mapped[float] = mapped_column(Float, default=0.0)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    song: Mapped[Song] = relationship(back_populates="tracks")


class Section(Base):
    """A named marker in a song (Intro, Verse 1, Chorus...)."""

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    start_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    color: Mapped[str] = mapped_column(String(16), default="")

    song: Mapped[Song] = relationship(back_populates="sections")
