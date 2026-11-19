from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .music import transpose_key


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


TRACK_ROLES = ("stem", "click", "guide", "cue")
CHURCH_ROLES = ("leader", "member")


class Church(Base):
    """A church's own space: its members and its own songs."""

    __tablename__ = "churches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[User]] = relationship(back_populates="church", order_by="User.username")
    songs: Mapped[list[Song]] = relationship(back_populates="church", foreign_keys="Song.church_id")
    setlists: Mapped[list[Setlist]] = relationship(
        back_populates="church", cascade="all, delete-orphan", order_by="Setlist.service_date.desc()"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Church members sign in straight to their church; site admins have no church.
    church_id: Mapped[int | None] = mapped_column(ForeignKey("churches.id", ondelete="CASCADE"), nullable=True, index=True)
    church_role: Mapped[str] = mapped_column(String(16), default="member", server_default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    songs: Mapped[list[Song]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    tokens: Mapped[list[ApiToken]] = relationship(back_populates="user", cascade="all, delete-orphan")
    church: Mapped[Church | None] = relationship(back_populates="members")

    @property
    def is_leader(self) -> bool:
        return self.church_id is not None and self.church_role == "leader"

    @property
    def practice_only(self) -> bool:
        """Church members just pick a song and practise; they don't manage anything."""
        return self.church_id is not None and self.church_role != "leader" and not self.is_admin


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
    # Set for a church's songs; empty for personal songs.
    church_id: Mapped[int | None] = mapped_column(ForeignKey("churches.id", ondelete="CASCADE"), nullable=True, index=True)
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
    # Section detection from the guide track: "", queued, running, done, none, failed, no_guide
    sections_status: Mapped[str] = mapped_column(String(16), default="", server_default="")
    sections_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="songs")
    church: Mapped[Church | None] = relationship(back_populates="songs", foreign_keys=[church_id])
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
    # "manual" (typed in) or "auto" (heard in the guide track)
    source: Mapped[str] = mapped_column(String(8), default="manual", server_default="manual")

    song: Mapped[Song] = relationship(back_populates="sections")


class Setlist(Base):
    """An ordered list of a church's songs for a service. Members see it once a leader shares it."""

    __tablename__ = "setlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    church_id: Mapped[int] = mapped_column(ForeignKey("churches.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    church: Mapped[Church] = relationship(back_populates="setlists")
    items: Mapped[list[SetlistItem]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan", order_by="SetlistItem.position"
    )

    @property
    def songs(self) -> list[Song]:
        return [i.song for i in self.items]

    @property
    def duration_seconds(self) -> float:
        return sum(i.song.duration_seconds for i in self.items)


class SetlistItem(Base):
    __tablename__ = "setlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id", ondelete="CASCADE"), index=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    setlist: Mapped[Setlist] = relationship(back_populates="items")
    song: Mapped[Song] = relationship()
