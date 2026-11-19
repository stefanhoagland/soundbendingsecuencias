from tests.conftest import wav_file


def test_token_login_and_me(api):
    r = api.get("/api/me")
    assert r.status_code == 200 and r.json()["username"] == "admin"


def test_bad_token(client):
    r = client.get("/api/songs", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_song_manifest_round_trip(api, wav):
    r = api.post("/api/songs", json={"title": "Goodness of God", "bpm": 63, "key": "Ab"})
    assert r.status_code == 201, r.text
    song_id = r.json()["id"]

    r = api.post(f"/api/songs/{song_id}/tracks", files=[wav_file("Guide.wav", wav(2)), wav_file("AG.wav", wav(2))])
    assert r.status_code == 201, r.text
    tracks = r.json()["tracks"]
    assert [t["role"] for t in tracks] == ["guide", "stem"]

    api.post(f"/api/songs/{song_id}/sections", json={"name": "Verse 1", "start_seconds": 12.5})
    api.patch(f"/api/tracks/{tracks[1]['id']}", json={"gain_db": -4.5, "pan": -0.3})

    m = api.get(f"/api/songs/{song_id}").json()
    assert m["manifest_version"] == 1
    assert m["bpm"] == 63 and m["key"] == "Ab"
    assert m["transpose"] == 0 and m["play_key"] == "Ab" and m["chart"] == ""
    assert m["duration_seconds"] == 2.0
    assert m["sections"] == [{"id": m["sections"][0]["id"], "name": "Verse 1", "start_seconds": 12.5, "color": ""}]
    ag = m["tracks"][1]
    assert ag["gain_db"] == -4.5 and ag["pan"] == -0.3
    assert len(ag["sha256"]) == 64

    audio = api.get(ag["audio_url"])
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"

    assert [s["title"] for s in api.get("/api/songs").json()["songs"]] == ["Goodness of God"]
    assert api.delete(f"/api/songs/{song_id}").status_code == 204
    assert api.get(f"/api/songs/{song_id}").status_code == 404


def test_api_validation(api):
    r = api.post("/api/songs", json={"title": "X", "bpm": 1000})
    assert r.status_code == 422
    assert "BPM" in r.json()["detail"]


def test_timestamp_parsing():
    from app.services import format_timestamp, parse_timestamp

    assert parse_timestamp("1:23.5") == 83.5
    assert parse_timestamp("83.5") == 83.5
    assert parse_timestamp("1:00:00") == 3600
    assert format_timestamp(83.5) == "1:23.5"
    assert format_timestamp(65) == "1:05"
    assert format_timestamp(3725) == "1:02:05"


def test_api_chart_and_transpose(api):
    song_id = api.post("/api/songs", json={"title": "Firm Foundation", "key": "B"}).json()["id"]
    r = api.put(f"/api/songs/{song_id}", json={"title": "Firm Foundation", "key": "B", "transpose": 1, "chart": "[B]Christ is my"})
    assert r.status_code == 200, r.text
    assert r.json()["play_key"] == "C" and r.json()["chart"] == "[B]Christ is my"
    assert api.put(f"/api/songs/{song_id}", json={"title": "x", "transpose": 99}).status_code == 422
