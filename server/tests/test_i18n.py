import re

from app import i18n


def test_message_translation():
    t = lambda s: i18n.translate_message("es", s)
    assert t("Saved.") == "Guardado."
    assert t("Deleted “Way Maker”.") == "Se eliminó “Way Maker”."
    assert t("Tracks saved. Removed Bass.") == "Pistas guardadas. Se quitó Bass."
    assert t("Bad.wav: Not a WAV file (missing RIFF/WAVE header)") == "Bad.wav: No es un archivo WAV (falta el encabezado RIFF/WAVE)"
    assert t("Something new") == "Something new"
    assert i18n.translate_message("en", "Saved.") == "Saved."


def test_all_template_strings_have_spanish():
    """Every _('...') in the templates has an entry, so nothing is left in English by accident."""
    from pathlib import Path

    missing = set()
    for path in Path("app/templates").glob("*.html"):
        for m in re.finditer(r"""_\((['"])(.+?)\1""", path.read_text()):
            text = m.group(2).replace("\\'", "'")
            if text not in i18n.ES and text not in ("stem", "click", "guide", "cue"):
                missing.add(text)
    # Roles are passed through _(r) with values from the code.
    assert not missing, sorted(missing)


def test_switch_language(client, web):
    r = web.get("/lang/es?next=/account", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/account"
    page = web.get("/").text
    assert 'lang="es-MX"' in page and "Biblioteca" in page and "Cerrar sesión" in page
    # Remembered on the account after signing out and back in
    web.post("/logout", data={"csrf": web.csrf})
    web.cookies.clear()
    html = web.get("/login").text
    assert "Iniciar sesión" not in html  # new browser, no preference yet
    token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    web.post("/login", data={"username": "admin", "password": "admin-pass-123", "csrf": token})
    assert "Cerrar sesión" in web.get("/").text
    # Can't be used to bounce to another site
    assert web.get("/lang/en?next=//evil.example", follow_redirects=False).headers["location"] == "/"


def test_spanish_browser_defaults_to_spanish(client):
    assert "Iniciar sesión" in client.get("/login", headers={"accept-language": "es-MX,es;q=0.9"}).text
    assert "Sign in" in client.get("/login", headers={"accept-language": "en-US"}).text
