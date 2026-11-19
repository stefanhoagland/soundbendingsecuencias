import io

import pytest

from app.audio import InvalidWav, guess_role, read_wav_info


def test_reads_pcm_24bit_stereo(wav):
    info = read_wav_info(io.BytesIO(wav(seconds=2, rate=48000, channels=2, bits=24)))
    assert (info.sample_rate, info.channels, info.bit_depth, info.sample_format) == (48000, 2, 24, "pcm")
    assert info.duration_seconds == pytest.approx(2.0)


def test_reads_float_extensible(wav):
    info = read_wav_info(io.BytesIO(wav(seconds=0.5, rate=44100, channels=1, bits=32, fmt_tag=3, extensible=True)))
    assert info.sample_format == "float"
    assert info.bit_depth == 32
    assert info.duration_seconds == pytest.approx(0.5, abs=1e-4)


def test_rejects_non_wav():
    with pytest.raises(InvalidWav):
        read_wav_info(io.BytesIO(b"ID3\x04" + b"\x00" * 100))


def test_rejects_compressed(wav):
    with pytest.raises(InvalidWav, match="Unsupported"):
        read_wav_info(io.BytesIO(wav(fmt_tag=0x55, bits=16)))


@pytest.mark.parametrize(
    "name,role",
    [("Click.wav", "click"), ("01_click_track.wav", "click"), ("Guide.wav", "guide"), ("Cues.wav", "guide"),
     ("Bass.wav", "stem"), ("Clicky Synth.wav", "stem")],
)
def test_guess_role(name, role):
    assert guess_role(name) == role
