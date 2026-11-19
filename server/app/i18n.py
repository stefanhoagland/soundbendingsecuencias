"""English / Mexican Spanish.

Pages wrap their text in ``_("English text")``. Messages built in Python (flash
notices, form errors) stay in English in the code and are translated when shown,
using the exact table first and then the patterns for messages with names or
numbers in them.
"""

from __future__ import annotations

import re

LANGS = ("en", "es")

ES: dict[str, str] = {
    # ---- navigation & common -------------------------------------------------
    "Library": "Biblioteca",
    "My library": "Mi biblioteca",
    "Churches": "Iglesias",
    "Users": "Usuarios",
    "Members": "Miembros",
    "Setlists": "Setlists",
    "Practice": "Ensayo",
    "Sign out": "Cerrar sesión",
    "Sign in": "Iniciar sesión",
    "Username": "Usuario",
    "Password": "Contraseña",
    "Name": "Nombre",
    "Role": "Rol",
    "Church": "Iglesia",
    "Songs": "Canciones",
    "Song": "Canción",
    "Title": "Título",
    "Artist": "Artista",
    "Key": "Tono",
    "BPM": "BPM",
    "Length": "Duración",
    "Tracks": "Pistas",
    "Size": "Tamaño",
    "Date": "Fecha",
    "Notes": "Notas",
    "Save": "Guardar",
    "Cancel": "Cancelar",
    "Delete": "Eliminar",
    "Remove": "Quitar",
    "Add": "Agregar",
    "Open": "Abrir",
    "Reset": "Restablecer",
    "Create": "Crear",
    "Upload": "Subir",
    "Print": "Imprimir",
    "Leader": "Líder",
    "Member": "Miembro",
    "Admin": "Administrador",
    "Own library": "Biblioteca propia",
    "New password": "Nueva contraseña",
    "Your multitrack library": "Tu biblioteca de multitracks",
    "Wrong username or password": "Usuario o contraseña incorrectos",
    "Language": "Idioma",
    # ---- library ----------------------------------------------------------------
    "+ New song": "+ Nueva canción",
    "Search title or artist": "Buscar por título o artista",
    "Search songs": "Buscar canciones",
    "No songs yet": "Todavía no hay canciones",
    "No songs match “{q}”.": "Ninguna canción coincide con “{q}”.",
    "Create a song, then drop its WAV stems in.": "Crea una canción y luego arrastra sus pistas WAV.",
    "Your church leader hasn't added any songs yet.": "Tu líder todavía no ha agregado canciones.",
    "Your leaders haven't added any songs yet.": "Tus líderes todavía no han agregado canciones.",
    "Drop a ZIP of stems to create a song": "Arrastra un ZIP con las pistas para crear una canción",
    "or click to choose. Drop several ZIPs to add several songs.": "o haz clic para elegir. Arrastra varios ZIP para agregar varias canciones.",
    "Name it like “Way Maker - E - 68bpm.zip” and the title, key and BPM are filled in for you.":
        "Nómbralo como “Way Maker - E - 68bpm.zip” y el título, el tono y el BPM se llenan solos.",
    "You're working in {church}'s library. New songs you add here belong to them.":
        "Estás trabajando en la biblioteca de {church}. Las canciones que agregues aquí son de esa iglesia.",
    "Back to my library": "Volver a mi biblioteca",
    "{church} · pick a song to rehearse": "{church} · elige una canción para ensayar",
    "Next up": "Próximo",
    "Coming up": "Más adelante",
    "All songs": "Todas las canciones",
    "{n} songs": "{n} canciones",
    # ---- song page ----------------------------------------------------------------
    "← Library": "← Biblioteca",
    "← Practice": "← Ensayo",
    "Change the key you play in. Shifts the chord chart and the preview audio.":
        "Cambia el tono en que tocas. Cambia los acordes y el audio de la vista previa.",
    "Original": "Original",
    "(original)": "(original)",
    "{n} tracks": "{n} pistas",
    "Edit details": "Editar datos",
    "Delete this song and all its audio? This cannot be undone.":
        "¿Eliminar esta canción y todo su audio? No se puede deshacer.",
    "You can play and download this song. Ask a church leader to make changes.":
        "Puedes reproducir y descargar esta canción. Pide a un líder de tu iglesia que haga cambios.",
    "{n} of {total}": "{n} de {total}",
    "Mix": "Mezcla",
    "Chord chart": "Acordes",
    "Play / pause (space)": "Reproducir / pausa (espacio)",
    "Back to start": "Volver al inicio",
    "Browser preview. Full playback comes in the Mac app.":
        "Vista previa en el navegador. La reproducción completa viene en la app para Mac.",
    "Solo": "Solo",
    "Mute": "Silenciar",
    "{name} level": "Nivel de {name}",
    "Drop WAV stems or a ZIP here": "Arrastra aquí pistas WAV o un ZIP",
    "or click to choose.": "o haz clic para elegir.",
    "Files named “click” or “guide” are tagged automatically.":
        "Los archivos llamados “click” o “guía” se marcan solos.",
    "Locked. Click Edit tracks to make changes.": "Bloqueado. Haz clic en Editar pistas para hacer cambios.",
    "Edit tracks": "Editar pistas",
    "Turn long filenames into standard names like Bajo, Acústica 2, Click":
        "Convierte nombres de archivo largos en nombres estándar como Bajo, Acústica 2, Click",
    "✨ Suggest names": "✨ Sugerir nombres",
    "Save changes": "Guardar cambios",
    "Track name": "Nombre de la pista",
    "Pick or type a name": "Elige o escribe un nombre",
    "Gain": "Ganancia",
    "Pan": "Paneo",
    "Muted": "Silenciada",
    "Move up": "Subir",
    "Move down": "Bajar",
    "Download WAV": "Descargar WAV",
    "stem": "Pista",
    "click": "Click",
    "guide": "Guía",
    "cue": "Cue",
    "mono": "mono",
    "stereo": "estéreo",
    "Sections": "Secciones",
    "Listening to the guide track for section cues…": "Escuchando la guía para encontrar las secciones…",
    "Heard in the guide track": "Detectada en la guía",
    "auto": "auto",
    "Add markers like Intro, Verse 1, Chorus so you can jump and loop in the player.":
        "Agrega marcas como Intro, Verso 1, Coro para saltar y repetir en el reproductor.",
    "No sections yet.": "Todavía no hay secciones.",
    "Chorus": "Coro",
    "Use current player time": "Usar el tiempo actual del reproductor",
    "Listen to the guide track and add its section cues. Sections you typed in are kept.":
        "Escucha la guía y agrega sus secciones. Las secciones que escribiste se conservan.",
    "🎧 Detect from guide": "🎧 Detectar desde la guía",
    "Clear auto sections": "Quitar secciones automáticas",
    "Smaller text": "Texto más pequeño",
    "Larger text": "Texto más grande",
    "Edit chart": "Editar acordes",
    "Add chart": "Agregar acordes",
    "No chord chart yet.": "Todavía no hay acordes.",
    "Click “Add chart” and paste one in.": "Haz clic en “Agregar acordes” y pega los tuyos.",
    "not set": "sin tono",
    "Write chords in the original key ({key}). Put chords on their own line above the lyrics, or inline in brackets like <code>Way[E]maker</code>. Section names go on their own line: <code>[Chorus]</code>, <code>Bridge:</code> or <code>{{c: Tag}}</code>.":
        "Escribe los acordes en el tono original ({key}). Pon los acordes en su propia línea arriba de la letra, o dentro del texto entre corchetes como <code>Way[E]maker</code>. Los nombres de sección van en su propia línea: <code>[Coro]</code>, <code>Puente:</code> o <code>{{c: Tag}}</code>.",
    "Save chart": "Guardar acordes",
    # ---- song form ----------------------------------------------------------------
    "New song": "Nueva canción",
    "Edit song": "Editar canción",
    "Edit {title}": "Editar {title}",
    "e.g. 72": "ej. 72",
    "Time signature": "Compás",
    "Arrangement notes, capo, who sings what…": "Notas del arreglo, capo, quién canta qué…",
    "Create song": "Crear canción",
    # ---- account ----------------------------------------------------------------
    "Account": "Cuenta",
    "Change password": "Cambiar contraseña",
    "Current password": "Contraseña actual",
    "App tokens": "Tokens de la app",
    "The Mac app signs in with your username and password and creates a token for itself. You can also create one here, and revoke any device you no longer use.":
        "La app para Mac inicia sesión con tu usuario y contraseña y crea su propio token. También puedes crear uno aquí y revocar los dispositivos que ya no uses.",
    "New token (shown once):": "Token nuevo (se muestra una sola vez):",
    "Device": "Dispositivo",
    "Created": "Creado",
    "Last used": "Último uso",
    "never": "nunca",
    "Revoke": "Revocar",
    "Device name, e.g. MacBook Pro": "Nombre del dispositivo, ej. MacBook Pro",
    "Create token": "Crear token",
    # ---- admin users ----------------------------------------------------------------
    "Add user": "Agregar usuario",
    "Display name": "Nombre para mostrar",
    "Admin (can manage users)": "Administrador (puede manejar usuarios)",
    "Delete {name} and all of their songs?": "¿Eliminar a {name} y todas sus canciones?",
    "People added here get their own private library. To add someone to a church, use <a href=\"/admin/churches\">Churches</a> → Members.":
        "Las personas que agregues aquí tienen su propia biblioteca privada. Para agregar a alguien a una iglesia, usa <a href=\"/admin/churches\">Iglesias</a> → Miembros.",
    # ---- churches ----------------------------------------------------------------
    "Each church gets its own page. Its people sign in here and land straight on it. They see only their own church's songs, which their leaders (or you) upload.":
        "Cada iglesia tiene su propia página. Su gente inicia sesión aquí y llega directo a ella. Solo ven las canciones de su iglesia, que suben sus líderes (o tú).",
    "Page": "Página",
    "People": "Personas",
    "Delete {name}, its people's logins and the songs they uploaded?":
        "¿Eliminar {name}, los accesos de su gente y las canciones que subieron?",
    "Add church": "Agregar iglesia",
    "Church name": "Nombre de la iglesia",
    "Page address": "Dirección de la página",
    "(optional)": "(opcional)",
    "First leader": "Primer líder",
    "(optional, you can add people later)": "(opcional, puedes agregar personas después)",
    # ---- members ----------------------------------------------------------------
    "{church} members": "Miembros de {church}",
    "<strong>Leaders</strong> add and change the church's songs and manage members. <strong>Members</strong> can play and download songs.":
        "Los <strong>líderes</strong> agregan y cambian las canciones de la iglesia y manejan a los miembros. Los <strong>miembros</strong> pueden reproducir y descargar canciones.",
    "Role for {name}": "Rol de {name}",
    "Remove {name} from {church}? The songs they added stay with the church.":
        "¿Quitar a {name} de {church}? Las canciones que agregó se quedan con la iglesia.",
    "No one yet. Add the first person below.": "Todavía no hay nadie. Agrega a la primera persona abajo.",
    "Add person": "Agregar persona",
    "Give them the username and password. They sign in on this site and go straight to {church}.":
        "Dales el usuario y la contraseña. Inician sesión en este sitio y llegan directo a {church}.",
    # ---- setlists ----------------------------------------------------------------
    "Build the songs for a service, then share it. Members see shared setlists at the top of their Practice page.":
        "Arma las canciones para un servicio y compártelo. Los miembros ven los setlists compartidos arriba en su página de Ensayo.",
    "New setlist": "Nuevo setlist",
    "Sunday": "Domingo",
    "Past": "Anteriores",
    "Shared": "Compartido",
    "Draft": "Borrador",
    "Shared with members": "Compartido con los miembros",
    "{n} songs · {length}": "{n} canciones · {length}",
    "▶ Start practising": "▶ Empezar a ensayar",
    "No songs in this setlist yet.": "Este setlist todavía no tiene canciones.",
    "Notes for the team": "Notas para el equipo",
    "Call time 8:30. Coro twice at the end of Santo.": "Llegar a las 8:30. Coro dos veces al final de Santo.",
    "No songs yet. Add some below.": "Todavía no hay canciones. Agrega algunas abajo.",
    "Song to add": "Canción para agregar",
    "Add a song…": "Agregar una canción…",
    "Share with members": "Compartir con los miembros",
    "They'll see it at the top of their Practice page.": "Lo verán arriba en su página de Ensayo.",
    "Save setlist": "Guardar setlist",
    "Delete this setlist? The songs stay in your library.": "¿Eliminar este setlist? Las canciones se quedan en tu biblioteca.",
    "Delete setlist": "Eliminar setlist",
    # ---- messages (flash / errors) ----------------------------------------------------
    "Song created. Now add its stems.": "Canción creada. Ahora agrega sus pistas.",
    "Saved.": "Guardado.",
    "Chord chart saved.": "Acordes guardados.",
    "Mark one track as Guide first.": "Primero marca una pista como Guía.",
    "Current password is wrong.": "La contraseña actual es incorrecta.",
    "Password changed.": "Contraseña cambiada.",
    "Token revoked.": "Token revocado.",
    "You can't delete your own account.": "No puedes eliminar tu propia cuenta.",
    "You can't take away your own leader role.": "No puedes quitarte tu propio rol de líder.",
    "You can't remove yourself.": "No puedes quitarte a ti mismo.",
    "Setlist created. Add songs, then share it with your members.":
        "Setlist creado. Agrega canciones y luego compártelo con tus miembros.",
    "Saved and shared with members.": "Guardado y compartido con los miembros.",
    "Saved as a draft. Members can't see it yet.": "Guardado como borrador. Los miembros todavía no lo ven.",
    "Tracks saved.": "Pistas guardadas.",
    "No track is marked as Guide.": "Ninguna pista está marcada como Guía.",
    "Didn't hear any section cues in the guide track.": "No se escucharon secciones en la guía.",
    "Form expired, please go back and try again": "El formulario expiró. Regresa e inténtalo de nuevo",
    "Transpose must be a whole number of semitones": "El cambio de tono debe ser un número entero de semitonos",
    "BPM must be a number": "El BPM debe ser un número",
    "BPM must be between 20 and 400": "El BPM debe estar entre 20 y 400",
    "Time signature should look like 4/4 or 6/8": "El compás debe verse como 4/4 o 6/8",
    "Enter a start time": "Escribe un tiempo de inicio",
    "Time should look like 1:23 or 83.5": "El tiempo debe verse como 1:23 o 83.5",
    "Title is required": "El título es obligatorio",
    "Unknown key": "Tono desconocido",
    "Track name is required": "El nombre de la pista es obligatorio",
    "Unknown track role": "Tipo de pista desconocido",
    "Gain must be a number": "La ganancia debe ser un número",
    "Pan must be a number": "El paneo debe ser un número",
    "Section name is required": "El nombre de la sección es obligatorio",
    "Username must be 2-64 letters, numbers, dots, dashes or underscores":
        "El usuario debe tener de 2 a 64 letras, números, puntos, guiones o guiones bajos",
    "Password must be at least 8 characters": "La contraseña debe tener al menos 8 caracteres",
    "That username is taken": "Ese usuario ya existe",
    "Church name is required": "El nombre de la iglesia es obligatorio",
    "Pick a web address with letters or numbers": "Elige una dirección con letras o números",
    "Unknown role": "Rol desconocido",
    "Use a date like 2026-11-22": "Usa una fecha como 2026-11-22",
    "Give the setlist a name": "Ponle nombre al setlist",
    "A song in the list isn't in this church's library": "Una canción de la lista no está en la biblioteca de esta iglesia",
    "File is too short to be a WAV file": "El archivo es demasiado corto para ser WAV",
    "Not a WAV file (missing RIFF/WAVE header)": "No es un archivo WAV (falta el encabezado RIFF/WAVE)",
    "Corrupt fmt chunk": "Bloque fmt dañado",
    "WAV file has no fmt chunk": "El WAV no tiene bloque fmt",
    "WAV file has no audio data": "El WAV no tiene audio",
    "WAV header has invalid channel, rate or bit-depth values": "El encabezado del WAV tiene canales, frecuencia o bits inválidos",
    "Only church leaders can add songs": "Solo los líderes de la iglesia pueden agregar canciones",
    "You can play this song but not change it": "Puedes reproducir esta canción pero no cambiarla",
    "Only church leaders can change setlists": "Solo los líderes de la iglesia pueden cambiar los setlists",
}

# Messages with names or numbers in them: (English regex, Spanish template).
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Created “(?P<t>.+)” with (?P<n>\d+) tracks\.$"), "Se creó “{t}” con {n} pistas."),
    (re.compile(r"^Created (?P<n>\d+) song\(s\)\.$"), "Se crearon {n} canción(es)."),
    (re.compile(r"^Deleted “(?P<t>.+)”\.$"), "Se eliminó “{t}”."),
    (re.compile(r"^Deleted (?P<t>.+)\.$"), "Se eliminó {t}."),
    (re.compile(r"^Added (?P<n>\d+) track\(s\)\.$"), "Se agregaron {n} pista(s)."),
    (re.compile(r"^Removed (?P<t>.+)\.$"), "Se quitó {t}."),
    (re.compile(r"^Saved (?P<t>.+)\.$"), "Se guardó {t}."),
    (re.compile(r"^Nothing was saved: (?P<t>.+)$"), "No se guardó nada: {t}"),
    (re.compile(r"^Added (?P<u>\S+)\. They sign in at this site and land on (?P<c>.+)\.$"),
     "Se agregó a {u}. Inicia sesión en este sitio y llega a {c}."),
    (re.compile(r"^Added (?P<c>.+)\. Its page is (?P<p>/c/\S+)\.$"), "Se agregó {c}. Su página es {p}."),
    (re.compile(r"^Added (?P<u>.+)\.$"), "Se agregó {u}."),
    (re.compile(r"^Password reset for (?P<u>.+)\.$"), "Se restableció la contraseña de {u}."),
    (re.compile(r"^(?P<u>\S+) is now a leader\.$"), "{u} ahora es líder."),
    (re.compile(r"^(?P<u>\S+) is now a member\.$"), "{u} ahora es miembro."),
    (re.compile(r"^The address (?P<p>/c/\S+) is taken$"), "La dirección {p} ya está ocupada"),
    (re.compile(r"^Transpose must be between (?P<a>-\d+) and (?P<b>\+\d+) semitones$"),
     "El cambio de tono debe estar entre {a} y {b} semitonos"),
    (re.compile(r"^Found (?P<n>\d+) sections? in the guide track\.$"), "Se encontraron {n} secciones en la guía."),
    (re.compile(r"^Couldn't listen to the guide track: (?P<t>.+)$"), "No se pudo escuchar la guía: {t}"),
    (re.compile(r"^Unsupported WAV encoding \((?P<t>.+)\); export as PCM or float$"),
     "Codificación WAV no compatible ({t}); exporta como PCM o float"),
    (re.compile(r"^(?P<f>.+): not a valid ZIP file$"), "{f}: no es un ZIP válido"),
    (re.compile(r"^(?P<f>.+): not a ZIP file$"), "{f}: no es un archivo ZIP"),
    (re.compile(r"^(?P<f>.+): no WAV files inside$"), "{f}: no tiene archivos WAV"),
]

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _one(text: str) -> str | None:
    if text in ES:
        return ES[text]
    for pattern, template in PATTERNS:
        m = pattern.match(text)
        if m:
            return template.format(**{k: translate_message("es", v) for k, v in m.groupdict().items()})
    # "file.wav: <reason>" from uploads
    head, sep, tail = text.partition(": ")
    if sep and tail in ES:
        return f"{head}: {ES[tail]}"
    return None


def translate_message(lang: str, text: str) -> str:
    """Translate a message built in Python. Unknown text is shown as it is."""
    if lang != "es" or not text:
        return text
    found = _one(text)
    if found is not None:
        return found
    # Several sentences joined together ("Tracks saved. Removed Bass.")
    parts = _SENTENCE.split(text)
    if len(parts) > 1:
        return " ".join(_one(p) or p for p in parts)
    return text


def gettext(lang: str):
    """The ``_`` used in templates: ``_("Hello {name}", name=x)``."""

    def _(text: str, **kw) -> str:
        out = ES.get(text, text) if lang == "es" else text
        return out.format(**kw) if kw else out

    return _


def pick_language(request, user) -> str:
    chosen = request.session.get("lang")
    if chosen in LANGS:
        return chosen
    if user is not None and getattr(user, "language", "") in LANGS:
        return user.language
    accept = request.headers.get("accept-language", "").lower()
    return "es" if accept.startswith("es") else "en"


# Strings the browser scripts show; sent to the page as window.I18N.
JS_ES = {
    "Unpacking…": "Descomprimiendo…",
    "Network error": "Error de red",
    "Upload failed": "No se pudo subir",
    "✓ {n} tracks": "✓ {n} pistas",
    "{n} added.": "{n} agregadas.",
    "Skipped {n} file(s) that aren't WAV or ZIP.": "Se omitieron {n} archivo(s) que no son WAV ni ZIP.",
    "Only ZIP files can be dropped here. Add single WAVs from a song's page.":
        "Aquí solo se pueden arrastrar ZIP. Agrega WAV sueltos desde la página de la canción.",
    "Editing. Changes aren't saved until you click Save changes.":
        "Editando. Los cambios no se guardan hasta que hagas clic en Guardar cambios.",
    "Locked. Click Edit tracks to make changes.": "Bloqueado. Haz clic en Editar pistas para hacer cambios.",
    "Unsaved changes.": "Cambios sin guardar.",
    "Suggested {n} names. Check them, then Save changes.": "Se sugirieron {n} nombres. Revísalos y luego Guardar cambios.",
    "Names already look tidy.": "Los nombres ya se ven bien.",
    "Remove {n} tracks and delete the audio? This cannot be undone.":
        "¿Quitar {n} pistas y borrar su audio? No se puede deshacer.",
    "Showing in {key} (original {orig}, {n})": "Mostrando en {key} (original {orig}, {n})",
    "Key of {key}": "Tono de {key}",
    "Transposed {n}": "Transportado {n}",
    "Loading tracks {done}/{total}…": "Cargando pistas {done}/{total}…",
    "Couldn't load: {err}": "No se pudo cargar: {err}",
}
