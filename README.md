# Soundbending Secuencias

A private, self-hosted home for your multitracks, plus (coming next) a Mac app that downloads a song's session and plays it live.

| Part | Status |
| --- | --- |
| **Library server** (`server/`): upload WAV stems, organize songs, add sections, preview in the browser | ✅ Step 1 |
| **Session packages and setlists**: download a song or a whole set in one go | Step 2 |
| **Mac playback app**: offline sessions, mixer, click/guide routing, section jumps and loops | Step 3 |
| **Advanced playback**: tempo and key change, MIDI cues and lighting, setlist auto-advance | Step 4 |

## What the server does

- Sign in with your own account. Admins can add more people, and each person gets a private library.
- Create a song with title, artist, BPM, key, time signature and notes.
- **Drop a ZIP of stems on the library page to create a song in one go.** Name it like `Way Maker - E - 68bpm.zip` and the title, key and BPM are filled in. ZIPs can also be dropped on an existing song. Folders inside the ZIP and macOS `__MACOSX` junk are ignored, and tracks are ordered by filename (1, 2, 10).
- Drag in WAV stems (16/24/32-bit, PCM or float, any sample rate, mono or stereo). Files named *click* or *guide* / *cues* are tagged automatically.
- Set each track's default name, role, gain, pan and mute. The Mac app will start from these.
- Add section markers (Intro, Verse 1, Chorus…) by typing a time or grabbing the preview player's position.
- **Change key**: pick a new key from the song header and the chord chart and preview audio shift with it (click and guide tracks stay untouched). The choice is saved with the song and included in what the Mac app downloads.
- **Chord chart tab**: paste or type a chart with chords above the lyrics or inline ChordPro (`Way[E]maker`), with section headings, a live preview while editing, text size, and print.
- Preview the multitrack in the browser with per-track faders, mute and solo, and jump to sections.
- JSON API for the Mac app at `/api` (interactive docs at `/api/docs`).

All data lives in one folder (`/data` in the container): the SQLite database `library.db` and the audio under `library/<song id>/`. Back up that folder and you've backed up everything.

## Install on Unraid

### Option A: Docker template (recommended)

Every push to `main` publishes the image `ghcr.io/stefanhoagland/soundbending-secuencias:latest`.

1. Copy `unraid/soundbending-secuencias.xml` to your flash drive at `/boot/config/plugins/dockerMan/templates-user/` (for example with the Unraid terminal: `wget -O /boot/config/plugins/dockerMan/templates-user/my-soundbending-secuencias.xml https://raw.githubusercontent.com/stefanhoagland/soundbendingsecuencias/main/unraid/soundbending-secuencias.xml`).
2. In the Unraid web UI go to **Docker → Add Container**, pick **soundbending-secuencias** from the template list.
3. Set **Library data** to a share with room for your audio (WAV stems add up fast: a 5-minute song with 12 stereo 24-bit stems is about 1 GB). `/mnt/user/appdata/soundbending-secuencias` is the default; something like `/mnt/user/multitracks` works too.
4. Set an **Admin password**, then **Apply**.
5. Open `http://<unraid-ip>:8080` and sign in as `admin`.

If you leave the admin password blank, one is generated and printed once in the container's log (Docker tab → container icon → Logs).

> If Unraid says it can't pull the image, open the package on GitHub (your profile → Packages → soundbending-secuencias → Package settings) and set its visibility to Public.

### Option B: build it yourself with Docker Compose

With the *Docker Compose Manager* plugin, or from any machine with Docker:

```sh
git clone https://github.com/stefanhoagland/soundbendingsecuencias
cd soundbendingsecuencias
# edit SBS_ADMIN_PASSWORD in docker-compose.yml first
docker compose up -d --build
```

### Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `SBS_DATA_DIR` | `/data` | Where the database and audio are stored |
| `SBS_ADMIN_USERNAME` | `admin` | First account, created only when there are no users yet |
| `SBS_ADMIN_PASSWORD` | *(generated)* | Password for that first account |
| `SBS_SECRET_KEY` | *(generated, saved in the data folder)* | Signs login cookies |
| `SBS_SESSION_DAYS` | `30` | How long you stay signed in |
| `PORT` | `8080` | Port inside the container |

The container runs as Unraid's `nobody:users` (99:100), so files it writes are owned the same way as the rest of your shares.

### Reaching it away from home

Right now it's meant for your home network. Later, the easiest safe way to reach it from church or gigs is Tailscale (there's an Unraid plugin) rather than opening a port on your router. If you do put it on the internet, put it behind HTTPS (for example Nginx Proxy Manager or SWAG).

## Development

```sh
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/*.test.js   # chord chart parser
SBS_DATA_DIR=./data SBS_ADMIN_PASSWORD=devpassword uvicorn app.main:create_app --factory --reload --port 8080
```

Stack: Python 3.13, FastAPI, SQLAlchemy with SQLite, server-rendered Jinja pages with a little vanilla JS. No build step.

### API quick look

```sh
TOKEN=$(curl -s -X POST localhost:8080/api/auth/token -H 'content-type: application/json' \
  -d '{"username":"admin","password":"…","device_name":"MacBook"}' | jq -r .token)
curl -s localhost:8080/api/songs -H "Authorization: Bearer $TOKEN"
curl -s localhost:8080/api/songs/1 -H "Authorization: Bearer $TOKEN"   # full session manifest
```

`GET /api/songs/{id}` returns the song's manifest: metadata, sections, and every track with its audio format, SHA-256, mix defaults and an `audio_url` to download it. The Mac app will be built against this.
