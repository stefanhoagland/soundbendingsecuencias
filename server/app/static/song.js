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
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) bar.value = (e.loaded / e.total) * 100; };
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (_) {}
        if (xhr.status === 200 && !(data.errors || []).length) {
          bar.value = 100; status.textContent = "✓"; li.classList.add("ok");
        } else {
          status.textContent = (data.errors && data.errors.join(" ")) || data.detail || "Upload failed";
          li.classList.add("error");
        }
        resolve(xhr.status === 200);
      };
      xhr.onerror = () => { status.textContent = "Network error"; li.classList.add("error"); resolve(false); };
      xhr.send(body);
    });
  }

  async function uploadAll(files) {
    const wavs = [...files].filter((f) => /\.wav$/i.test(f.name) || /wav/.test(f.type));
    const skipped = files.length - wavs.length;
    if (skipped) {
      const li = document.createElement("li");
      li.className = "error";
      li.textContent = `Skipped ${skipped} file(s) that aren't WAV.`;
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

  // ---------- Preview player ----------
  const mixer = document.getElementById("mixer");
  if (!mixer) return;

  const playBtn = document.getElementById("play");
  const stopBtn = document.getElementById("stop");
  const clock = document.getElementById("clock");
  const timeline = document.getElementById("timeline");
  const progress = document.getElementById("progress");
  let ctx = null;
  let playing = false;

  const strips = [...mixer.querySelectorAll(".strip")].map((el) => {
    const audio = new Audio();
    audio.preload = "auto";
    audio.src = el.dataset.src;
    return {
      el, audio,
      gainDb: parseFloat(el.dataset.gain) || 0,
      pan: parseFloat(el.dataset.pan) || 0,
      muted: el.dataset.muted === "1",
      solo: false,
      gain: null, panner: null,
    };
  });

  const master = () => strips.reduce((a, b) => (b.audio.duration > (a.audio.duration || 0) ? b : a), strips[0]);
  const duration = () => Math.max(0, ...strips.map((s) => s.audio.duration || 0));

  function ensureGraph() {
    if (ctx) return;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    for (const s of strips) {
      const src = ctx.createMediaElementSource(s.audio);
      s.gain = ctx.createGain();
      s.panner = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
      src.connect(s.gain);
      (s.panner ? s.gain.connect(s.panner) : null);
      (s.panner || s.gain).connect(ctx.destination);
      if (s.panner) s.panner.pan.value = s.pan;
    }
    applyMix();
  }

  function applyMix() {
    const anySolo = strips.some((s) => s.solo);
    for (const s of strips) {
      const audible = anySolo ? s.solo : !s.muted;
      if (s.gain) s.gain.gain.value = audible ? Math.pow(10, s.gainDb / 20) : 0;
      s.el.classList.toggle("silent", !audible);
    }
  }

  function fmt(t) {
    t = Math.max(0, t || 0);
    return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  }

  function seek(t) {
    for (const s of strips) {
      const d = s.audio.duration || Infinity;
      try { s.audio.currentTime = Math.min(t, d); } catch (_) {}
    }
    render();
  }

  async function play() {
    ensureGraph();
    if (ctx.state === "suspended") await ctx.resume();
    const t = master().audio.currentTime;
    seek(t);
    await Promise.allSettled(strips.map((s) => (s.audio.currentTime < (s.audio.duration || Infinity) ? s.audio.play() : null)));
    playing = true;
    playBtn.textContent = "❚❚";
    requestAnimationFrame(tick);
  }

  function pause() {
    strips.forEach((s) => s.audio.pause());
    playing = false;
    playBtn.textContent = "▶";
  }

  function render() {
    const t = master().audio.currentTime;
    const d = duration();
    clock.textContent = fmt(t);
    progress.style.width = d ? `${(t / d) * 100}%` : "0";
  }

  let lastSync = 0;
  function tick(now) {
    if (!playing) return;
    const m = master().audio;
    // Element players drift apart slowly; nudge stragglers back in line.
    if (now - lastSync > 1000) {
      lastSync = now;
      for (const s of strips) {
        if (s.audio === m || s.audio.ended) continue;
        if (Math.abs(s.audio.currentTime - m.currentTime) > 0.04) s.audio.currentTime = m.currentTime;
      }
    }
    render();
    if (m.ended) { pause(); seek(0); return; }
    requestAnimationFrame(tick);
  }

  playBtn.addEventListener("click", () => (playing ? pause() : play()));
  stopBtn.addEventListener("click", () => { pause(); seek(0); });
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName)) {
      e.preventDefault();
      playing ? pause() : play();
    }
  });

  timeline.addEventListener("click", (e) => {
    if (e.target.classList.contains("marker")) return;
    const r = timeline.getBoundingClientRect();
    seek(((e.clientX - r.left) / r.width) * duration());
  });
  document.querySelectorAll("[data-time]").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.preventDefault();
      seek(parseFloat(b.dataset.time));
      document.getElementById("player").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));

  const useTime = document.getElementById("use-time");
  if (useTime) useTime.addEventListener("click", () => {
    const t = master().audio.currentTime;
    document.getElementById("section-start").value = `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;
  });

  for (const s of strips) {
    const fader = s.el.querySelector(".fader");
    const db = s.el.querySelector(".db");
    const muteBtn = s.el.querySelector(".mute");
    const soloBtn = s.el.querySelector(".solo");
    fader.addEventListener("input", () => {
      s.gainDb = parseFloat(fader.value);
      db.textContent = `${s.gainDb >= 0 ? "+" : ""}${s.gainDb.toFixed(1)} dB`;
      applyMix();
    });
    muteBtn.addEventListener("click", () => { s.muted = !s.muted; muteBtn.classList.toggle("on", s.muted); applyMix(); });
    soloBtn.addEventListener("click", () => { s.solo = !s.solo; soloBtn.classList.toggle("on", s.solo); applyMix(); });
    s.audio.addEventListener("loadedmetadata", render);
  }
  applyMix();
})();
