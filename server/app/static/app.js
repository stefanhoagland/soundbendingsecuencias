// Translate a string the scripts show: T("Loading {n}", { n: 3 }). window.I18N holds the Spanish.
window.T = (text, vars) => {
  let out = (window.I18N && window.I18N[text]) || text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(v);
  return out;
};

// Confirm destructive forms: <form data-confirm="Are you sure?">
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset && e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});

// Phone menu: the ☰ button in the top bar opens and closes the links.
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".menu-btn");
  if (!btn) return;
  const open = btn.closest(".topbar").classList.toggle("open");
  btn.setAttribute("aria-expanded", String(open));
});
