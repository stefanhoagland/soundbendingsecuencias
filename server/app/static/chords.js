/* Chord chart parsing, transposition and rendering.
 *
 * Supported input (mix freely):
 *   - ChordPro inline chords:   Way[E]maker, [B]miracle worker
 *   - Chord lines over lyrics:   E        B
 *                                Waymaker, miracle worker
 *   - Section headings:          [Chorus]   Chorus:   {c: Bridge}   {soc} ... {eoc}
 * Works in the browser (window.Chords) and in Node (module.exports) for tests.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Chords = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
  const PITCH = {};
  SHARPS.forEach((n, i) => (PITCH[n] = i));
  FLATS.forEach((n, i) => (PITCH[n] = i));
  Object.assign(PITCH, { Cb: 11, Fb: 4, "E#": 5, "B#": 0 });
  // Latin (Do-Re-Mi) note names, common in Spanish charts.
  const LATIN_SHARPS = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"];
  const LATIN_FLATS = ["Do", "Reb", "Re", "Mib", "Mi", "Fa", "Solb", "Sol", "Lab", "La", "Sib", "Si"];
  const LATIN = { do: 0, re: 2, mi: 4, fa: 5, sol: 7, la: 9, si: 11 };
  const FLAT_KEYS = new Set(["F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"]);

  // Root, quality (restricted so words like "Bridge" or "Each" are not chords), optional bass.
  const ROOT = "([A-G]|Do|Re|Mi|Fa|Sol|La|Si|DO|RE|MI|FA|SOL|LA|SI)";
  const CHORD_RE = new RegExp(
    "^" + ROOT + "([#b♯♭]?)((?:maj|min|dim|aug|sus|add|alt|no|omit|m|M|[0-9]|[+\\-#b()°º△ø^Δ,])*)(?:\\/" + ROOT + "([#b♯♭]?))?$");
  const FILLER_RE = /^(\||\|\||-+|\/|%|x\d+|\(x?\d+x?\)|N\.?C\.?|\(|\)|\.+|:\|\||\|\|:)$/i;
  const DIRECTIVE_RE = /^\s*\{\s*([a-z_]+)\s*(?::\s*(.*?))?\s*\}\s*$/i;
  const HEADING_RE = /^\s*(?:\[([^\]]+)\]|([A-Za-z][A-Za-z0-9 \-']{0,30}):)\s*$/;
  const SECTION_WORDS = /^(intro|verse|pre[- ]?chorus|chorus|bridge|tag|outro|ending|interlude|instrumental|turnaround|vamp|refrain|coda|breakdown|hook|post[- ]?chorus)\b/i;

  function isChord(token) {
    return CHORD_RE.test(token);
  }

  function prefersFlats(key) {
    return FLAT_KEYS.has(key);
  }

  function transposeKey(key, semitones) {
    if (!key) return "";
    const minor = key.endsWith("m");
    const root = minor ? key.slice(0, -1) : key;
    if (!(root in PITCH)) return key;
    const p = (((PITCH[root] + semitones) % 12) + 12) % 12;
    const s = SHARPS[p] + (minor ? "m" : "");
    const f = FLATS[p] + (minor ? "m" : "");
    return s === f ? s : FLAT_KEYS.has(f) ? f : s;
  }

  function pitchOf(root, acc) {
    acc = acc === "♯" ? "#" : acc === "♭" ? "b" : acc;
    const latin = LATIN[root.toLowerCase()];
    const base = latin !== undefined ? latin : PITCH[root];
    return base + (acc === "#" ? 1 : acc === "b" ? -1 : 0);
  }

  function shiftNote(root, acc, semitones, flats) {
    const p = (((pitchOf(root, acc) + semitones) % 12) + 12) % 12;
    if (LATIN[root.toLowerCase()] !== undefined) {
      const name = (flats ? LATIN_FLATS : LATIN_SHARPS)[p];
      return root === root.toUpperCase() ? name.toUpperCase().replace("B", "b") : name;
    }
    return (flats ? FLATS : SHARPS)[p];
  }

  /** Transpose one chord symbol. `flats` picks the spelling of the result. */
  function transposeChord(chord, semitones, flats) {
    if (!semitones) return chord;
    const m = CHORD_RE.exec(chord);
    if (!m) return chord;
    const [, r, ra, quality, b, ba] = m;
    let out = shiftNote(r, ra, semitones, flats) + quality;
    if (b) out += "/" + shiftNote(b, ba, semitones, flats);
    return out;
  }

  function tokensOf(line) {
    const out = [];
    const re = /\S+/g;
    let m;
    while ((m = re.exec(line))) out.push({ text: m[0], at: m.index });
    return out;
  }

  function isChordLine(line) {
    const toks = tokensOf(line);
    if (!toks.length) return false;
    let chords = 0;
    for (const t of toks) {
      if (isChord(t.text)) chords++;
      else if (!FILLER_RE.test(t.text)) return false;
    }
    return chords > 0;
  }

  /** Transpose a chord-only line, keeping chords at their columns where possible. */
  function transposeChordLine(line, semitones, flats) {
    let out = "";
    for (const t of tokensOf(line)) {
      const text = isChord(t.text) ? transposeChord(t.text, semitones, flats) : t.text;
      if (out.length < t.at) out += " ".repeat(t.at - out.length);
      else if (out.length && out[out.length - 1] !== " ") out += " ";
      out += text;
    }
    return out;
  }

  /** Split "Way[E]maker" into [{chord:"", lyric:"Way"}, {chord:"E", lyric:"maker"}]. */
  function splitInline(line, semitones, flats) {
    const parts = [];
    const re = /\[([^\]]*)\]/g;
    let last = 0, chord = "", m;
    while ((m = re.exec(line))) {
      parts.push({ chord, lyric: line.slice(last, m.index) });
      chord = isChord(m[1].trim()) ? transposeChord(m[1].trim(), semitones, flats) : m[1];
      last = re.lastIndex;
    }
    parts.push({ chord, lyric: line.slice(last) });
    return parts.filter((p, i) => i > 0 || p.lyric);
  }

  function hasInlineChords(line) {
    const re = /\[([^\]]+)\]/g;
    let m;
    while ((m = re.exec(line))) if (isChord(m[1].trim())) return true;
    return false;
  }

  /** Charts pasted from websites or PDFs carry invisible characters (zero-width spaces,
   *  no-break spaces, odd line breaks) that stop chords from being recognised. */
  function normalize(text) {
    return String(text || "")
      .replace(/\r\n?|[\u2028\u2029\u0085]/g, "\n")
      .replace(/[\u200b-\u200d\u2060\ufeff\u00ad]/g, "")
      .replace(/[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000\t]/g, (c) => (c === "\t" ? "    " : " "))
      .replace(/[\uff03]/g, "#");
  }

  /** Parse a chart into blocks the renderer (or the Mac app) can lay out. */
  function parse(text, semitones, flats) {
    semitones = semitones || 0;
    const lines = normalize(text).split("\n");
    const out = [];
    let inChorus = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const d = DIRECTIVE_RE.exec(line);
      if (d) {
        const name = d[1].toLowerCase();
        const val = d[2] || "";
        if (name === "title" || name === "t") out.push({ type: "title", text: val });
        else if (name === "subtitle" || name === "st" || name === "artist") out.push({ type: "subtitle", text: val });
        else if (["comment", "c", "ci", "comment_italic", "cb", "comment_box"].includes(name)) out.push({ type: "heading", text: val });
        else if (name === "start_of_chorus" || name === "soc") { inChorus = true; out.push({ type: "heading", text: val || "Chorus" }); }
        else if (name === "end_of_chorus" || name === "eoc") inChorus = false;
        else if (/^start_of_(verse|bridge|tab)$|^so[vbt]$/.test(name)) { if (val) out.push({ type: "heading", text: val }); }
        continue;  // other directives (key, tempo, ...) are metadata we already store
      }
      if (!line.trim()) { out.push({ type: "blank" }); continue; }
      const h = HEADING_RE.exec(line);
      if (h) {
        const label = (h[1] || h[2]).trim();
        if (h[2] ? SECTION_WORDS.test(label) : !isChord(label)) {
          out.push({ type: "heading", text: label });
          continue;
        }
      }
      const tagged = /^\s*\[([^\]]+)\]\s+(.+)$/.exec(line);
      if (tagged && !isChord(tagged[1].trim()) && isChordLine(tagged[2])) {
        out.push({ type: "heading", text: tagged[1].trim() });
        out.push({ type: "chords", chords: transposeChordLine(tagged[2], semitones, flats), chorus: inChorus });
        continue;
      }
      const labelled = /^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 \-']{0,24}):\s+(.+)$/.exec(line);
      if (labelled && isChordLine(labelled[2])) {
        out.push({ type: "heading", text: labelled[1].trim() });
        out.push({ type: "chords", chords: transposeChordLine(labelled[2], semitones, flats), chorus: inChorus });
        continue;
      }
      if (isChordLine(line)) {
        const chords = transposeChordLine(line, semitones, flats);
        const next = lines[i + 1];
        if (next !== undefined && next.trim() && !isChordLine(next) && !DIRECTIVE_RE.test(next) && !HEADING_RE.test(next) && !hasInlineChords(next)) {
          out.push({ type: "pair", chords, lyric: next, chorus: inChorus });
          i++;
        } else {
          out.push({ type: "chords", chords, chorus: inChorus });
        }
        continue;
      }
      if (hasInlineChords(line)) {
        out.push({ type: "inline", parts: splitInline(line, semitones, flats), chorus: inChorus });
        continue;
      }
      out.push({ type: "lyric", text: line, chorus: inChorus });
    }
    // collapse runs of blank lines
    return out.filter((b, i) => !(b.type === "blank" && (i === 0 || out[i - 1].type === "blank")));
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  function chordSpans(text) {
    // Wrap chord tokens so they can be coloured, leaving spacing intact.
    return esc(text).replace(/\S+/g, (t) => (isChord(t) ? `<b>${t}</b>` : t));
  }

  function toHTML(blocks) {
    return blocks.map((b) => {
      const cls = b.chorus ? " chorus" : "";
      switch (b.type) {
        case "title": return `<h3 class="c-title">${esc(b.text)}</h3>`;
        case "subtitle": return `<div class="c-subtitle">${esc(b.text)}</div>`;
        case "heading": return `<div class="c-heading">${esc(b.text)}</div>`;
        case "blank": return `<div class="c-blank"></div>`;
        case "pair": return `<pre class="c-pair${cls}"><span class="c-chords">${chordSpans(b.chords)}</span>\n${esc(b.lyric)}</pre>`;
        case "chords": return `<pre class="c-pair${cls}"><span class="c-chords">${chordSpans(b.chords)}</span></pre>`;
        case "inline":
          return `<div class="c-line${cls}">` + b.parts.map((p) =>
            `<span class="c-seg"><b class="c-chord">${esc(p.chord) || "&nbsp;"}</b><span class="c-lyric">${esc(p.lyric) || "&nbsp;"}</span></span>`
          ).join("") + `</div>`;
        default: return `<div class="c-lyric-line${cls}">${esc(b.text)}</div>`;
      }
    }).join("\n");
  }

  function render(text, semitones, flats) {
    return toHTML(parse(text, semitones, flats));
  }

  return { normalize, isChord, isChordLine, transposeChord, transposeChordLine, transposeKey, prefersFlats, parse, render };
});
