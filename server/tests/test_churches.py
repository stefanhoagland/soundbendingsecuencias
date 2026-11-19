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
