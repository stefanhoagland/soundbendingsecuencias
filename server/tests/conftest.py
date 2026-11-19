import io
import struct

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app


def make_wav(seconds=1.0, rate=48000, channels=2, bits=24, fmt_tag=1, extensible=False, extra_chunk=True) -> bytes:
    frames = int(seconds * rate)
    block = channels * bits // 8
    data = b"\x00" * frames * block
    if extensible:
        fmt = struct.pack("<HHIIHH", 0xFFFE, channels, rate, rate * block, block, bits)
        fmt += struct.pack("<HHI", 22, bits, 3) + struct.pack("<H", fmt_tag) + b"\x00" * 14
    else:
        fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * block, block, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if extra_chunk:
        bext = b"x" * 7  # odd size to exercise pad byte handling
        chunks += b"bext" + struct.pack("<I", len(bext)) + bext + b"\x00"
    chunks += b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


@pytest.fixture
def wav():
    return make_wav


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SBS_ADMIN_PASSWORD", "admin-pass-123")
    monkeypatch.delenv("SBS_SECRET_KEY", raising=False)
    return create_app(load_settings(tmp_path / "data"))


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def web(client):
    """A browser-like client already signed in as admin."""
    import re

    html = client.get("/login").text
    token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    r = client.post("/login", data={"username": "admin", "password": "admin-pass-123", "csrf": token}, follow_redirects=False)
    assert r.status_code == 303
    client.csrf = re.search(r'name="csrf" value="([^"]+)"', client.get("/").text).group(1)
    return client


@pytest.fixture
def api(client):
    r = client.post("/api/auth/token", json={"username": "admin", "password": "admin-pass-123"})
    assert r.status_code == 200
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


def wav_file(name, data):
    return ("files", (name, io.BytesIO(data), "audio/wav"))
