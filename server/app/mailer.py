"""Welcome and password emails.

Links carry a signed token (no database table): it names the user, expires, and
includes a piece of their current password hash, so it stops working as soon as
the password is set. Sending goes through any SMTP service (Resend, Gmail, ...)
configured with the SBS_SMTP_* settings.
"""

from __future__ import annotations

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import Settings
from .models import User

log = logging.getLogger("soundbending.mail")

SITE = "Soundbending Secuencias"
# How long each kind of link works, in seconds.
LIFETIME = {"invite": 7 * 86400, "reset": 2 * 3600}


class MailError(RuntimeError):
    pass


# ---- links -------------------------------------------------------------------

def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="password-link")


def make_token(settings: Settings, user: User, kind: str) -> str:
    return _serializer(settings).dumps({"u": user.id, "h": user.password_hash[-16:], "k": kind})


def read_token(settings: Settings, db: Session, token: str) -> tuple[User, str] | None:
    """The user and link kind, or None if the link is bad, expired or already used."""
    s = _serializer(settings)
    try:
        data = s.loads(token or "", max_age=max(LIFETIME.values()))
        kind = data.get("k")
        s.loads(token, max_age=LIFETIME.get(kind, 0))
    except (BadSignature, SignatureExpired, AttributeError):
        return None
    user = db.get(User, data.get("u"))
    if user is None or user.password_hash[-16:] != data.get("h"):
        return None
    return user, kind


# ---- sending -----------------------------------------------------------------

class SmtpMailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.mail_enabled

    def send(self, to: str, subject: str, text: str, html_body: str) -> None:
        st = self.settings
        if not self.enabled:
            raise MailError("Email isn't set up on the server yet")
        msg = EmailMessage()
        name, addr = parseaddr(st.smtp_from)
        msg["From"] = formataddr((name or SITE, addr or st.smtp_from))
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        msg.add_alternative(html_body, subtype="html")
        try:
            if st.smtp_port == 465:
                server = smtplib.SMTP_SSL(st.smtp_host, st.smtp_port, timeout=20, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(st.smtp_host, st.smtp_port, timeout=20)
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
            with server:
                if st.smtp_user:
                    server.login(st.smtp_user, st.smtp_password)
                server.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("Sending email to %s failed: %s", to, exc)
            raise MailError(f"Couldn't send the email ({exc})") from exc


# ---- messages ----------------------------------------------------------------

TEXT = {
    "en": {
        "invite_subject": "Welcome to {site}",
        "invite_intro": "{inviter} added you to {place} on {site}, where you can practice with the multitracks.",
        "invite_action": "Set your password",
        "invite_expiry": "This link works for 7 days.",
        "reset_subject": "Reset your {site} password",
        "reset_intro": "Someone asked to reset the password for your {site} account. If it was you, use the button below.",
        "reset_action": "Choose a new password",
        "reset_expiry": "This link works for 2 hours. If you didn't ask for this, you can ignore this email.",
        "hello": "Hi {name},",
        "username": "Your username is {username}.",
        "fallback": "If the button doesn't work, copy this link into your browser:",
        "library": "their library",
    },
    "es": {
        "invite_subject": "Bienvenido a {site}",
        "invite_intro": "{inviter} te agregó a {place} en {site}, donde puedes ensayar con las secuencias.",
        "invite_action": "Crear tu contraseña",
        "invite_expiry": "Este enlace funciona durante 7 días.",
        "reset_subject": "Restablece tu contraseña de {site}",
        "reset_intro": "Alguien pidió restablecer la contraseña de tu cuenta de {site}. Si fuiste tú, usa el botón de abajo.",
        "reset_action": "Elegir una nueva contraseña",
        "reset_expiry": "Este enlace funciona durante 2 horas. Si no lo pediste, puedes ignorar este correo.",
        "hello": "Hola {name}:",
        "username": "Tu usuario es {username}.",
        "fallback": "Si el botón no funciona, copia este enlace en tu navegador:",
        "library": "su biblioteca",
    },
}


def compose(kind: str, lang: str, user: User, link: str, inviter: str = "") -> tuple[str, str, str]:
    """(subject, plain text, html) for an "invite" or "reset" email."""
    t = TEXT["es" if lang == "es" else "en"]
    place = user.church.name if user.church else SITE
    fill = dict(site=SITE, inviter=inviter or SITE, place=place, name=user.display_name or user.username, username=user.username)
    subject = t[f"{kind}_subject"].format(**fill)
    lines = [
        t["hello"].format(**fill),
        t[f"{kind}_intro"].format(**fill),
        t["username"].format(**fill),
    ]
    action, expiry = t[f"{kind}_action"], t[f"{kind}_expiry"]
    text = "\n\n".join(lines + [f"{action}: {link}", expiry]) + "\n"
    e = html.escape
    paras = "".join(f'<p style="margin:0 0 14px">{e(line)}</p>' for line in lines)
    html_body = f"""<!doctype html><html><body style="margin:0;background:#f4f4f6;padding:24px;font:15px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;color:#1d2129">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:28px">
<div style="font-weight:800;font-size:18px;margin-bottom:18px">Soundbending <span style="color:#ff7a3d">Secuencias</span></div>
{paras}
<p style="margin:22px 0"><a href="{e(link)}" style="background:#ff7a3d;color:#111;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:8px;display:inline-block">{e(action)}</a></p>
<p style="margin:0 0 14px;color:#666;font-size:13px">{e(expiry)}</p>
<p style="margin:0;color:#888;font-size:12px">{e(t["fallback"])}<br><a href="{e(link)}" style="color:#888;word-break:break-all">{e(link)}</a></p>
</div></body></html>"""
    return subject, text, html_body
