import re

from app.storage import preview_path
from tests.conftest import make_wav, wav_file


def _song_with_stems(web, n=2):
    r = web.post("/songs", data={"title": "Preview Song", "bpm": "70", "key": "E", "time_signature": "4/4", "csrf": web.csrf}, follow_redirects=False)
    song_id = int(re.search(r"/songs/(\d+)", r.headers["location"]).group(1))
    files = [wav_file(f"Stem {i}.wav", make_wav(seconds=0.5, channels=1 + i % 2)) for i in range(n)]
    r = web.post(f"/songs/{song_id}/tracks", data={"csrf": web.csrf}, files=files, follow_redirects=False)
    assert r.status_code in (302, 303)
    return song_id


def test_upload_makes_small_previews_and_player_uses_them(web, app):
    song_id = _song_with_stems(web)
    lib = app.state.settings.library_dir
    from app.models import Song

    with app.state.session_factory() as db:
        tracks = db.get(Song, song_id).tracks
        paths = [preview_path(lib, song_id, t.stored_filename) for t in tracks]
        ids = [t.id for t in tracks]
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
    page = web.get(f"/songs/{song_id}").text
    assert f'data-src="/tracks/{ids[0]}/preview"' in page
    r = web.get(f"/tracks/{ids[0]}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mp4"
    # downloads still give the original WAV
    r = web.get(f"/tracks/{ids[0]}/audio")
    assert r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"


def test_missing_previews_fall_back_to_wav_and_get_backfilled(web, app):
    song_id = _song_with_stems(web)
    lib = app.state.settings.library_dir
    from app.models import Song

    with app.state.session_factory() as db:
        tracks = db.get(Song, song_id).tracks
        first = tracks[0]
        preview_path(lib, song_id, first.stored_filename).unlink()
        tid = first.id
    page = web.get(f"/songs/{song_id}").text
    assert f'data-src="/tracks/{tid}/audio"' in page  # not all ready: use WAVs for every stem
    assert web.get(f"/tracks/{tid}/preview").headers["content-type"] == "audio/wav"
    assert app.state.previews.make_missing() == 1
    assert f'data-src="/tracks/{tid}/preview"' in web.get(f"/songs/{song_id}").text


def test_deleting_a_track_removes_its_preview(web, app):
    song_id = _song_with_stems(web, n=1)
    lib = app.state.settings.library_dir
    from app.models import Song

    with app.state.session_factory() as db:
        t = db.get(Song, song_id).tracks[0]
        p, tid = preview_path(lib, song_id, t.stored_filename), t.id
    assert p.exists()
    web.post(f"/tracks/{tid}/delete", data={"csrf": web.csrf})
    assert not p.exists()
