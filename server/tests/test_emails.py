import re


def _csrf(client, url="/login"):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(url).text).group(1)


def _link(mail):
    return re.search(r"(http\S+/set-password\?token=[\w.\-]+)", mail["text"]).group(1)


def test_new_leader_gets_welcome_email_and_sets_password(web, app, client):
    r = web.post(
        "/admin/churches",
        data={"name": "Iglesia Luz", "leader_username": "ana", "leader_name": "Ana", "leader_email": "Ana@Example.com", "csrf": web.csrf},
    )
    assert "Welcome email sent to ana@example.com" in r.text
    [mail] = app.state.mailer.sent
    assert mail["to"] == "ana@example.com" and "Iglesia Luz" in mail["text"] and "ana" in mail["text"]
    link = _link(mail)
    path = link.split("testserver", 1)[1]

    web.post("/logout", data={"csrf": web.csrf})
    web.cookies.clear()
    page = client.get(path)
    assert page.status_code == 200 and "ana" in page.text
    token = re.search(r'name="token" value="([^"]+)"', page.text).group(1)
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    r = client.post("/set-password", data={"token": token, "password": "nuevo-pass-1", "confirm": "nope", "csrf": csrf})
    assert r.status_code == 400 and "passwords don" in r.text
    r = client.post("/set-password", data={"token": token, "password": "nuevo-pass-1", "confirm": "nuevo-pass-1", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "Iglesia Luz" in client.get("/c/iglesia-luz").text  # signed in as the leader
    # The link only works once
    assert client.get(path).status_code == 400


def test_password_required_without_email(web, app):
    r = web.post("/admin/users", data={"username": "nomail", "csrf": web.csrf})
    assert "Add their email" in r.text
    app.state.mailer.enabled = False
    r = web.post("/admin/users", data={"username": "nomail", "email": "x@y.com", "csrf": web.csrf})
    assert "at least 8 characters" in r.text


def test_forgot_password(web, app, client):
    web.post("/admin/users", data={"username": "bob", "email": "bob@example.com", "password": "bob-pass-123", "csrf": web.csrf})
    app.state.mailer.sent.clear()
    web.post("/logout", data={"csrf": web.csrf})
    web.cookies.clear()
    assert "Forgot password?" in client.get("/login").text
    csrf = _csrf(client, "/forgot-password")
    r = client.post("/forgot-password", data={"who": "nobody", "csrf": csrf})
    assert "If that account has an email" in r.text and not app.state.mailer.sent
    r = client.post("/forgot-password", data={"who": "BOB@example.com", "csrf": csrf})
    assert "If that account has an email" in r.text
    [mail] = app.state.mailer.sent
    assert "reset" in mail["subject"].lower()
    assert client.get(_link(mail).split("testserver", 1)[1]).status_code == 200


def test_leader_sends_link_to_existing_member(web, app):
    web.post("/admin/churches", data={"name": "Casa", "csrf": web.csrf})
    web.post("/c/casa/members", data={"username": "luis", "password": "luis-pass-123", "csrf": web.csrf})
    from app.models import User

    with app.state.session_factory() as db:
        uid = db.query(User).filter_by(username="luis").one().id
    r = web.post(f"/c/casa/members/{uid}/invite", data={"email": "luis@example.com", "csrf": web.csrf})
    assert "Password link sent to luis@example.com" in r.text
    assert app.state.mailer.sent[-1]["to"] == "luis@example.com"
    # Duplicate emails are refused
    web.post("/c/casa/members", data={"username": "otro", "password": "otro-pass-123", "csrf": web.csrf})
    with app.state.session_factory() as db:
        oid = db.query(User).filter_by(username="otro").one().id
    r = web.post(f"/c/casa/members/{oid}/invite", data={"email": "LUIS@example.com", "csrf": web.csrf})
    assert "already uses that email" in r.text


def test_spanish_welcome_email(web, app):
    web.get("/lang/es?next=/")
    web.post("/admin/users", data={"username": "maria", "email": "maria@example.com", "csrf": web.csrf})
    mail = app.state.mailer.sent[-1]
    assert mail["subject"].startswith("Bienvenido") and "Crear tu contraseña" in mail["text"]


def test_account_email(web):
    r = web.post("/account/email", data={"email": "admin@example.com", "csrf": web.csrf})
    assert "Email saved." in r.text and 'value="admin@example.com"' in r.text
    r = web.post("/account/email", data={"email": "not-an-email", "csrf": web.csrf})
    assert "look right" in r.text
