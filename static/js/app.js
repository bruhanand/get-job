/* get-job dashboard — vanilla JS, no frameworks. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STATUS_META = {
  to_apply: { label: "To Apply", dot: "bg-sky-400", chip: "bg-sky-500/15 text-sky-300" },
  applied: { label: "Applied", dot: "bg-indigo-400", chip: "bg-indigo-500/15 text-indigo-300" },
  interviewing: { label: "Interviewing", dot: "bg-amber-400", chip: "bg-amber-500/15 text-amber-300" },
  offer: { label: "Offer", dot: "bg-emerald-400", chip: "bg-emerald-500/15 text-emerald-300" },
  rejected: { label: "Rejected", dot: "bg-rose-400", chip: "bg-rose-500/15 text-rose-300" },
};

const SOURCE_COLORS = {
  remoteok: "bg-rose-500/15 text-rose-300",
  weworkremotely: "bg-sky-500/15 text-sky-300",
  remotive: "bg-violet-500/15 text-violet-300",
  jobicy: "bg-emerald-500/15 text-emerald-300",
  himalayas: "bg-cyan-500/15 text-cyan-300",
  arbeitnow: "bg-orange-500/15 text-orange-300",
  workingnomads: "bg-lime-500/15 text-lime-300",
  hackernews: "bg-amber-500/15 text-amber-300",
};

const state = {
  jobs: [],
  tracked: [],
  sources: [],
  filters: { q: "", date: "all", source: "", sort: "match" },
  charts: {},
};

/* ------------------------------------------------------------ helpers --- */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

function toast(msg, kind = "info", ms = 4200) {
  const colors = { info: "border-indigo-500/40", ok: "border-emerald-500/40", warn: "border-amber-500/40", err: "border-rose-500/40" };
  const el = document.createElement("div");
  el.className = `toast rounded-lg border ${colors[kind]} bg-slate-900/95 px-4 py-3 text-sm text-slate-200 shadow-xl`;
  el.innerHTML = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function relTime(iso) {
  if (!iso) return "—";
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 31) return `${days}d ago`;
  return then.toLocaleDateString();
}

const debounce = (fn, ms) => {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
};

/* --------------------------------------------------------------- tabs --- */

function showTab(name) {
  $$("#tabs .tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$("main > section").forEach((s) => s.classList.toggle("hidden", s.dataset.panel !== name));
  if (name === "analytics") loadAnalytics();
}

$("#tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (btn) showTab(btn.dataset.tab);
});

/* ------------------------------------------------------------- scraper --- */

function matchBadge(job) {
  if (job.match_score === null || job.match_score === undefined) {
    return `<span class="text-[11px] rounded-full border border-dashed border-slate-700 px-2.5 py-1 text-slate-500"
                  title="Add your resume in the Profile tab to unlock match scoring">no profile</span>`;
  }
  const s = job.match_score;
  const cls = s >= 70 ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
    : s >= 40 ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
    : "bg-slate-800 text-slate-400 border-slate-700";
  const kw = (job.matched_keywords || []).slice(0, 6).join(", ");
  return `<span class="text-xs font-bold rounded-full border px-2.5 py-1 ${cls}" title="${esc(kw ? "Matched: " + kw : "No keyword overlap")}">${s}% match</span>`;
}

function jobCard(job) {
  const src = state.sources.find((s) => s.key === job.source);
  const srcCls = SOURCE_COLORS[job.source] || "bg-slate-800 text-slate-300";
  const tags = (job.tags || []).slice(0, 6)
    .map((t) => `<span class="rounded bg-slate-800/80 px-1.5 py-0.5 text-[11px] text-slate-400">${esc(t)}</span>`).join(" ");
  const kw = (job.matched_keywords || []).slice(0, 5)
    .map((t) => `<span class="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[11px] text-indigo-300">${esc(t)}</span>`).join(" ");
  return `
  <article class="rounded-xl border border-slate-800 bg-slate-900 p-4 hover:border-slate-700 transition group" data-job-id="${job.id}">
    <div class="flex flex-wrap items-start gap-2">
      <div class="min-w-0 flex-1">
        <button class="job-open text-left font-semibold text-slate-100 hover:text-indigo-300 transition leading-snug">${esc(job.title)}</button>
        <p class="text-sm text-slate-400 mt-0.5 truncate">
          <span class="font-medium text-slate-300">${esc(job.company || "—")}</span>
          ${job.location ? ` · ${esc(job.location)}` : ""}
          ${job.salary ? ` · <span class="text-emerald-300">${esc(job.salary)}</span>` : ""}
        </p>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        ${matchBadge(job)}
        <span class="text-[11px] rounded-full px-2.5 py-1 ${srcCls}">${esc(src ? src.label : job.source)}</span>
        <span class="text-[11px] text-slate-500" title="${esc(job.posted_at || "")}">${relTime(job.posted_at)}</span>
      </div>
    </div>
    ${job.snippet ? `<p class="mt-2 text-[13px] text-slate-500 line-clamp-2">${esc(job.snippet)}</p>` : ""}
    <div class="mt-3 flex flex-wrap items-center gap-1.5">
      ${kw}${kw && tags ? `<span class="text-slate-700">·</span>` : ""}${tags}
      <span class="ml-auto flex gap-2">
        <a href="${esc(job.url)}" target="_blank" rel="noopener"
           class="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-indigo-500">Open ↗</a>
        ${job.tracked
          ? `<span class="rounded-lg bg-emerald-500/10 border border-emerald-500/30 px-3 py-1.5 text-xs font-semibold text-emerald-300">✓ Tracked</span>`
          : `<button class="job-track rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white transition">📌 Track This Job</button>`}
      </span>
    </div>
  </article>`;
}

async function loadJobs() {
  const f = state.filters;
  const params = new URLSearchParams();
  if (f.q) params.set("q", f.q);
  if (f.date !== "all") params.set("date", f.date);
  if (f.source) params.set("source", f.source);
  params.set("sort", f.sort);
  try {
    const data = await api(`/api/jobs?${params}`);
    state.jobs = data.jobs;
    $("#jobs-list").innerHTML = state.jobs.map(jobCard).join("");
    $("#jobs-empty").classList.toggle("hidden", state.jobs.length > 0);
    $("#job-count-pill").textContent = `${data.total} jobs in feed`;
  } catch (err) {
    toast(`Couldn't load jobs: ${esc(err.message)}`, "err");
  }
}

async function loadSources() {
  try {
    const data = await api("/api/sources");
    state.sources = data.sources;
    const sel = $("#source-filter");
    const current = sel.value;
    sel.innerHTML = `<option value="">All sources</option>` +
      state.sources.map((s) => `<option value="${s.key}">${esc(s.label)}</option>`).join("");
    sel.value = current;
    $("#source-chips").innerHTML = state.sources.map((s) => {
      const status = s.last_status === "ok" ? `✓ ${s.last_count}` : s.last_status === "error" ? "⚠" : "·";
      const cls = s.last_status === "error" ? "border-rose-500/40 text-rose-300"
        : s.last_status === "ok" ? "border-slate-700 text-slate-400" : "border-slate-800 text-slate-600";
      const tip = s.last_status === "error" ? s.last_error
        : s.last_fetched_at ? `Last pulled ${relTime(s.last_fetched_at)}` : "Never pulled";
      return `<span class="rounded-full border ${cls} px-2.5 py-1 text-[11px]" title="${esc(tip)}">${esc(s.label)} ${status}</span>`;
    }).join("");
  } catch { /* chips are cosmetic — ignore */ }
}

async function scrapeNow() {
  const btn = $("#scrape-btn");
  btn.disabled = true;
  btn.classList.add("opacity-60", "cursor-wait");
  $("#scrape-spinner").classList.remove("hidden");
  $("#scrape-label").textContent = "Scraping feeds…";
  try {
    const data = await api("/api/scrape", { method: "POST" });
    const lines = Object.values(data.sources).map((r) => {
      if (r.status === "ok") return `<div>✓ ${esc(r.label)} — ${r.added} new (${r.fetched} fetched)</div>`;
      if (r.status === "cooldown") return `<div class="text-slate-400">⏳ ${esc(r.label)} — cooldown (resting politely)</div>`;
      return `<div class="text-rose-300">✗ ${esc(r.label)} — ${esc(r.error)}</div>`;
    }).join("");
    toast(`<div class="font-semibold mb-1">Scrape finished — ${data.added} new jobs</div>${lines}`,
      data.ok_sources > 0 ? "ok" : "warn", 9000);
    await Promise.all([loadJobs(), loadSources()]);
  } catch (err) {
    toast(`Scrape failed: ${esc(err.message)}`, "err");
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-60", "cursor-wait");
    $("#scrape-spinner").classList.add("hidden");
    $("#scrape-label").textContent = "⚡ Scrape Now";
  }
}

async function trackScrapedJob(jobId, sourceEl) {
  try {
    const data = await api("/api/tracked", { method: "POST", body: { scraped_job_id: jobId } });
    if (data.duplicate) toast("Already on your board 👍", "warn");
    else toast(`Added <b>${esc(data.job.title)}</b> to <b>To Apply</b>`, "ok");
    const job = state.jobs.find((j) => j.id === jobId);
    if (job) job.tracked = true;
    if (sourceEl) {
      const card = sourceEl.closest("[data-job-id]");
      if (card && job) card.outerHTML = jobCard(job);
    }
    loadTracked();
  } catch (err) {
    toast(`Couldn't track job: ${esc(err.message)}`, "err");
  }
}

async function openJobModal(jobId) {
  try {
    const job = await api(`/api/jobs/${jobId}`);
    $("#jm-title").textContent = job.title;
    const src = state.sources.find((s) => s.key === job.source);
    $("#jm-meta").textContent = [job.company, job.location, job.salary, `via ${src ? src.label : job.source}`, relTime(job.posted_at)]
      .filter(Boolean).join(" · ");
    const badges = [
      ...(job.match_score !== null ? [`<span class="rounded-full bg-indigo-500/15 px-2.5 py-1 text-xs font-bold text-indigo-300">${job.match_score}% match</span>`] : []),
      ...(job.matched_keywords || []).map((t) => `<span class="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[11px] text-indigo-300">${esc(t)}</span>`),
      ...(job.tags || []).slice(0, 10).map((t) => `<span class="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400">${esc(t)}</span>`),
    ];
    $("#jm-badges").innerHTML = badges.join(" ");
    $("#jm-desc").textContent = job.description || "No description captured — open the original posting.";
    $("#jm-link").href = job.url || "#";
    const trackBtn = $("#jm-track");
    trackBtn.onclick = () => { trackScrapedJob(job.id); $("#job-modal").classList.add("hidden"); };
    $("#job-modal").classList.remove("hidden");
  } catch (err) {
    toast(`Couldn't open job: ${esc(err.message)}`, "err");
  }
}

$("#jobs-list").addEventListener("click", (e) => {
  const card = e.target.closest("[data-job-id]");
  if (!card) return;
  const id = Number(card.dataset.jobId);
  if (e.target.closest(".job-track")) trackScrapedJob(id, e.target);
  else if (e.target.closest(".job-open")) openJobModal(id);
});

$("#scrape-btn").addEventListener("click", scrapeNow);
$("#search-input").addEventListener("input", debounce((e) => { state.filters.q = e.target.value.trim(); loadJobs(); }, 300));
$("#date-filter").addEventListener("change", (e) => { state.filters.date = e.target.value; loadJobs(); });
$("#source-filter").addEventListener("change", (e) => { state.filters.source = e.target.value; loadJobs(); });
$("#sort-select").addEventListener("change", (e) => { state.filters.sort = e.target.value; loadJobs(); });

/* ------------------------------------------------------------- tracker --- */

function trackedCard(job) {
  const meta = STATUS_META[job.status] || STATUS_META.to_apply;
  const statusOptions = Object.entries(STATUS_META)
    .map(([k, m]) => `<option value="${k}" ${k === job.status ? "selected" : ""}>${m.label}</option>`).join("");
  return `
  <div class="kanban-card rounded-lg border border-slate-800 bg-slate-900 p-3 shadow" draggable="true" data-tracked-id="${job.id}">
    <div class="flex items-start gap-2">
      <p class="flex-1 text-sm font-semibold text-slate-100 leading-snug">${esc(job.title)}</p>
      <button class="tk-edit text-slate-500 hover:text-indigo-300 text-xs" title="Edit">✏️</button>
      <button class="tk-del text-slate-500 hover:text-rose-400 text-xs" title="Delete">🗑</button>
    </div>
    <p class="mt-0.5 text-xs text-slate-400 truncate">${esc(job.company || "—")}${job.salary_range ? ` · <span class="text-emerald-300">${esc(job.salary_range)}</span>` : ""}</p>
    ${job.notes ? `<p class="mt-1.5 text-[11px] text-slate-500 line-clamp-2 whitespace-pre-line">${esc(job.notes)}</p>` : ""}
    <div class="mt-2 flex items-center gap-2">
      <select class="tk-status field text-[11px] py-1 px-1.5 flex-1">${statusOptions}</select>
      ${job.url ? `<a href="${esc(job.url)}" target="_blank" rel="noopener" class="text-xs text-slate-500 hover:text-indigo-300" title="Open job URL">↗</a>` : ""}
    </div>
    ${job.date_applied ? `<p class="mt-1.5 text-[11px] text-slate-600">applied ${esc(job.date_applied)}</p>` : ""}
  </div>`;
}

function renderKanban() {
  const cols = Object.entries(STATUS_META).map(([key, meta]) => {
    const cards = state.tracked.filter((j) => j.status === key);
    return `
    <div class="kanban-col" data-status="${key}">
      <div class="flex items-center gap-2 px-3 py-2.5 border-b border-slate-800">
        <span class="h-2 w-2 rounded-full ${meta.dot}"></span>
        <h3 class="text-sm font-semibold text-slate-200">${meta.label}</h3>
        <span class="ml-auto text-xs text-slate-500">${cards.length}</span>
      </div>
      <div class="col-body">
        ${cards.map(trackedCard).join("") ||
          `<p class="text-center text-[11px] text-slate-700 border border-dashed border-slate-800 rounded-lg py-4">drop here</p>`}
      </div>
    </div>`;
  }).join("");
  $("#kanban").innerHTML = cols;
}

async function loadTracked() {
  try {
    const data = await api("/api/tracked");
    state.tracked = data.jobs;
    renderKanban();
  } catch (err) {
    toast(`Couldn't load tracker: ${esc(err.message)}`, "err");
  }
}

async function updateTracked(id, patch) {
  try {
    await api(`/api/tracked/${id}`, { method: "PATCH", body: patch });
    await loadTracked();
  } catch (err) {
    toast(`Update failed: ${esc(err.message)}`, "err");
    loadTracked();
  }
}

/* Drag and drop */
let dragId = null;
$("#kanban").addEventListener("dragstart", (e) => {
  const card = e.target.closest("[data-tracked-id]");
  if (!card) return;
  dragId = Number(card.dataset.trackedId);
  card.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
});
$("#kanban").addEventListener("dragend", (e) => {
  e.target.closest?.("[data-tracked-id]")?.classList.remove("dragging");
  $$(".kanban-col").forEach((c) => c.classList.remove("drag-over"));
});
$("#kanban").addEventListener("dragover", (e) => {
  const col = e.target.closest(".kanban-col");
  if (!col || dragId === null) return;
  e.preventDefault();
  $$(".kanban-col").forEach((c) => c.classList.toggle("drag-over", c === col));
});
$("#kanban").addEventListener("drop", (e) => {
  const col = e.target.closest(".kanban-col");
  if (!col || dragId === null) return;
  e.preventDefault();
  const job = state.tracked.find((j) => j.id === dragId);
  if (job && job.status !== col.dataset.status) updateTracked(dragId, { status: col.dataset.status });
  else $$(".kanban-col").forEach((c) => c.classList.remove("drag-over"));
  dragId = null;
});

$("#kanban").addEventListener("change", (e) => {
  if (!e.target.classList.contains("tk-status")) return;
  const id = Number(e.target.closest("[data-tracked-id]").dataset.trackedId);
  updateTracked(id, { status: e.target.value });
});

$("#kanban").addEventListener("click", (e) => {
  const card = e.target.closest("[data-tracked-id]");
  if (!card) return;
  const id = Number(card.dataset.trackedId);
  if (e.target.closest(".tk-del")) {
    const job = state.tracked.find((j) => j.id === id);
    if (confirm(`Remove "${job?.title}" from your board?`)) {
      api(`/api/tracked/${id}`, { method: "DELETE" })
        .then(() => { toast("Removed from board", "info"); loadTracked(); })
        .catch((err) => toast(esc(err.message), "err"));
    }
  } else if (e.target.closest(".tk-edit")) {
    openTrackedModal(id);
  }
});

/* Add / edit modal */
function fillStatusSelect() {
  $("#tm-status").innerHTML = Object.entries(STATUS_META)
    .map(([k, m]) => `<option value="${k}">${m.label}</option>`).join("");
}

function openTrackedModal(id = null) {
  fillStatusSelect();
  const job = id ? state.tracked.find((j) => j.id === id) : null;
  $("#tm-heading").textContent = job ? "Edit Job" : "Add Job";
  $("#tm-id").value = job ? job.id : "";
  $("#tm-title").value = job?.title || "";
  $("#tm-company").value = job?.company || "";
  $("#tm-salary").value = job?.salary_range || "";
  $("#tm-url").value = job?.url || "";
  $("#tm-status").value = job?.status || "to_apply";
  $("#tm-date").value = job?.date_applied || "";
  $("#tm-notes").value = job?.notes || "";
  $("#tracked-modal").classList.remove("hidden");
  $("#tm-title").focus();
}

$("#add-job-btn").addEventListener("click", () => openTrackedModal());

$("#tracked-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#tm-id").value;
  const body = {
    title: $("#tm-title").value.trim(),
    company: $("#tm-company").value.trim(),
    salary_range: $("#tm-salary").value.trim(),
    url: $("#tm-url").value.trim(),
    status: $("#tm-status").value,
    date_applied: $("#tm-date").value || null,
    notes: $("#tm-notes").value,
  };
  try {
    if (id) await api(`/api/tracked/${id}`, { method: "PATCH", body });
    else await api("/api/tracked", { method: "POST", body });
    $("#tracked-modal").classList.add("hidden");
    toast(id ? "Job updated" : "Job added to board", "ok");
    loadTracked();
  } catch (err) {
    toast(esc(err.message), "err");
  }
});

/* Modals: close buttons + backdrop click */
$$(".modal").forEach((modal) => {
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) modal.classList.add("hidden");
  });
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $$(".modal").forEach((m) => m.classList.add("hidden"));
});

/* ------------------------------------------------------------- profile --- */

async function loadProfile() {
  try {
    const p = await api("/api/profile");
    $("#resume-text").value = p.resume_text || "";
    $("#skills-text").value = p.skills || "";
    if (p.updated_at) $("#profile-meta").textContent = `Last saved ${relTime(p.updated_at)}`;
  } catch (err) {
    toast(`Couldn't load profile: ${esc(err.message)}`, "err");
  }
}

$("#save-profile-btn").addEventListener("click", async () => {
  try {
    const p = await api("/api/profile", {
      method: "PUT",
      body: { resume_text: $("#resume-text").value, skills: $("#skills-text").value },
    });
    $("#profile-meta").textContent = `Saved · ${p.term_count} terms indexed`;
    toast(`Profile saved — ${p.term_count} terms indexed. Match scores refreshed.`, "ok");
    loadJobs();
  } catch (err) {
    toast(`Save failed: ${esc(err.message)}`, "err");
  }
});

/* ----------------------------------------------------------- analytics --- */

function mkChart(id, cfg) {
  state.charts[id]?.destroy();
  state.charts[id] = new Chart($(id), cfg);
}

async function loadAnalytics() {
  let a;
  try {
    a = await api("/api/analytics");
  } catch (err) {
    toast(`Couldn't load analytics: ${esc(err.message)}`, "err");
    return;
  }
  $("#stat-total").textContent = a.total_tracked;
  $("#stat-sent").textContent = a.applications_sent;
  $("#stat-conversion").textContent = `${a.interview_conversion}%`;
  $("#stat-offers").textContent = `${a.offer_rate}%`;
  $("#analytics-empty").classList.toggle("hidden", a.total_tracked > 0);

  Chart.defaults.color = "#94a3b8";
  Chart.defaults.borderColor = "rgba(148,163,184,0.08)";
  Chart.defaults.font.family = "system-ui, sans-serif";

  mkChart("#chart-timeline", {
    type: "line",
    data: {
      labels: a.timeline.labels,
      datasets: [{
        label: "Applications sent",
        data: a.timeline.counts,
        borderColor: "#818cf8",
        backgroundColor: "rgba(99,102,241,0.18)",
        fill: true,
        tension: 0.35,
        pointRadius: a.timeline.labels.length > 30 ? 0 : 3,
        pointBackgroundColor: "#818cf8",
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 } },
        x: { ticks: { maxTicksLimit: 10 } },
      },
    },
  });

  const statusColors = { to_apply: "#38bdf8", applied: "#818cf8", interviewing: "#fbbf24", offer: "#34d399", rejected: "#fb7185" };
  mkChart("#chart-status", {
    type: "doughnut",
    data: {
      labels: Object.keys(a.by_status).map((k) => STATUS_META[k]?.label || k),
      datasets: [{
        data: Object.values(a.by_status),
        backgroundColor: Object.keys(a.by_status).map((k) => statusColors[k]),
        borderColor: "#0f172a",
        borderWidth: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 14 } } },
    },
  });
}

/* ---------------------------------------------------------------- init --- */

(async function init() {
  showTab("scraper");
  await loadSources();
  await Promise.all([loadJobs(), loadTracked(), loadProfile()]);
})();
