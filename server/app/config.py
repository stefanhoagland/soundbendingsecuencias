"""Runtime settings, read from environment variables.

Everything the server writes (database, audio, secret key) lives under
SBS_DATA_DIR so a single Unraid share mapping keeps it all.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    secret_key: str
    admin_username: str
    admin_password: str | None
    session_max_age: int
    auto_sections: bool = True
    whisper_model: str = "small"
    # Address people use to reach the site, e.g. https://secuencias.hoaglu.com (used in email links).
    public_url: str = ""
    # Outgoing email (welcome and password emails). Any SMTP service works, e.g. Resend or Gmail.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @property
    def mail_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "library.db"

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"


def _load_or_create_secret(data_dir: Path) -> str:
    env = os.environ.get("SBS_SECRET_KEY")
    if env:
        return env
    path = data_dir / ".secret_key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def _whisper_model(value: str) -> str:
    """The old default was the English-only "base.en", which can't hear Spanish guides.
    Installs that still carry it (or nothing) get the multilingual "small" model."""
    value = value.strip()
    return "small" if value in ("", "base.en") else value


def load_settings(data_dir: str | Path | None = None) -> Settings:
    root = Path(data_dir or os.environ.get("SBS_DATA_DIR", "./data")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "library").mkdir(exist_ok=True)
    (root / "tmp").mkdir(exist_ok=True)
    return Settings(
        data_dir=root,
        secret_key=_load_or_create_secret(root),
        admin_username=os.environ.get("SBS_ADMIN_USERNAME", "admin"),
        admin_password=os.environ.get("SBS_ADMIN_PASSWORD") or None,
        session_max_age=int(os.environ.get("SBS_SESSION_DAYS", "30")) * 86400,
        auto_sections=os.environ.get("SBS_AUTO_SECTIONS", "1").lower() not in ("0", "false", "no", "off"),
        whisper_model=_whisper_model(os.environ.get("SBS_WHISPER_MODEL", "")),
        public_url=os.environ.get("SBS_PUBLIC_URL", "").strip().rstrip("/"),
        smtp_host=os.environ.get("SBS_SMTP_HOST", "").strip(),
        smtp_port=int(os.environ.get("SBS_SMTP_PORT", "") or 587),
        smtp_user=os.environ.get("SBS_SMTP_USER", "").strip(),
        smtp_password=os.environ.get("SBS_SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SBS_SMTP_FROM", "").strip(),
    )
