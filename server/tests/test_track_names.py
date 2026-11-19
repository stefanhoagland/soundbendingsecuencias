import pytest

from app.track_names import clean_name, picker_names


@pytest.mark.parametrize(
    "filename,title,expected",
    [
        ("Way Maker_E_68bpm_BASS_48k_24bit.wav", "Way Maker", "Bajo"),
        ("07 - Electric Gtr 2.wav", "", "Eléctrica 2"),
        ("WayMaker_AG.wav", "Way Maker", "Acústica"),
        ("Goodness of God - Click.wav", "Goodness of God", "Click"),
        ("Goodness of God - Guide.wav", "Goodness of God", "Guía"),
        ("01 Drums.wav", "", "Batería"),
        ("Synth Bass.wav", "", "Bajo Sintético"),
        ("BGV 3.wav", "", "BGVS 3"),
        ("Keys two.wav", "", "Teclado 2"),
        ("EG1.wav", "", "Eléctrica 1"),
        ("Lead Vox.wav", "", "Voz Principal"),
        ("Pad_Ambient.wav", "", "Pad Ambiente"),
        ("Gratitude_Bb_Piano_44.1k.wav", "Gratitude", "Piano"),
        ("Guia No Dinamica.wav", "", "Guía (No-Dinámica)"),
        ("Random Thing Stereo.wav", "", "Random Thing"),
        ("808.wav", "", "808"),
    ],
)
def test_clean_name(filename, title, expected):
    assert clean_name(filename, title) == expected


def test_picker_has_the_basics_first():
    names = picker_names()
    assert names[:2] == ["Click", "Guía"]
    assert len(names) > 250 and len(set(names)) == len(names)
