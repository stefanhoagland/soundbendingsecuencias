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


def test_chart_and_transpose(web):
    song_id = _new_song(web)
    chart = "[Chorus]\r\nWay[E]maker, [B]miracle worker\r\n"
    r = web.post(f"/songs/{song_id}/chart", data={"chart": chart, "csrf": web.csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("?tab=chart")
    r = web.post(
        f"/songs/{song_id}/transpose",
        data={"semitones": "-2"},
        headers={"X-CSRF-Token": web.csrf, "X-Requested-With": "fetch"},
    )
    assert r.json() == {"transpose": -2, "play_key": "D"}
    page = web.get(f"/songs/{song_id}?tab=chart").text
    assert '"[Chorus]\\nWay[E]maker, [B]miracle worker"' in page  # chart stored without CRs
    assert '<option value="-2" selected>D (-2)</option>' in page
    bad = web.post(
        f"/songs/{song_id}/transpose",
        data={"semitones": "20"},
        headers={"X-CSRF-Token": web.csrf, "X-Requested-With": "fetch"},
    )
    assert bad.status_code == 422


def test_old_database_gets_new_columns(tmp_path, monkeypatch):
    import sqlite3

    from app.config import load_settings
    from app.main import create_app

    data = tmp_path / "old"
    settings = load_settings(data)
    con = sqlite3.connect(settings.db_path)
    con.execute("CREATE TABLE songs (id INTEGER PRIMARY KEY, owner_id INTEGER, title VARCHAR(255), artist VARCHAR(255),"
                " bpm FLOAT, key VARCHAR(16), time_signature VARCHAR(8), notes TEXT, created_at DATETIME, updated_at DATETIME)")
    con.commit()
    con.close()
    monkeypatch.setenv("SBS_ADMIN_PASSWORD", "admin-pass-123")
    create_app(settings)
    cols = {row[1] for row in sqlite3.connect(settings.db_path).execute("PRAGMA table_info(songs)")}
    assert {"chart", "transpose"} <= cols


def _zip(entries):
    import io as _io
    import zipfile

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def test_zip_upload_to_song(web, wav):
    song_id = _new_song(web)
    data = _zip([
        ("Way Maker/10 Pad.wav", wav(1)),
        ("Way Maker/2 Click.wav", wav(1)),
        ("Way Maker/1 Drums.wav", wav(2)),
        ("__MACOSX/Way Maker/._1 Drums.wav", b"junk"),
        ("Way Maker/readme.txt", b"hi"),
        ("Way Maker/broken.wav", b"nope nope nope"),
    ])
    r = web.post(
        f"/songs/{song_id}/tracks",
        headers={"X-CSRF-Token": web.csrf, "X-Requested-With": "fetch"},
        files=[("files", ("stems.zip", data, "application/zip"))],
    )
    assert r.status_code == 200
    assert len(r.json()["created"]) == 3
    assert r.json()["errors"] == ["broken.wav: Not a WAV file (missing RIFF/WAVE header)"]
    page = web.get(f"/songs/{song_id}").text
    # natural order: 1, 2, 10
    assert page.index('value="Batería"') < page.index('value="Click"') < page.index('value="Pad"')
    assert "role-click" in page


def test_new_song_from_zip(web, wav):
    data = _zip([("Bass.wav", wav(1)), ("Keys.wav", wav(1))])
    r = web.post(
        "/songs/from-zip",
        headers={"X-CSRF-Token": web.csrf, "X-Requested-With": "fetch"},
        files=[("files", ("Way Maker - E - 68bpm.zip", data, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    song = r.json()["songs"][0]
    assert song["title"] == "Way Maker"
    page = web.get(song["url"]).text
    assert "68 BPM" in page and 'value="Bajo"' in page and 'value="Teclado"' in page
    assert "E (original)" in page


def test_zip_without_wavs_creates_nothing(web):
    r = web.post(
        "/songs/from-zip",
        headers={"X-CSRF-Token": web.csrf, "X-Requested-With": "fetch"},
        files=[("files", ("Empty.zip", _zip([("notes.txt", b"x")]), "application/zip"))],
    )
    assert r.status_code == 422
    assert "no WAV files" in r.json()["errors"][0]
    assert "Empty" not in web.get("/").text.split("<table")[-1]


def test_song_fields_from_filename():
    from app.services import song_fields_from_filename as f

    assert f("Way Maker - E - 68bpm.zip") == {"title": "Way Maker", "bpm": 68.0, "key": "E"}
    assert f("Goodness_of_God_Ab_63BPM.zip") == {"title": "Goodness of God", "bpm": 63.0, "key": "Ab"}
    assert f("Gratitude - Key of Bb - 72 BPM.zip") == {"title": "Gratitude", "bpm": 72.0, "key": "Bb"}
    assert f("Plan A.zip") == {"title": "Plan A", "bpm": None, "key": ""}


def test_save_all_tracks_at_once(web, wav, app):
    song_id = _new_song(web)
    web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[wav_file("Drums.wav", wav(1)), wav_file("Bass.wav", wav(1)), wav_file("Keys.wav", wav(1))],
    )
    page = web.get(f"/songs/{song_id}").text
    assert "<fieldset id=\"tracks-fields\" disabled>" in page  # locked by default
    d, b, k = [int(i) for i in re.findall(r'id="track-(\d+)"', page)]
    form = {
        "csrf": web.csrf,
        "order": [str(k), str(d), str(b)],
        f"name-{k}": "Rhodes", f"role-{k}": "stem", f"gain-{k}": "-2", f"pan-{k}": "0",
        f"name-{d}": "Drums", f"role-{d}": "stem", f"gain-{d}": "0", f"pan-{d}": "0", f"muted-{d}": "on",
        f"name-{b}": "Bass", f"role-{b}": "stem", f"gain-{b}": "0", f"pan-{b}": "0", f"delete-{b}": "on",
    }
    r = web.post(f"/songs/{song_id}/tracks/save", data=form, follow_redirects=False)
    assert r.status_code == 303
    page = web.get(f"/songs/{song_id}").text
    assert re.findall(r'id="track-(\d+)"', page) == [str(k), str(d)]
    assert 'value="Rhodes"' in page and "Removed 1" in page
    assert len(list((app.state.settings.library_dir / str(song_id)).glob("*.wav"))) == 2

    # a bad value saves nothing
    bad = dict(form, **{f"gain-{k}": "loud", f"name-{d}": "Changed"})
    bad.pop(f"delete-{b}")
    bad["order"] = [str(k), str(d)]
    web.post(f"/songs/{song_id}/tracks/save", data=bad)
    page = web.get(f"/songs/{song_id}").text
    assert 'value="Changed"' not in page


def test_track_names_cleaned_on_upload_and_picker(web, wav):
    song_id = _new_song(web, title="Way Maker")
    web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[
            wav_file("Way Maker_E_68bpm_BASS_48k_24bit.wav", wav(1)),
            wav_file("07 - Electric Gtr 2.wav", wav(1)),
            wav_file("WayMaker_Guia.wav", wav(1)),
            wav_file("My Weird Thing.wav", wav(1)),
        ],
    )
    page = web.get(f"/songs/{song_id}").text
    for name in ("Bajo", "Eléctrica 2", "Guía", "My Weird Thing"):
        assert f'value="{name}"' in page, name
    assert re.search(r'class="track role-guide"[^>]*data-suggest="Guía"', page)
    # picker offers standard names and remembers custom ones
    datalist = page.split('<datalist id="track-names">')[1].split("</datalist>")[0]
    for n in ("Click", "Acústica 2", "Bajo Sintético", "Armónica", "My Weird Thing"):
        assert f'<option value="{n}">' in datalist, n
