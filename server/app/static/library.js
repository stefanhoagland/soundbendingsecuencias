(() => {
  "use strict";
  const form = document.getElementById("zip-upload");
  if (!form) return;
  const input = document.getElementById("zip-files");
  const list = document.getElementById("zip-list");

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
      xhr.open("POST", form.action);
      xhr.setRequestHeader("X-CSRF-Token", window.CSRF);
      xhr.setRequestHeader("X-Requested-With", "fetch");
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        bar.value = (e.loaded / e.total) * 100;
        if (e.loaded === e.total) status.textContent = "Unpacking…";
      };
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (_) {}
        const songs = data.songs || [];
        status.textContent = "";
        if (songs.length) {
          const a = document.createElement("a");
          a.href = songs[0].url;
          a.textContent = `✓ ${songs[0].title}`;
          status.appendChild(a);
          li.classList.add("ok");
        }
        if ((data.errors || []).length || !songs.length) {
          status.append(" " + ((data.errors || []).join(" ") || data.detail || "Upload failed"));
          li.classList.add("error");
        }
        resolve(songs);
      };
      xhr.onerror = () => { status.textContent = "Network error"; li.classList.add("error"); resolve([]); };
      xhr.send(body);
    });
  }

  async function uploadAll(files) {
    const zips = [...files].filter((f) => /\.zip$/i.test(f.name));
    if (zips.length < files.length) {
      const li = document.createElement("li");
      li.className = "error";
      li.textContent = "Only ZIP files can be dropped here. Add single WAVs from a song's page.";
      list.appendChild(li);
    }
    if (!zips.length) return;
    form.classList.add("busy");
    const made = [];
    for (const f of zips) made.push(...(await uploadOne(f)));
    form.classList.remove("busy");
    const hadErrors = list.querySelector("li.error");
    if (made.length === 1 && !hadErrors) location.href = made[0].url;
    else if (made.length && !hadErrors) setTimeout(() => location.reload(), 800);
  }

  input.addEventListener("change", () => uploadAll(input.files));
  ["dragenter", "dragover"].forEach((ev) =>
    form.addEventListener(ev, (e) => { e.preventDefault(); form.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    form.addEventListener(ev, (e) => { e.preventDefault(); form.classList.remove("over"); }));
  form.addEventListener("drop", (e) => uploadAll(e.dataTransfer.files));
})();
