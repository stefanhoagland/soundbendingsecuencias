// Run with: node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("../app/static/chords.js");

test("recognises chords and rejects words", () => {
  for (const c of ["E", "F#m7", "Bb", "Asus4", "C/E", "Dmaj7", "G/B", "Cadd9", "E7(b9)", "Bbm", "F#m7b5", "Gsus", "A2"]) assert.ok(C.isChord(c), c);
  for (const w of ["Bridge", "Each", "And", "Am I", "Go", "Be", "Ab-solutely", "Every"]) assert.ok(!C.isChord(w), w);
});

test("transposes chords with the right spelling", () => {
  assert.equal(C.transposeChord("E", 1, false), "F");
  assert.equal(C.transposeChord("F#m7", 2, false), "G#m7");
  assert.equal(C.transposeChord("C/E", -2, true), "Bb/D");
  assert.equal(C.transposeChord("Asus4", 3, false), "Csus4");
  assert.equal(C.transposeChord("Bb", 0, false), "Bb");
});

test("transposes keys", () => {
  assert.equal(C.transposeKey("E", 1), "F");
  assert.equal(C.transposeKey("G", 1), "Ab");
  assert.equal(C.transposeKey("A", -2), "G");
  assert.equal(C.transposeKey("Bbm", 2), "Cm");
  assert.equal(C.transposeKey("", 3), "");
});

test("keeps chord columns over lyrics", () => {
  assert.equal(C.transposeChordLine("E        B/D#   C#m", 1, false), "F        C/E    Dm");
  assert.equal(C.transposeChordLine("A B", 1, true), "Bb C");
});

test("parses mixed chart formats", () => {
  const chart = [
    "{title: Way Maker}",
    "[Verse 1]",
    "E              B",
    "You are here, moving in our midst",
    "",
    "",
    "Chorus:",
    "Way[E]maker, [B]miracle worker",
    "{soc}",
    "[C#m]Promise keeper",
    "{eoc}",
    "| E / / / | B / / / | x2",
  ].join("\n");
  const blocks = C.parse(chart, 1, false);
  assert.deepEqual(blocks.map((b) => b.type), ["title", "heading", "pair", "blank", "heading", "inline", "heading", "inline", "chords"]);
  assert.equal(blocks[2].chords.trim(), "F              C");
  assert.deepEqual(blocks[5].parts.map((p) => p.chord), ["", "F", "C"]);
  assert.equal(blocks[7].chorus, true);
  assert.match(blocks[8].chords, /F \/ \/ \/ \| C/);
});

test("render escapes HTML", () => {
  assert.ok(!C.render("<script>alert(1)</script>").includes("<script>"));
});

test("Latin (Do-Re-Mi) chords transpose in Latin", () => {
  for (const c of ["Do", "Re", "Mim", "Fa#m7", "Sol/Si", "Sib", "La7sus4", "DO"]) assert.ok(C.isChord(c), c);
  assert.equal(C.transposeChord("Do", 2, false), "Re");
  assert.equal(C.transposeChord("Sol/Si", 2, false), "La/Do#");
  assert.equal(C.transposeChord("Mi7", -1, true), "Mib7");
  assert.equal(C.transposeChord("Sib", 2, false), "Do");
  assert.equal(C.transposeChordLine("Mi      Si      Do#m", 1, false), "Fa      Do      Rem");
});

test("labelled chord lines and extra symbols", () => {
  const b = C.parse("Intro: E B C#m A", 2, false);
  assert.deepEqual(b.map((x) => x.type), ["heading", "chords"]);
  assert.equal(b[1].chords, "F# C# D#m B");
  assert.equal(C.transposeChord("Fº", 2, false), "Gº");
  assert.equal(C.transposeChord("C△7", 2, false), "D△7");
});

test("Spanish lyric lines are not mistaken for chords", () => {
  assert.ok(!C.isChordLine("Mi Dios es fiel"));
  assert.ok(!C.isChordLine("Si tú estás aquí"));
});
