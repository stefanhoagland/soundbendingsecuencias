import re

from tests.conftest import wav_file


def _new_song(web, **fields):
    data = {"title": "Way Maker", "artist": "Sinach", "bpm": "68", "key": "E", "time_signature": "4/4", "csrf": web.csrf}
    data.update(fields)
    r = web.post("/songs", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(re.search(r"/songs/(\d+)", r.headers["location"]).group(1))


def test_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_wrong_password(client):
    html = client.get("/login").text
    token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    r = client.post("/login", data={"username": "admin", "password": "nope", "csrf": token})
    assert r.status_code == 401
    assert "Wrong username or password" in r.text


def test_csrf_required(web):
    r = web.post("/songs", data={"title": "X"})
    assert r.status_code == 400


def test_create_song_upload_and_view(web, wav, app):
    song_id = _new_song(web)
    r = web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[wav_file("Click.wav", wav(1)), wav_file("Bass.wav", wav(3)), wav_file("notes.txt", b"hello")],
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = web.get(f"/songs/{song_id}").text
    assert "Way Maker" in page and "Click" in page and "Bass" in page
    assert "role-click" in page
    assert "0:03" in page  # song length comes from the longest stem
    stored = list((app.state.settings.library_dir / str(song_id)).glob("*.wav"))
    assert len(stored) == 2
    assert not list((app.state.settings.library_dir / str(song_id)).glob("*.part"))


def test_fetch_upload_reports_errors(web):
    song_id = _new_song(web)
    r = web.post(
        f"/songs/{song_id}/tracks",
        headers={"X-CSRF-Token": web.csrf, "X-Requested-With": "fetch"},
        files=[wav_file("bad.wav", b"ID3 this is an mp3 really")],
    )
    assert r.status_code == 422
    assert "Not a WAV file" in r.json()["errors"][0]


def test_validation_error_rerenders_form(web):
    r = web.post("/songs", data={"title": "", "csrf": web.csrf})
    assert r.status_code == 422
    assert "Title is required" in r.text


def test_sections_and_delete_song(web, wav, app):
    song_id = _new_song(web)
    web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=[wav_file("Keys.wav", wav(1))])
    web.post(f"/songs/{song_id}/sections", data={"name": "Chorus", "start": "1:05.5", "csrf": web.csrf})
    web.post(f"/songs/{song_id}/sections", data={"name": "Intro", "start": "0", "csrf": web.csrf})
    page = web.get(f"/songs/{song_id}").text
    assert page.index("Intro") < page.index("Chorus")
    assert "1:05.5" in page
    r = web.post(f"/songs/{song_id}/delete", data={"csrf": web.csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert not (app.state.settings.library_dir / str(song_id)).exists()
    assert web.get(f"/songs/{song_id}").status_code == 404


def test_users_are_isolated(web, wav):
    song_id = _new_song(web, title="Private song")
    r = web.post("/admin/users", data={"username": "Maria", "password": "maria-pass-1", "csrf": web.csrf}, follow_redirects=False)
    assert r.status_code == 303
    web.post("/logout", data={"csrf": web.csrf})
    html = web.get("/login").text
    token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    web.post("/login", data={"username": "maria", "password": "maria-pass-1", "csrf": token})
    assert "Private song" not in web.get("/").text
    assert web.get(f"/songs/{song_id}").status_code == 404
    assert web.get("/admin/users").status_code == 403


def test_track_edit_and_reorder(web, wav):
    song_id = _new_song(web)
    web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[wav_file("Drums.wav", wav(1)), wav_file("Bass.wav", wav(1))],
    )
    ids = [int(i) for i in re.findall(r'id="track-(\d+)"', web.get(f"/songs/{song_id}").text)]
    web.post(f"/tracks/{ids[1]}/move", data={"direction": "-1", "csrf": web.csrf})
    web.post(
        f"/tracks/{ids[0]}",
        data={"name": "Kit", "role": "stem", "gain_db": "-3", "pan": "0.2", "muted": "on", "csrf": web.csrf},
    )
    page = web.get(f"/songs/{song_id}").text
    assert page.index('id="track-%d"' % ids[1]) < page.index('id="track-%d"' % ids[0])
    assert 'value="Kit"' in page


def test_range_request_for_audio(web, wav):
    song_id = _new_song(web)
    web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=[wav_file("Pad.wav", wav(1))])
    track_id = re.search(r'id="track-(\d+)"', web.get(f"/songs/{song_id}").text).group(1)
    r = web.get(f"/tracks/{track_id}/audio", headers={"Range": "bytes=0-11"})
    assert r.status_code == 206
    assert r.content == b"RIFF" + r.content[4:8] + b"WAVE"
