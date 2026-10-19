// Shared by every page: navigation, footer and small helpers. No framework.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "-").replace(/[&<>"']/g, (c) =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

async function api(path, opts = {}) {
  // A page must end up showing data or a reason, never an endless placeholder.
  const r = await fetch(path, {...opts, signal: AbortSignal.timeout(60000),
    headers: {"X-Actor": "workbench", ...(opts.headers || {})}}).catch((e) => {
      throw new Error(e.name === "TimeoutError" ? "the server did not answer within a minute"
                                               : "the server is not running"); });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
  return body;
}
const post = (path, body) => api(path, {method: "POST",
  headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});

// Group the integer part only: figures are exact strings and stay exact.
const grouped = (n) => {
  if (n === null || n === undefined) return "-";
  const [i, f] = String(n).split(".");
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (f ? "." + f : "");
};
// For entered quantities only (display): 1180000.000000 -> 1,180,000
const qty = (n) => grouped(String(n).includes(".") ? String(n).replace(/\.?0+$/, "") : n);
const when = (t) => t ? new Date(t).toLocaleString("en-GB", {dateStyle: "medium", timeStyle: "short"}) : "-";
const short = (hash) => esc(String(hash).slice(0, 12));
const say = (el, text, cls = "") => { el.className = "msg " + cls; el.textContent = text; };
const kv = (pairs) => `<dl class="kv">${pairs.map(([k, v]) =>
  `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;

const PUBLIC = [["/findings", "Findings"], ["/registry", "Factor registry"], ["/method", "How it works"], ["/console", "Console"]];
const APP = [["/ledger", "Ledger"], ["/evidence", "Evidence"], ["/reports", "Reports"], ["/sampling", "Sampling"]];
const here = location.pathname.replace(/\/$/, "") || "/";
const links = (items) => items.map(([href, label]) =>
  `<a href="${href}"${href === here ? ' aria-current="page"' : ""}>${label}</a>`).join("");
const inApp = APP.some(([href]) => href === here);

document.body.insertAdjacentHTML("afterbegin", `
  <header class="nav"><div class="wrap">
    <a class="brand" href="/">CarbonX</a>
    <nav aria-label="Main">${links(PUBLIC)}</nav>
    <button class="ghost sm" id="theme" type="button"></button>
    <a class="btn primary sm" href="/ledger">Open workbench</a>
  </div></header>
  ${inApp ? `<div class="subnav"><div class="wrap">${links(APP)}
    <span class="org"><label for="org" style="margin:0">Organisation</label><select id="org"></select></span>
  </div></div>` : ""}`);
document.body.insertAdjacentHTML("beforeend", `
  <footer><div class="wrap">
    <p>CarbonX is a research prototype built at RVCE for SDG 13. It supports accredited
       verifiers in their work. It is not accredited and does not issue assurance opinions.</p>
    <p>${links([...PUBLIC, ...APP])}</p>
  </div></footer>`);

// Theme: dark unless the viewer chose light. The <head> of each page sets the
// attribute before first paint; this keeps the button and the figures in step.
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("theme", theme); } catch { /* private mode: not remembered */ }
  const btn = $("theme");
  btn.textContent = theme === "dark" ? "Light" : "Dark";
  btn.setAttribute("aria-label", `Switch to the ${theme === "dark" ? "light" : "dark"} theme`);
  document.querySelectorAll("img[data-figure]").forEach((img) => {
    img.src = `/figures/${img.dataset.figure}${theme === "dark" ? "_dark" : ""}.svg`; });
}
applyTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
$("theme").onclick = () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");

// Workbench pages share one selected organisation, kept across pages.
async function orgs() {
  const facilities = await api("/api/facilities");
  const list = [...new Map(facilities.map((f) => [f.org_id, f.organisation])).entries()];
  const sel = $("org");
  if (sel) {
    sel.innerHTML = list.map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join("");
    const saved = sessionStorage.getItem("org");
    if (saved && list.some(([id]) => String(id) === saved)) sel.value = saved;
    sel.addEventListener("change", () => { sessionStorage.setItem("org", sel.value); location.reload(); });
  }
  return {facilities, org: sel && sel.value ? +sel.value : null};
}
const unreachable = (e) => document.querySelector("main").insertAdjacentHTML("afterbegin",
  `<div class="wrap"><p class="notice bad" style="margin:24px 0">This page could not load its data: ${esc(e.message)}.</p></div>`);
