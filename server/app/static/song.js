(() => {
  "use strict";

  // ---------- Upload ----------
  const uploadForm = document.getElementById("upload");
  const fileInput = document.getElementById("files");
  const list = document.getElementById("upload-list");

  function uploadOne(file) {
    return new Promise((resolve) => {
      const li = document.createElement("li");
      li.innerHTML = '<span class="fname"></span><progress max="100" value="0"></progress><span class="status"></span>';
      li.querySelector(".fname").textContent = file.name;
      list.appendChild(li);
      const bar = li.querySelector("progress");
      const status = li.querySelector(".status");
      const body = new FormData();
      body.append("files", file, file.name);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", uploadForm.action);
      xhr.setRequestHeader("X-CSRF-Token", window.CSRF);
      xhr.setRequestHeader("X-Requested-With", "fetch");
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        bar.value = (e.loaded / e.total) * 100;
        if (e.loaded === e.total && /\.zip$/i.test(file.name)) status.textContent = "Unpacking…";
      };
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (_) {}
        if (xhr.status === 200 && !(data.errors || []).length) {
          bar.value = 100; li.classList.add("ok");
          const n = (data.created || []).length;
          status.textContent = /\.zip$/i.test(file.name) ? `✓ ${n} track${n === 1 ? "" : "s"}` : "✓";
        } else if (xhr.status === 200) {
          status.textContent = `${(data.created || []).length} added. ` + data.errors.join(" ");
          li.classList.add("error");
        } else {
          status.textContent = (data.errors && data.errors.join(" ")) || data.detail || "Upload failed";
          li.classList.add("error");
        }
        resolve(xhr.status === 200 && (data.created || []).length > 0);
      };
      xhr.onerror = () => { status.textContent = "Network error"; li.classList.add("error"); resolve(false); };
      xhr.send(body);
    });
  }

  async function uploadAll(files) {
    const wavs = [...files].filter((f) => /\.(wav|zip)$/i.test(f.name) || /wav|zip/.test(f.type));
    const skipped = files.length - wavs.length;
    if (skipped) {
      const li = document.createElement("li");
      li.className = "error";
      li.textContent = `Skipped ${skipped} file(s) that aren't WAV or ZIP.`;
      list.appendChild(li);
    }
    if (!wavs.length) return;
    uploadForm.classList.add("busy");
    let ok = 0;
    for (const f of wavs) if (await uploadOne(f)) ok++;   // one at a time keeps the server's disk happy
    uploadForm.classList.remove("busy");
    if (ok) setTimeout(() => location.reload(), 600);
  }

  if (uploadForm) {
    fileInput.addEventListener("change", () => uploadAll(fileInput.files));
    ["dragenter", "dragover"].forEach((ev) =>
      uploadForm.addEventListener(ev, (e) => { e.preventDefault(); uploadForm.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) =>
      uploadForm.addEventListener(ev, (e) => { e.preventDefault(); uploadForm.classList.remove("over"); }));
    uploadForm.addEventListener("drop", (e) => uploadAll(e.dataTransfer.files));
  }

  // ---------- Track list: locked until "Edit tracks" ----------
  const tracksForm = document.getElementById("tracks-form");
  if (tracksForm) {
    const fields = document.getElementById("tracks-fields");
    const editBtn = document.getElementById("tracks-edit");
    const saveBtn = document.getElementById("tracks-save");
    const cancelBtn = document.getElementById("tracks-cancel");
    const status = document.getElementById("tracks-status");
    const list = tracksForm.querySelector(".tracks");
    const originalOrder = [...list.children];
    let dirty = false;

    const suggestBtn = document.getElementById("tracks-suggest");
    const setEditing = (on) => {
      fields.disabled = !on;
      tracksForm.classList.toggle("editing", on);
      editBtn.hidden = on; saveBtn.hidden = !on; cancelBtn.hidden = !on; suggestBtn.hidden = !on;
      status.textContent = on ? "Editing. Changes aren't saved until you click Save changes." : "Locked. Click Edit tracks to make changes.";
    };
    const markDirty = () => { dirty = true; status.textContent = "Unsaved changes."; };

    editBtn.addEventListener("click", () => setEditing(true));
    suggestBtn.addEventListener("click", () => {
      let changed = 0;
      list.querySelectorAll(".track").forEach((li) => {
        const input = li.querySelector(".name");
        const name = li.dataset.suggest;
        if (name && input.value !== name) { input.value = name; changed++; }
        // A name like "Click" or "Guía" also sets the role.
        const role = li.querySelector("select");
        const n = name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
        if (n === "click") role.value = "click";
        else if (n.startsWith("guia") || n === "cues" || n === "conteo") role.value = "guide";
      });
      markDirty();
      status.textContent = changed ? `Suggested ${changed} name${changed === 1 ? "" : "s"}. Check them, then Save changes.` : "Names already look tidy.";
    });
    // Picking "Click"/"Guía" from the list sets the role too.
    list.addEventListener("change", (e) => {
      if (!e.target.classList.contains("name")) return;
      const n = e.target.value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const role = e.target.closest(".track").querySelector("select");
      if (n === "click") role.value = "click";
      else if (n.startsWith("guia")) role.value = "guide";
    });
    cancelBtn.addEventListener("click", () => {
      tracksForm.reset();
      originalOrder.forEach((li) => list.appendChild(li));
      list.querySelectorAll(".track").forEach((li) => li.classList.remove("removing"));
      dirty = false;
      setEditing(false);
    });
    tracksForm.addEventListener("input", markDirty);
    tracksForm.addEventListener("change", (e) => {
      if (e.target.name && e.target.name.startsWith("delete-")) e.target.closest(".track").classList.toggle("removing", e.target.checked);
    });
    list.addEventListener("click", (e) => {
      const btn = e.target.closest(".move");
      if (!btn) return;
      const li = btn.closest(".track");
      if (btn.dataset.dir === "-1" && li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
      if (btn.dataset.dir === "1" && li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
      markDirty();
    });
    tracksForm.addEventListener("submit", (e) => {
      const n = tracksForm.querySelectorAll('input[name^="delete-"]:checked').length;
      if (n && !window.confirm(`Remove ${n} track${n === 1 ? "" : "s"} and delete the audio? This cannot be undone.`)) { e.preventDefault(); return; }
      dirty = false;
    });
    window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
    setEditing(false);
  }

  // ---------- Section detection progress ----------
  const detect = document.getElementById("detect-status");
  if (detect) {
    const poll = async () => {
      try {
        const r = await fetch(detect.dataset.url, { credentials: "same-origin" });
        const d = await r.json();
        if (!["queued", "running"].includes(d.status)) { location.hash = "sections"; location.reload(); return; }
      } catch (_) {}
      setTimeout(poll, 3000);
    };
    setTimeout(poll, 3000);
  }

  // ---------- Tabs ----------
  const tabs = document.querySelectorAll(".tabs [data-tab]");
  function showTab(name) {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== name));
    const url = new URL(location.href);
    url.searchParams.set("tab", name);
    history.replaceState(null, "", url);
  }
  tabs.forEach((t) => t.addEventListener("click", (e) => { e.preventDefault(); showTab(t.dataset.tab); }));

  // ---------- Key & chord chart ----------
  window.SBS = window.SBS || {};
  const transposeSel = document.getElementById("transpose");
  const originalKey = transposeSel ? transposeSel.dataset.key : "";
  const chartSrc = document.getElementById("chart-src");
  let chartText = chartSrc ? JSON.parse(chartSrc.textContent) : "";
  const chartView = document.getElementById("chart-view");
  const chartForm = document.getElementById("chart-form");
  const chartTextarea = document.getElementById("chart-text");
  const chartPreview = document.getElementById("chart-preview");
  const keyLabel = document.getElementById("chart-key-label");

  const semis = () => (transposeSel ? parseInt(transposeSel.value, 10) || 0 : 0);
  const playKey = () => window.Chords.transposeKey(originalKey, semis());
  // Spell chords for the key we're playing in; with no key set, sharps going up and flats going down.
  const useFlats = () => (originalKey ? window.Chords.prefersFlats(playKey()) : semis() < 0);

  function renderChart() {
    if (!chartView || !window.Chords) return;
    if (chartText) chartView.innerHTML = window.Chords.render(chartText, semis(), useFlats());
    if (keyLabel) {
      const n = semis();
      keyLabel.textContent = originalKey
        ? (n ? `Showing in ${playKey()} (original ${originalKey}, ${n > 0 ? "+" : ""}${n})` : `Key of ${originalKey}`)
        : (n ? `Transposed ${n > 0 ? "+" : ""}${n}` : "");
    }
    if (chartPreview && !chartForm.hidden) chartPreview.innerHTML = window.Chords.render(chartTextarea.value, semis(), useFlats());
  }

  if (chartForm) {
    const edit = document.getElementById("chart-edit");
    edit.addEventListener("click", () => {
      chartForm.hidden = false; chartView.hidden = true; edit.hidden = true;
      chartTextarea.focus(); renderChart();
    });
    document.getElementById("chart-cancel").addEventListener("click", () => {
      chartTextarea.value = chartText;
      chartForm.hidden = true; chartView.hidden = false; edit.hidden = false;
    });
    chartTextarea.addEventListener("input", renderChart);
    let size = 1;
    try { size = parseFloat(localStorage.getItem("sbs.chartSize")) || 1; } catch (_) {}
    const applySize = () => {
      document.documentElement.style.setProperty("--chart-scale", size);
      try { localStorage.setItem("sbs.chartSize", size); } catch (_) {}
    };
    document.getElementById("chart-smaller").addEventListener("click", () => { size = Math.max(0.7, size - 0.1); applySize(); });
    document.getElementById("chart-larger").addEventListener("click", () => { size = Math.min(2.2, size + 0.1); applySize(); });
    applySize();
  }

  if (transposeSel) {
    transposeSel.addEventListener("change", async () => {
      renderChart();
      if (window.SBS.setPitch) window.SBS.setPitch(semis());
      const body = new URLSearchParams({ semitones: transposeSel.value });
      try {
        await fetch(transposeSel.dataset.url, {
          method: "POST", body,
          headers: { "X-CSRF-Token": window.CSRF, "X-Requested-With": "fetch" },
        });
      } catch (_) { /* the page still works; it just won't remember the key */ }
    });
  }
  renderChart();

  // ---------- Preview player ----------
  // Every stem is decoded into memory and started from the same AudioContext clock,
  // so tracks stay sample-locked to each other (and to the click) for the whole song.
  const mixer = document.getElementById("mixer");
  if (!mixer) return;

  const playBtn = document.getElementById("play");
  const stopBtn = document.getElementById("stop");
  const clock = document.getElementById("clock");
  const timeline = document.getElementById("timeline");
  const progress = document.getElementById("progress");
  const loadNote = document.getElementById("load-note");

  let ctx = null;
  let loading = null;       // promise while stems download/decode
  let playing = false;
  let startedAt = 0;        // ctx time when playback (re)started
  let offset = 0;           // song position at startedAt (or while paused)
  let duration = 0;
  let pitchRatio = 1;
  let shifter = null;

  const strips = [...mixer.querySelectorAll(".strip")].map((el) => ({
    el,
    url: el.dataset.src,
    pitched: !/role-(click|guide)/.test(el.className),   // click & guide never get pitch-shifted
    gainDb: parseFloat(el.dataset.gain) || 0,
    pan: parseFloat(el.dataset.pan) || 0,
    muted: el.dataset.muted === "1",
    solo: false,
    buffer: null, source: null, gain: null, panner: null, analyser: null,
  }));

  const position = () => (playing ? offset + (ctx.currentTime - startedAt) : offset);

  function fmt(t) {
    t = Math.max(0, t || 0);
    return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  }

  // One processor handles both buses so they get exactly the same latency:
  // inputs 0-1 = stems (pitch-shifted when transposed), inputs 2-3 = click/guide (only delayed
  // by the shifter's average latency so they stay lined up with the shifted stems).
  function makeProcessor() {
    const node = ctx.createScriptProcessor(2048, 4, 2);
    const N = 16384, W = Math.round(ctx.sampleRate * 0.05), HALF = W / 2 + 2;
    const pbuf = [new Float32Array(N), new Float32Array(N)];
    const dbuf = [new Float32Array(N), new Float32Array(N)];
    let w = 0, phase = 0;
    const tap = (b, pos) => {
      pos = ((pos % N) + N) % N;
      const i0 = Math.floor(pos), f = pos - i0;
      return b[i0] * (1 - f) + b[(i0 + 1) % N] * f;
    };
    node.onaudioprocess = (e) => {
      const ib = e.inputBuffer, ob = e.outputBuffer;
      const pin = [ib.getChannelData(0), ib.getChannelData(1)];
      const din = [ib.getChannelData(2), ib.getChannelData(3)];
      const out = [ob.getChannelData(0), ob.getChannelData(1)];
      const len = out[0].length;
      if (pitchRatio === 1) {
        for (let c = 0; c < 2; c++) for (let i = 0; i < len; i++) out[c][i] = pin[c][i] + din[c][i];
        return;
      }
      const step = (pitchRatio - 1) / W;
      for (let i = 0; i < len; i++) {
        const p1 = phase, p2 = (phase + 0.5) % 1;
        const g1 = Math.sin(Math.PI * p1) ** 2, g2 = Math.sin(Math.PI * p2) ** 2;
        const d1 = p1 * W + 2, d2 = p2 * W + 2;
        for (let c = 0; c < 2; c++) {
          pbuf[c][w] = pin[c][i];
          dbuf[c][w] = din[c][i];
          out[c][i] = tap(pbuf[c], w - d1) * g1 + tap(pbuf[c], w - d2) * g2 + dbuf[c][(w - HALF + N) % N];
        }
        w = (w + 1) % N;
        phase -= step;
        phase -= Math.floor(phase);
      }
    };
    return node;
  }

  function buildGraph() {
    ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "playback" });
    const merger = ctx.createChannelMerger(4);
    const busses = {};
    for (const [name, first] of [["pitched", 0], ["dry", 2]]) {
      const bus = ctx.createGain();
      bus.channelCount = 2;
      bus.channelCountMode = "explicit";
      bus.channelInterpretation = "speakers";
      const split = ctx.createChannelSplitter(2);
      bus.connect(split);
      split.connect(merger, 0, first);
      split.connect(merger, 1, first + 1);
      busses[name] = bus;
    }
    shifter = makeProcessor();
    merger.connect(shifter);
    shifter.connect(ctx.destination);
    for (const s of strips) {
      s.gain = ctx.createGain();
      s.panner = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
      if (s.panner) { s.gain.connect(s.panner); s.panner.pan.value = s.pan; }
      (s.panner || s.gain).connect(s.pitched ? busses.pitched : busses.dry);
      s.analyser = ctx.createAnalyser();
      s.analyser.fftSize = 1024;
      (s.panner || s.gain).connect(s.analyser);
    }
    applyMix();
  }

  async function load() {
    if (loading) return loading;
    loading = (async () => {
      buildGraph();
      let done = 0;
      const note = () => { if (loadNote) loadNote.textContent = `Loading tracks ${done}/${strips.length}…`; };
      note();
      playBtn.disabled = true;
      // A few at a time keeps memory and the server's disk happy.
      const queue = [...strips];
      const worker = async () => {
        while (queue.length) {
          const s = queue.shift();
          try {
            const res = await fetch(s.url, { credentials: "same-origin" });
            if (!res.ok) throw new Error(res.statusText);
            s.buffer = await ctx.decodeAudioData(await res.arrayBuffer());
          } catch (err) {
            s.el.classList.add("failed");
            s.el.title = `Couldn't load: ${err.message || err}`;
          }
          done++; note();
        }
      };
      await Promise.all([worker(), worker(), worker()]);
      duration = Math.max(0, ...strips.map((s) => (s.buffer ? s.buffer.duration : 0)));
      playBtn.disabled = false;
      if (loadNote) loadNote.textContent = "";
    })();
    return loading;
  }

  function applyMix() {
    const anySolo = strips.some((s) => s.solo);
    for (const s of strips) {
      const audible = anySolo ? s.solo : !s.muted;
      if (s.gain) s.gain.gain.setTargetAtTime(audible ? Math.pow(10, s.gainDb / 20) : 0, ctx.currentTime, 0.01);
      s.el.classList.toggle("silent", !audible);
    }
  }

  function stopSources() {
    for (const s of strips) {
      if (s.source) { try { s.source.stop(); } catch (_) {} s.source.disconnect(); s.source = null; }
    }
  }

  function startSources(from) {
    const when = ctx.currentTime + 0.06;   // a little headroom so every track starts on the same sample
    for (const s of strips) {
      if (!s.buffer || from >= s.buffer.duration) continue;
      const src = ctx.createBufferSource();
      src.buffer = s.buffer;
      src.connect(s.gain);
      src.start(when, from);
      s.source = src;
    }
    startedAt = when;
    offset = from;
  }

  async function play() {
    await load();
    if (ctx.state === "suspended") await ctx.resume();
    if (offset >= duration) offset = 0;
    startSources(offset);
    playing = true;
    playBtn.textContent = "❚❚";
    requestAnimationFrame(tick);
  }

  function pause() {
    if (!playing) return;
    offset = Math.min(position(), duration);
    stopSources();
    playing = false;
    playBtn.textContent = "▶";
    render();
  }

  function seek(t) {
    t = Math.max(0, Math.min(t, duration || t));
    if (playing) { stopSources(); startSources(t); } else { offset = t; }
    render();
  }

  function render() {
    const t = ctx ? position() : offset;
    clock.textContent = fmt(t);
    progress.style.width = duration ? `${Math.min(100, (t / duration) * 100)}%` : "0";
  }

  function tick() {
    if (!playing) return;
    if (position() >= duration) { pause(); offset = 0; render(); return; }
    render();
    requestAnimationFrame(tick);
  }

  window.SBS.setPitch = (semitones) => { pitchRatio = Math.pow(2, (semitones || 0) / 12); };
  window.SBS.setPitch(transposeSel ? parseInt(transposeSel.value, 10) : 0);

  playBtn.addEventListener("click", () => (playing ? pause() : play()));
  stopBtn.addEventListener("click", () => { pause(); offset = 0; render(); });
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName)) {
      e.preventDefault();
      playing ? pause() : play();
    }
  });

  // Duration from the page (longest stem) so the timeline works before audio is loaded.
  duration = parseFloat(timeline.dataset.duration) || 0;

  timeline.addEventListener("click", (e) => {
    if (e.target.classList.contains("marker")) return;
    const r = timeline.getBoundingClientRect();
    seek(((e.clientX - r.left) / r.width) * duration);
  });
  document.querySelectorAll("[data-time]").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.preventDefault();
      seek(parseFloat(b.dataset.time));
      document.getElementById("player").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));

  const useTime = document.getElementById("use-time");
  if (useTime) useTime.addEventListener("click", () => {
    const t = ctx ? position() : offset;
    document.getElementById("section-start").value = `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;
  });

  // Console-style fader law: 0 dB sits three quarters up, +12 at the top, -60 (off) at the bottom.
  const MAX_DB = 12, MIN_DB = -60, UNITY = 0.75;
  const dbToPos = (db) => (db >= 0 ? UNITY + (db / MAX_DB) * (1 - UNITY) : UNITY * (1 - Math.sqrt(Math.min(1, db / MIN_DB))));
  const posToDb = (p) => (p >= UNITY ? ((p - UNITY) / (1 - UNITY)) * MAX_DB : MIN_DB * (1 - p / UNITY) ** 2);
  const SCALE = [12, 6, 0, -5, -10, -20, -30, -40, -60];

  function placeCap(s) {
    const p = dbToPos(s.gainDb);
    s.cap.style.top = `calc(.55rem + ${(1 - p).toFixed(4)} * (100% - 1.1rem))`;
    s.fader.setAttribute("aria-valuenow", s.gainDb.toFixed(1));
    s.dbLabel.textContent = s.gainDb <= MIN_DB + 0.05 ? "-∞" : `${s.gainDb >= 0 ? "+" : ""}${s.gainDb.toFixed(1)}`;
  }

  for (const s of strips) {
    s.fader = s.el.querySelector(".fader");
    s.cap = s.el.querySelector(".fader-cap");
    s.dbLabel = s.el.querySelector(".db");
    s.meterFill = s.el.querySelector(".meter-fill");
    s.meterPeak = s.el.querySelector(".meter-peak");
    s.peakHold = 0; s.peakAt = 0; s.level = 0;
    const scale = s.el.querySelector(".fader-scale");
    scale.innerHTML = SCALE.map((db) => `<i class="${db === 0 ? "zero" : ""}" style="top:${((1 - dbToPos(db)) * 100).toFixed(2)}%"></i>`).join("");
    placeCap(s);

    const update = () => { if (ctx) applyMix(); else s.el.classList.toggle("silent", s.muted); };
    const setDb = (db) => {
      s.gainDb = Math.round(Math.max(MIN_DB, Math.min(MAX_DB, db)) * 10) / 10;
      placeCap(s); update();
    };
    const fromPointer = (e) => {
      const r = s.fader.getBoundingClientRect();
      const inner = r.height - 17.6;  // minus the cap's travel margins (1.1rem)
      const p = 1 - (e.clientY - r.top - 8.8) / inner;
      return posToDb(Math.max(0, Math.min(1, p)));
    };
    let dragging = false, grabOffset = 0;
    s.fader.addEventListener("pointerdown", (e) => {
      s.fader.setPointerCapture(e.pointerId);
      dragging = true;
      // Grabbing the cap moves it relatively; clicking the slot jumps there.
      const capR = s.cap.getBoundingClientRect();
      grabOffset = (e.target.closest(".fader-cap")) ? e.clientY - (capR.top + capR.height / 2) : 0;
      if (!grabOffset && !e.target.closest(".fader-cap")) setDb(fromPointer(e));
      s.fader.focus();
    });
    s.fader.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      setDb(fromPointer({ clientY: e.clientY - grabOffset }));
    });
    const end = () => { dragging = false; };
    s.fader.addEventListener("pointerup", end);
    s.fader.addEventListener("pointercancel", end);
    s.fader.addEventListener("dblclick", () => setDb(0));   // double-click = back to unity
    s.fader.addEventListener("wheel", (e) => { e.preventDefault(); setDb(posToDb(Math.max(0, Math.min(1, dbToPos(s.gainDb) - e.deltaY * 0.0008)))); }, { passive: false });
    s.fader.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 0.1 : 0.02;
      if (e.key === "ArrowUp") { e.preventDefault(); setDb(posToDb(Math.min(1, dbToPos(s.gainDb) + step))); }
      if (e.key === "ArrowDown") { e.preventDefault(); setDb(posToDb(Math.max(0, dbToPos(s.gainDb) - step))); }
      if (e.key === "0" || e.key === "Home") { e.preventDefault(); setDb(0); }
    });

    const muteBtn = s.el.querySelector(".mute");
    const soloBtn = s.el.querySelector(".solo");
    muteBtn.addEventListener("click", () => { s.muted = !s.muted; muteBtn.classList.toggle("on", s.muted); update(); });
    soloBtn.addEventListener("click", () => {
      s.solo = !s.solo; soloBtn.classList.toggle("on", s.solo);
      if (ctx) applyMix();
      else { const any = strips.some((x) => x.solo); strips.forEach((x) => x.el.classList.toggle("silent", any ? !x.solo : x.muted)); }
    });
  }

  // ---------- Meters (post-fader peak, like a console) ----------
  const meterBuf = new Float32Array(1024);
  function drawMeters(now) {
    for (const s of strips) {
      let peak = 0;
      if (s.analyser && playing) {
        s.analyser.getFloatTimeDomainData(meterBuf);
        for (let i = 0; i < meterBuf.length; i++) { const v = Math.abs(meterBuf[i]); if (v > peak) peak = v; }
      }
      const db = peak > 0 ? 20 * Math.log10(peak) : -Infinity;
      const target = Math.max(0, Math.min(1, (db + 60) / 60));      // -60..0 dBFS
      s.level = target > s.level ? target : Math.max(target, s.level - 0.018);   // fast attack, smooth fall
      if (s.level > s.peakHold || now - s.peakAt > 1200) { s.peakHold = s.level; s.peakAt = now; }
      s.meterFill.style.clipPath = `inset(${((1 - s.level) * 100).toFixed(1)}% 0 0 0)`;
      s.meterPeak.style.bottom = `calc(${(s.peakHold * 100).toFixed(1)}% - 2px)`;
      s.meterPeak.style.opacity = s.peakHold > 0.01 ? (s.peakHold > 0.97 ? 1 : 0.7) : 0;
      s.meterPeak.style.background = s.peakHold > 0.97 ? "#ff5d6c" : "#fff";
    }
    requestAnimationFrame(drawMeters);
  }
  requestAnimationFrame(drawMeters);

  strips.forEach((s) => s.el.classList.toggle("silent", s.muted));
  render();
})();
