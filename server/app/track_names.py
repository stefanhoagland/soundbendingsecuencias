"""Standard track names, and turning long stem filenames into them.

"Way Maker_E_68bpm_BASS_48k_24bit.wav" -> "Bajo"
"07 - Electric Gtr 2.wav"             -> "Eléctrica 2"
"""

from __future__ import annotations

import re
import unicodedata

# Canonical names offered in the picker. Numbers are added automatically ("Acústica 2").
BASE_NAMES = [
    # cues
    "Click", "Guía", "Guía (No-Dinámica)", "Nombre De Canción", "Conteo", "Cues", "Canción Original",
    # drums & percussion
    "Batería", "Batería (En Vivo)", "Aux Drums", "Aux Drums (En Vivo)", "Bombo", "Redoblante", "Toms", "Platillos",
    "Overheads", "Hi-Hat", "Room", "Brushes", "Beatbox", "Loop", "Loops", "Drum Loop", "Percusión", "Percusión Electrónica",
    "Pandereta", "Shaker", "Cajón", "Bongo", "Congas", "Timbales", "Güiro", "Maracas", "Claves", "Cencerro", "Cabasa",
    "Djembe", "Tambor", "Taiko", "Timpani", "Bar Chimes", "Campanas", "Campanas Tubulares", "Carillón", "Gong",
    "Hits", "Stomps", "Claps",
    # bass
    "Bajo", "Bajo Sintético", "Sub Bass", "Contrabajo", "808",
    # guitars
    "Acústica", "Acústica 12 Cuerdas", "Eléctrica", "Eléctrica Limpia", "Eléctrica Distorsionada", "Guitarra Lead",
    "Guitarra Ambiente", "Guitarra Swell", "Nylon", "Slide", "Lap Steel", "Pedal Steel", "Dobro", "Banjo", "Mandolina",
    "Ukulele", "Requinto", "Cuatro", "Charango", "Tres",
    # keys & synths
    "Piano", "Piano Eléctrico", "Rhodes", "Wurlitzer", "Teclado", "Teclados", "Órgano", "Hammond", "Armonio", "Clavinet",
    "Celesta", "Sintetizador", "Synth", "Synth Lead", "Synth Pluck", "Synth Bass", "Pad", "Pads", "Pad Ambiente",
    "Arps", "Secuencia", "Drones", "Ambiente", "Atmósfera", "Texturas", "Swells", "Riser", "Reverse", "Sweep", "FX",
    "Efectos", "Impactos", "Transiciones",
    # tuned percussion
    "Glockenspiel", "Vibráfono", "Marimba", "Xilófono", "Steel Drum", "Kalimba", "Music Box",
    # strings
    "Cuerdas", "Cuerdas Altas", "Cuerdas Bajas", "Strings Pad", "Violín", "Violines", "Viola", "Chelo", "Pizzicato",
    "Orquesta", "Arpa",
    # brass & winds
    "Metales", "Trompeta", "Trombón", "Saxofón", "Saxo Alto", "Saxo Tenor", "Saxo Barítono", "Tuba", "Corno Francés",
    "Fliscorno", "Flauta", "Flauta Dulce", "Piccolo", "Clarinete", "Oboe", "Fagot", "Gaita", "Whistle", "Armónica",
    "Acordeón", "Bandoneón", "Melódica",
    # vocals
    "Voz Principal", "Voz Líder", "Voces", "BGVS", "BGVS FX", "Coros", "Coro", "Choir", "Soprano", "Alto", "Tenor",
    "Barítono", "Bajo Vocal", "Unísono", "Armonías", "Voz Hombre", "Voz Mujer", "Vocoder", "Talk Box", "Hablado",
    "Vox FX", "Gang Vox", "Gritos",
    # mixes
    "Mezcla", "Tracks", "Instrumental", "Pista", "Mix Sin Voz",
]

# Names that commonly come in numbered sets, so the picker lists "Acústica 1", "Acústica 2"...
NUMBERED = [
    "Acústica", "Eléctrica", "Teclado", "Synth", "Sintetizador", "Pad", "Arps", "Loop", "Percusión", "BGVS", "Coro",
    "Choir", "Soprano", "Alto", "Tenor", "Bajo", "Batería", "Aux Drums", "Cuerdas", "Violín", "Chelo", "Viola", "Metales",
    "Trompeta", "Saxofón", "Flauta", "Clarinete", "Banjo", "Piano", "Órgano", "FX", "Voz Principal", "Accordion",
    "Acordeón", "Mandolina", "Guitarra Lead", "Swells", "Drones",
]


def picker_names() -> list[str]:
    names = set(BASE_NAMES)
    for n in NUMBERED:
        names.update(f"{n} {i}" for i in (1, 2, 3))
    first = ["Click", "Guía", "Guía (No-Dinámica)", "Nombre De Canción"]
    rest = sorted((n for n in names if n not in first), key=lambda n: _norm(n))
    return first + rest


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# Filename words (English, Spanish and common abbreviations) -> canonical name.
_ALIASES: dict[str, str] = {
    # cues
    "click": "Click", "clic": "Click", "clik": "Click", "clk": "Click", "metronome": "Click", "metronomo": "Click",
    "met": "Click", "tempo": "Click",
    "guide": "Guía", "guia": "Guía", "guides": "Guía", "cue": "Guía", "cues": "Cues", "vocal cues": "Guía",
    "guide cues": "Guía", "guia no dinamica": "Guía (No-Dinámica)", "guide no dynamic": "Guía (No-Dinámica)",
    "guide static": "Guía (No-Dinámica)", "count": "Conteo", "count in": "Conteo", "countin": "Conteo", "conteo": "Conteo",
    "song name": "Nombre De Canción", "nombre de cancion": "Nombre De Canción", "original": "Canción Original",
    "original song": "Canción Original", "reference": "Canción Original", "ref": "Canción Original",
    # drums
    "drums": "Batería", "drum": "Batería", "dr": "Batería", "drms": "Batería", "bateria": "Batería", "kit": "Batería",
    "drum kit": "Batería", "drums live": "Batería (En Vivo)", "live drums": "Batería (En Vivo)",
    "bateria en vivo": "Batería (En Vivo)", "aux drums": "Aux Drums", "aux perc": "Percusión", "aux": "Aux Drums",
    "kick": "Bombo", "bombo": "Bombo", "bd": "Bombo", "snare": "Redoblante", "sn": "Redoblante", "redoblante": "Redoblante",
    "caja": "Redoblante", "toms": "Toms", "tom": "Toms", "cymbals": "Platillos", "platillos": "Platillos",
    "overheads": "Overheads", "oh": "Overheads", "hihat": "Hi-Hat", "hi hat": "Hi-Hat", "hh": "Hi-Hat",
    "brushes": "Brushes", "beatbox": "Beatbox", "loop": "Loop", "loops": "Loops", "drum loop": "Drum Loop",
    "perc": "Percusión", "percussion": "Percusión", "percusion": "Percusión", "electronic perc": "Percusión Electrónica",
    "tamb": "Pandereta", "tambourine": "Pandereta", "pandereta": "Pandereta", "pandero": "Pandereta", "shaker": "Shaker",
    "shakers": "Shaker", "cajon": "Cajón", "bongo": "Bongo", "bongos": "Bongo", "congas": "Congas", "conga": "Congas",
    "timbales": "Timbales", "guiro": "Güiro", "cowbell": "Cencerro", "cencerro": "Cencerro", "timpani": "Timpani",
    "timp": "Timpani", "taiko": "Taiko", "toms taiko": "Taiko", "chimes": "Campanas", "bells": "Campanas",
    "campanas": "Campanas", "bar chimes": "Bar Chimes", "tubular bells": "Campanas Tubulares", "carillon": "Carillón",
    "gong": "Gong", "hits": "Hits", "stomps": "Stomps", "claps": "Claps", "clap": "Claps", "djembe": "Djembe",
    # bass
    "bass": "Bajo", "bajo": "Bajo", "bs": "Bajo", "bass gtr": "Bajo", "bass guitar": "Bajo", "electric bass": "Bajo",
    "synth bass": "Bajo Sintético", "synthbass": "Bajo Sintético", "syn bass": "Bajo Sintético", "sub": "Sub Bass",
    "sub bass": "Sub Bass", "bajo sintetico": "Bajo Sintético", "upright": "Contrabajo", "upright bass": "Contrabajo",
    "double bass": "Contrabajo", "contrabajo": "Contrabajo", "808": "808",
    # guitars
    "ag": "Acústica", "acoustic": "Acústica", "acoustic gtr": "Acústica", "acoustic guitar": "Acústica", "acgtr": "Acústica",
    "ac gtr": "Acústica", "acustica": "Acústica", "guitarra acustica": "Acústica", "12 string": "Acústica 12 Cuerdas",
    "eg": "Eléctrica", "electric": "Eléctrica", "electric gtr": "Eléctrica", "electric guitar": "Eléctrica",
    "elec gtr": "Eléctrica", "egtr": "Eléctrica", "gtr": "Eléctrica", "guitar": "Eléctrica", "guitars": "Eléctrica",
    "electrica": "Eléctrica", "guitarra": "Eléctrica", "guitarra electrica": "Eléctrica", "clean gtr": "Eléctrica Limpia",
    "clean": "Eléctrica Limpia", "dirty gtr": "Eléctrica Distorsionada", "drive": "Eléctrica Distorsionada",
    "lead gtr": "Guitarra Lead", "lead guitar": "Guitarra Lead", "ambient gtr": "Guitarra Ambiente",
    "gtr swell": "Guitarra Swell", "nylon": "Nylon", "classical gtr": "Nylon", "slide": "Slide", "lap steel": "Lap Steel",
    "pedal steel": "Pedal Steel", "steel": "Pedal Steel", "dobro": "Dobro", "banjo": "Banjo", "mandolin": "Mandolina",
    "mandolina": "Mandolina", "mando": "Mandolina", "ukulele": "Ukulele", "uke": "Ukulele", "requinto": "Requinto",
    "cuatro": "Cuatro", "charango": "Charango",
    # keys
    "piano": "Piano", "pno": "Piano", "pn": "Piano", "grand": "Piano", "keys": "Teclado", "key": "Teclado",
    "keyboard": "Teclado", "keyboards": "Teclados", "teclado": "Teclado", "teclados": "Teclados", "rhodes": "Rhodes",
    "ep": "Piano Eléctrico", "electric piano": "Piano Eléctrico", "wurli": "Wurlitzer", "wurlitzer": "Wurlitzer",
    "organ": "Órgano", "organo": "Órgano", "b3": "Hammond", "hammond": "Hammond", "harmonium": "Armonio",
    "armonio": "Armonio", "clav": "Clavinet", "clavinet": "Clavinet", "celesta": "Celesta", "synth": "Synth",
    "synths": "Synth", "syn": "Synth", "sintetizador": "Sintetizador", "sinte": "Sintetizador", "lead synth": "Synth Lead",
    "synth lead": "Synth Lead", "pluck": "Synth Pluck", "plucks": "Synth Pluck", "pad": "Pad", "pads": "Pads",
    "ambient pad": "Pad Ambiente", "pad ambient": "Pad Ambiente", "pad ambiente": "Pad Ambiente", "arp": "Arps", "arps": "Arps", "arpeggio": "Arps", "seq": "Secuencia",
    "sequence": "Secuencia", "secuencia": "Secuencia", "drone": "Drones", "drones": "Drones", "ambient": "Ambiente",
    "ambiente": "Ambiente", "atmos": "Atmósfera", "atmosphere": "Atmósfera", "texture": "Texturas", "textures": "Texturas",
    "swell": "Swells", "swells": "Swells", "riser": "Riser", "risers": "Riser", "reverse": "Reverse", "rev": "Reverse",
    "sweep": "Sweep", "fx": "FX", "sfx": "FX", "efectos": "Efectos", "effects": "Efectos", "impact": "Impactos",
    "impacts": "Impactos", "transitions": "Transiciones",
    # tuned perc
    "glock": "Glockenspiel", "glockenspiel": "Glockenspiel", "vibes": "Vibráfono", "vibraphone": "Vibráfono",
    "marimba": "Marimba", "xylophone": "Xilófono", "steel drum": "Steel Drum", "kalimba": "Kalimba",
    "music box": "Music Box",
    # strings
    "strings": "Cuerdas", "str": "Cuerdas", "strs": "Cuerdas", "cuerdas": "Cuerdas", "high strings": "Cuerdas Altas",
    "low strings": "Cuerdas Bajas", "string pad": "Strings Pad", "violin": "Violín", "violins": "Violines",
    "vln": "Violín", "viola": "Viola", "vla": "Viola", "cello": "Chelo", "cellos": "Chelo", "vc": "Chelo",
    "chelo": "Chelo", "pizz": "Pizzicato", "pizzicato": "Pizzicato", "orchestra": "Orquesta", "orch": "Orquesta",
    "harp": "Arpa", "arpa": "Arpa",
    # brass & winds
    "brass": "Metales", "horns": "Metales", "metales": "Metales", "trumpet": "Trompeta", "tpt": "Trompeta",
    "trompeta": "Trompeta", "trombone": "Trombón", "tbn": "Trombón", "sax": "Saxofón", "saxophone": "Saxofón",
    "alto sax": "Saxo Alto", "tenor sax": "Saxo Tenor", "bari sax": "Saxo Barítono", "tuba": "Tuba",
    "french horn": "Corno Francés", "horn": "Corno Francés", "flugelhorn": "Fliscorno", "flute": "Flauta",
    "flauta": "Flauta", "recorder": "Flauta Dulce", "piccolo": "Piccolo", "clarinet": "Clarinete",
    "clarinete": "Clarinete", "oboe": "Oboe", "bassoon": "Fagot", "bagpipes": "Gaita", "whistle": "Whistle",
    "tin whistle": "Whistle", "harmonica": "Armónica", "armonica": "Armónica", "accordion": "Acordeón",
    "acordeon": "Acordeón", "bandoneon": "Bandoneón", "melodica": "Melódica",
    # vocals
    "lead vocal": "Voz Principal", "lead vox": "Voz Principal", "lead vocals": "Voz Principal", "lv": "Voz Principal",
    "vocal": "Voz Principal", "vocals": "Voces", "vox": "Voz Principal", "voz": "Voz Principal",
    "voz principal": "Voz Principal", "voces": "Voces", "bgv": "BGVS", "bgvs": "BGVS", "bvs": "BGVS", "bv": "BGVS",
    "backing vocals": "BGVS", "backing vox": "BGVS", "bgv fx": "BGVS FX", "bgvs fx": "BGVS FX", "coros": "Coros",
    "coro": "Coro", "choir": "Choir", "soprano": "Soprano", "sop": "Soprano", "alto": "Alto", "tenor": "Tenor",
    "baritone": "Barítono", "bari": "Barítono", "baritono": "Barítono", "unison": "Unísono", "harmony": "Armonías",
    "harmonies": "Armonías", "male vox": "Voz Hombre", "female vox": "Voz Mujer", "vocoder": "Vocoder",
    "talkbox": "Talk Box", "spoken": "Hablado", "gang vox": "Gang Vox", "gang vocals": "Gang Vox", "shouts": "Gritos",
    "vox fx": "Vox FX",
    # mixes
    "mix": "Mezcla", "full mix": "Mezcla", "tracks": "Tracks", "instrumental": "Instrumental", "inst": "Instrumental",
    "minus one": "Mix Sin Voz",
}

# Filename noise: formats, versions, take/bounce words.
_NOISE = re.compile(
    r"\b(\d{2}(\.\d)?\s?k(hz)?|\d{2}\s?bit|\d{2}f|stems?|multitracks?|mt|bounce[d]?|print|final|master|mstr|"
    r"mono|stereo|st|wav|v\d+|ver\d*|version|take\d*|copy|export(ed)?|track|pista|\d{2,3}(\.\d+)?\s?bpm)\b",
    re.I,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4}
_ALIAS_KEYS = sorted(_ALIASES, key=lambda k: -len(k))  # longest match wins ("synth bass" before "bass")


def clean_name(filename: str, song_title: str = "") -> str:
    """Best short name for a stem file."""
    stem = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", filename)
    text = re.sub(r"[_\-.]+", " ", stem)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)            # "ElectricGtr" -> "Electric Gtr"
    norm = _norm(text)
    if song_title:
        t = _norm(song_title)
        if t:
            norm = re.sub(rf"\b{re.escape(t)}\b", " ", norm)
    norm = _NOISE.sub(" ", norm)
    norm = re.sub(r"^\s*\d{1,3}\s+", "", norm)                  # leading track number "07 "
    norm = re.sub(r"\b(in )?[a-g](b|sharp|flat)?m?\s*(major|minor|maj|min)?\b(?=\s*$)", " ", norm) if len(norm.split()) > 1 else norm
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return _fallback(stem)

    # trailing number: "eg 2", "eg2", "bgv 3", "keys two"
    number = None
    m = re.match(r"^(.*?)(?:\s*(\d{1,2})|\s+(one|two|three|four|uno|dos|tres|cuatro))$", norm)
    if m and m.group(1).strip():
        base_part = m.group(1).strip()
        if m.group(2) and base_part in ("808",):
            base_part = norm
        else:
            number = int(m.group(2)) if m.group(2) else _NUMBER_WORDS[m.group(3)]
            norm_wo = base_part
            if norm_wo in _ALIASES:
                return f"{_ALIASES[norm_wo]} {number}"
    if norm in _ALIASES:
        return _ALIASES[norm]
    # no exact match: look for a known word inside ("lead acoustic gtr dry" -> Acústica)
    search_in = f" {norm if number is None else m.group(1).strip()} "
    for key in _ALIAS_KEYS:
        if len(key) <= 2:
            continue  # tiny abbreviations only count when they're the whole name
        if f" {key} " in search_in:
            name = _ALIASES[key]
            return f"{name} {number}" if number else name
    return _fallback(" ".join(w for w in re.split(r"\s+", text) if _norm(w) in norm.split()) or stem)


def _fallback(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -_")
    if not text:
        return "Track"
    return text if any(c.isupper() for c in text[1:]) else text[:1].upper() + text[1:]


def role_for_name(name: str) -> str | None:
    n = _norm(name)
    if n == "click":
        return "click"
    if n.startswith("guia") or n in ("cues", "conteo", "nombre de cancion"):
        return "guide"
    return None
