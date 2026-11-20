import re

from fastapi.testclient import TestClient

from app.models import Song


def csrf_of(client, path="/login"):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def sign_in(app, username, password):
    c = TestClient(app)
    r = c.post("/login", data={"username": username, "password": password, "csrf": csrf_of(c)}, follow_redirects=False)
    assert r.status_code == 303, r.text
    c.csrf = csrf_of(c, "/account")
    return c


def make_song(web, title, wav):
    r = web.post("/songs", data={"title": title, "key": "E", "time_signature": "4/4", "csrf": web.csrf}, follow_redirects=False)
    song_id = int(r.headers["location"].rsplit("/", 1)[1])
    web.post(
        f"/songs/{song_id}/tracks",
        data={"csrf": web.csrf},
        files=[("files", ("Bass.wav", wav(0.2), "audio/wav"))],
        headers={"x-requested-with": "fetch"},
    )
    return song_id


def member_row_id(client, username):
    html = client.get("/c/iglesia-central/members").text
    return re.search(rf"<td>{username}</td>.*?/members/(\d+)/role", html, re.S).group(1)


def setup_church(web, name="Iglesia Central", leader="pastor"):
    r = web.post(
        "/admin/churches",
        data={
            "name": name,
            "leader_username": leader,
            "leader_name": "Pastor",
            "leader_password": "leader-pass-1",
            "csrf": web.csrf,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Added" in web.get("/admin/churches").text


def test_church_user_lands_on_church_page(app, web):
    setup_church(web)
    leader = sign_in(app, "pastor", "leader-pass-1")
    r = leader.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/c/iglesia-central"
    page = leader.get("/c/iglesia-central").text
    assert "Iglesia Central" in page and "Members" in page
    # Can't see another church's page or the admin pages
    setup_church(web, "Otra Iglesia", "otro")
    assert leader.get("/c/otra-iglesia").status_code == 404
    assert leader.get("/admin/churches").status_code == 403


def test_churches_only_see_their_own_songs(app, web, wav):
    setup_church(web)
    setup_church(web, "Otra Iglesia", "otro")
    private_id = make_song(web, "Private Demo", wav)

    leader = sign_in(app, "pastor", "leader-pass-1")
    assert "Private Demo" not in leader.get("/c/iglesia-central").text
    assert leader.get(f"/songs/{private_id}").status_code == 404
    assert leader.post(f"/songs/{private_id}/delete", data={"csrf": leader.csrf}).status_code == 404

    # A leader's upload belongs to the church, not to the admin's library
    own_id = make_song(leader, "Nuestra Canción", wav)
    assert "Nuestra Canción" in leader.get("/c/iglesia-central").text
    assert "Edit details" in leader.get(f"/songs/{own_id}").text
    assert "Nuestra Canción" not in web.get("/").text
    with app.state.session_factory() as db:
        assert db.get(Song, own_id).church_id is not None

    # The other church can't see it
    other = sign_in(app, "otro", "leader-pass-1")
    assert "Nuestra Canción" not in other.get("/c/otra-iglesia").text
    assert other.get(f"/songs/{own_id}").status_code == 404
    track_id = re.search(r"/tracks/(\d+)/audio", leader.get(f"/songs/{own_id}").text).group(1)
    assert other.get(f"/tracks/{track_id}/audio").status_code == 404


def test_members_can_play_but_not_change(app, web, wav):
    setup_church(web)
    leader = sign_in(app, "pastor", "leader-pass-1")
    song_id = make_song(leader, "Santo", wav)
    r = leader.post(
        "/c/iglesia-central/members",
        data={"username": "musico", "display_name": "Músico", "password": "member-pass-1", "role": "member", "csrf": leader.csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    member = sign_in(app, "musico", "member-pass-1")
    lib = member.get("/c/iglesia-central").text
    assert "Santo" in lib and "New song" not in lib and "Members" not in lib
    page = member.get(f"/songs/{song_id}").text
    assert "Edit details" not in page and "tracks-edit" not in page and "chart-form" not in page
    assert member.get("/songs/new").status_code == 403
    assert member.post(f"/songs/{song_id}/chart", data={"chart": "[E]", "csrf": member.csrf}).status_code == 403
    assert member.get("/c/iglesia-central/members").status_code == 404

    # Promote to leader, then they can edit
    member_id = member_row_id(leader, "musico")
    leader.post(f"/c/iglesia-central/members/{member_id}/role", data={"role": "leader", "csrf": leader.csrf})
    assert "Edit details" in member.get(f"/songs/{song_id}").text

    # A leader can't demote themselves
    me_id = member_row_id(leader, "pastor")
    r = leader.post(f"/c/iglesia-central/members/{me_id}/role", data={"role": "member", "csrf": leader.csrf})
    assert "take away your own leader role" in r.text


def test_admin_can_work_inside_a_church(app, web, wav):
    setup_church(web)
    web.get("/c/iglesia-central")
    song_id = make_song(web, "Para la Iglesia", wav)
    assert "Para la Iglesia" in web.get("/c/iglesia-central").text
    assert "Para la Iglesia" not in web.get("/").text  # back in the catalog
    leader = sign_in(app, "pastor", "leader-pass-1")
    assert leader.get(f"/songs/{song_id}").status_code == 200


def test_delete_church_removes_its_people_and_songs(app, web, wav):
    setup_church(web)
    leader = sign_in(app, "pastor", "leader-pass-1")
    song_id = make_song(leader, "Santo", wav)
    mine = make_song(web, "Mine", wav)
    church_id = re.search(r"/admin/churches/(\d+)/delete", web.get("/admin/churches").text).group(1)
    web.post(f"/admin/churches/{church_id}/delete", data={"csrf": web.csrf})
    assert web.get(f"/songs/{song_id}").status_code == 404
    assert web.get(f"/songs/{mine}").status_code == 200
    c = TestClient(app)
    r = c.post("/login", data={"username": "pastor", "password": "leader-pass-1", "csrf": csrf_of(c)})
    assert r.status_code == 401


def test_api_scopes_to_church(app, web, wav):
    setup_church(web)
    make_song(web, "Private Demo", wav)
    leader = sign_in(app, "pastor", "leader-pass-1")
    song_id = make_song(leader, "Santo", wav)
    leader.post(
        "/c/iglesia-central/members",
        data={"username": "musico", "password": "member-pass-1", "role": "member", "csrf": leader.csrf},
    )
    c = TestClient(app)
    token = c.post("/api/auth/token", json={"username": "musico", "password": "member-pass-1", "device_name": "Mac"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    me = c.get("/api/me", headers=h).json()
    assert me["church"]["slug"] == "iglesia-central" and me["church_role"] == "member"
    assert [s["title"] for s in c.get("/api/songs", headers=h).json()["songs"]] == ["Santo"]
    manifest = c.get(f"/api/songs/{song_id}", headers=h).json()
    assert c.get(manifest["tracks"][0]["audio_url"], headers=h).status_code == 200
    assert c.put(f"/api/songs/{song_id}", headers=h, json={"title": "X", "key": "E"}).status_code == 403
    assert c.post("/api/songs", headers=h, json={"title": "X", "key": "E"}).status_code == 403


def test_members_get_a_practice_only_view(app, web, wav):
    setup_church(web)
    leader = sign_in(app, "pastor", "leader-pass-1")
    song_id = make_song(leader, "Santo", wav)
    leader.post(f"/songs/{song_id}/sections", data={"name": "Coro", "start": "0:00.1", "csrf": leader.csrf})
    leader.post(
        "/c/iglesia-central/members",
        data={"username": "musico", "password": "member-pass-1", "role": "member", "csrf": leader.csrf},
    )
    member = sign_in(app, "musico", "member-pass-1")
    lib = member.get("/c/iglesia-central").text
    assert "<h1>Practice</h1>" in lib and "practice-list" in lib and "Santo" in lib
    assert "zip-upload" not in lib
    page = member.get(f"/songs/{song_id}").text
    assert 'id="player"' in page and 'data-panel="chart"' in page
    assert 'id="tracks"' not in page and 'id="sections"' not in page and "download" not in page
    assert 'class="chip" data-time' in page and "Coro" in page
    # Leaders still get the full page
    full = leader.get(f"/songs/{song_id}").text
    assert 'id="tracks"' in full and "practice-list" not in leader.get("/c/iglesia-central").text


def test_setlists_leaders_build_and_share(app, web, wav):
    setup_church(web)
    leader = sign_in(app, "pastor", "leader-pass-1")
    a = make_song(leader, "Santo", wav)
    b = make_song(leader, "Digno", wav)
    leader.post(
        "/c/iglesia-central/members",
        data={"username": "musico", "password": "member-pass-1", "role": "member", "csrf": leader.csrf},
    )
    member = sign_in(app, "musico", "member-pass-1")
    assert member.get("/c/iglesia-central/setlists").status_code == 404

    r = leader.post("/c/iglesia-central/setlists", data={"name": "Domingo", "service_date": "2099-01-04", "csrf": leader.csrf}, follow_redirects=False)
    sl = int(r.headers["location"].rsplit("/", 1)[1])
    data = {"name": "Domingo", "service_date": "2099-01-04", "notes": "Llegar 8:30", "song": [str(b), str(a)], "csrf": leader.csrf}
    leader.post(f"/setlists/{sl}", data=data)

    # Draft: members can't see it
    assert "Domingo" not in member.get("/c/iglesia-central").text
    assert member.get(f"/setlists/{sl}").status_code == 404

    leader.post(f"/setlists/{sl}", data={**data, "shared": "on"})
    practice = member.get("/c/iglesia-central").text
    assert "Next up" in practice and "Domingo" in practice
    page = member.get(f"/setlists/{sl}").text
    assert page.index("Digno") < page.index("Santo") and "Llegar 8:30" in page and "add-song" not in page
    assert member.post(f"/setlists/{sl}", data={**data, "song": [str(a)], "csrf": member.csrf}).status_code == 403

    song = member.get(f"/songs/{b}?setlist={sl}").text
    assert "1 of 2" in song and f"/songs/{a}?setlist={sl}" in song

    # Other churches' songs can't be added
    setup_church(web, "Otra Iglesia", "otro")
    other = sign_in(app, "otro", "leader-pass-1")
    foreign = make_song(other, "Ajena", wav)
    r = leader.post(f"/setlists/{sl}", data={**data, "song": [str(foreign)]})
    assert "isn" in r.text  # "isn't in this church's library"

    # API
    c = TestClient(app)
    token = c.post("/api/auth/token", json={"username": "musico", "password": "member-pass-1", "device_name": "Mac"}).json()["token"]
    lists = c.get("/api/setlists", headers={"Authorization": f"Bearer {token}"}).json()["setlists"]
    assert [s["title"] for s in lists[0]["songs"]] == ["Digno", "Santo"]

    # Deleting a song drops it from the setlist
    leader.post(f"/songs/{b}/delete", data={"csrf": leader.csrf})
    assert "Digno" not in member.get(f"/setlists/{sl}").text


def test_super_admin_lands_on_churches(app, client, web):
    setup_church(web)
    c = TestClient(app)
    r = c.post("/login", data={"username": "admin", "password": "admin-pass-123", "csrf": csrf_of(c)}, follow_redirects=False)
    assert r.headers["location"] == "/admin/churches"
    page = c.get("/admin/churches").text
    assert "Super admin" in page and "Pastor" in page  # leaders listed
    leader = TestClient(app)
    r = leader.post("/login", data={"username": "pastor", "password": "leader-pass-1", "csrf": csrf_of(leader)}, follow_redirects=False)
    assert r.headers["location"] == "/"
    assert "Super admin" not in leader.get("/c/iglesia-central").text


def test_super_admin_copies_and_moves_songs(app, web, wav):
    import os

    setup_church(web)
    setup_church(web, "Otra Iglesia", "otro")
    leader = sign_in(app, "pastor", "leader-pass-1")
    other = sign_in(app, "otro", "leader-pass-1")
    song_id = make_song(leader, "Santo", wav)
    leader.post(f"/songs/{song_id}/sections", data={"name": "Coro", "start": "0:00.1", "csrf": leader.csrf})
    r = leader.post("/c/iglesia-central/setlists", data={"name": "Domingo", "csrf": leader.csrf}, follow_redirects=False)
    sl = int(r.headers["location"].rsplit("/", 1)[1])
    leader.post(f"/setlists/{sl}", data={"name": "Domingo", "service_date": "", "song": [str(song_id)], "shared": "on", "csrf": leader.csrf})

    page = web.get(f"/songs/{song_id}").text
    assert "Send to church" in page
    assert "Send to church" not in leader.get(f"/songs/{song_id}").text
    assert leader.post(f"/songs/{song_id}/transfer", data={"target": "", "csrf": leader.csrf}).status_code == 403
    other_id = re.search(r'<option value="(\d+)">Otra Iglesia</option>', page).group(1)

    # Copy: both churches have it, with its own audio and sections
    r = web.post(f"/songs/{song_id}/transfer", data={"target": other_id, "mode": "copy", "csrf": web.csrf}, follow_redirects=False)
    copy_id = int(r.headers["location"].rsplit("/", 1)[1])
    assert copy_id != song_id
    assert "Santo" in other.get("/c/otra-iglesia").text and "Santo" in leader.get("/c/iglesia-central").text
    copy_page = other.get(f"/songs/{copy_id}").text
    assert "Coro" in copy_page
    track_id = re.search(r"/tracks/(\d+)/audio", copy_page).group(1)
    assert other.get(f"/tracks/{track_id}/audio").status_code == 200
    # Deleting the original leaves the copy's audio intact
    leader.post(f"/songs/{song_id}/delete", data={"csrf": leader.csrf})
    assert other.get(f"/tracks/{track_id}/audio").status_code == 200

    # Move: the copy goes to the super admin's library and out of the church
    web.post(f"/songs/{copy_id}/transfer", data={"target": "", "mode": "move", "csrf": web.csrf})
    assert other.get(f"/songs/{copy_id}").status_code == 404
    assert "Santo" in web.get("/").text
