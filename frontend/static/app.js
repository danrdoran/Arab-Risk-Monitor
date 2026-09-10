/* Arab Risk Monitor — Conflict-Prevention Advisor: front-end controller. */

const state = {
  messages: [],
  indicators: [],
  countries: [],
  exploreChart: null,
  railChart: null,
  lastPayload: null,
  conversationId: null,
  railMode: "sources",
  pinRefs: [],
  pinned: new Set(),
  brief: [],
  booted: { explore: false, methodology: false, history: false },
};

const PATHWAY_COLOR = { Conflict: "#b45309", Climate: "#0e7490", Development: "#15803d", Context: "#64748b" };

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtNum(v) {
  return typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v;
}
function renderMarkdown(md) {
  return DOMPurify.sanitize(marked.parse(md || "", { breaks: true }), { ADD_ATTR: ["target", "rel"] });
}

/* ---------------------------------------------------------------- tabs */
document.getElementById("nav").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (btn) showTab(btn.dataset.tab);
});
function showTab(tab) {
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  if (tab === "risk") setTimeout(loadRisk, 30);
  if (tab === "explore" && !state.booted.explore) { state.booted.explore = true; loadExplore(); }
  if (tab === "graph") setTimeout(loadGraph, 30);
  if (tab === "methodology" && !state.booted.methodology) { state.booted.methodology = true; loadMethodology(); }
}

/* ---------------------------------------------------------------- language */
document.getElementById("langpick").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-lang]");
  if (btn) applyI18n(btn.dataset.lang);
});
document.addEventListener("langchange", () => {
  renderChips();
  if (state.messages.length === 0) renderGreeting();
  if (state.booted.methodology) loadMethodology();
  if (GRAPH.loaded) { renderLegend(); if (!GRAPH.selected) window.clearGraphSelection(); }
  if (RISK.loaded) renderRisk();
  loadBrief().then(renderRail);
});

/* ---------------------------------------------------------------- health */
async function checkHealth() {
  const dot = document.getElementById("health-dot");
  const text = document.getElementById("health-text");
  try {
    const h = await (await fetch("/api/health")).json();
    if (!h.data_loaded || !h.papers_loaded || !h.graph_loaded || !h.scores_loaded) {
      dot.className = "dot warn"; text.textContent = t("health.partial");
    } else if (!h.chat_configured) {
      dot.className = "dot warn"; text.textContent = t("health.nochat");
    } else {
      dot.className = "dot ok"; text.textContent = t("health.ready");
    }
    text.title = `retriever: ${h.retriever} · MCP: ${h.mcp_transport} · lead ${h.models?.lead} · subagent ${h.models?.subagent}`;
  } catch {
    dot.className = "dot err"; text.textContent = t("health.offline");
  }
}

/* ---------------------------------------------------------------- advisor */
const messagesEl = document.getElementById("messages");

function renderGreeting() {
  messagesEl.innerHTML = `<div class="msg bot"><div class="bubble intro md">${renderMarkdown(t("advisor.greeting"))}</div></div>`;
}
function renderChips() {
  document.getElementById("chips").innerHTML = (t("chips") || [])
    .map((c) => `<button class="chip">${escapeHtml(c)}</button>`).join("");
  document.querySelectorAll("#chips .chip").forEach((b) => b.addEventListener("click", () => sendChat(b.textContent)));
}

function addMessage(role, content, { markdown } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role === "user" ? "user" : "bot"}`;
  wrap.innerHTML = `<div class="bubble ${role === "user" ? "" : "md"}">${markdown ? renderMarkdown(content) : escapeHtml(content)}</div>`;
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
function addTyping() {
  const w = document.createElement("div");
  w.className = "msg bot"; w.id = "typing";
  w.innerHTML = `<div class="bubble"><div class="typing"><i></i><i></i><i></i></div>
     <div style="font-size:11.5px;color:var(--ink-3);padding:0 17px 10px">${escapeHtml(t("advisor.thinking"))}</div></div>`;
  messagesEl.appendChild(w);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
const removeTyping = () => document.getElementById("typing")?.remove();

const input = document.getElementById("chat-input");
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
document.getElementById("chat-send").addEventListener("click", submit);
function submit() {
  const v = input.value.trim();
  if (v) sendChat(v);
}

async function sendChat(text) {
  input.value = ""; input.style.height = "auto";
  addMessage("user", text);
  state.messages.push({ role: "user", content: text });
  addTyping();
  document.getElementById("chat-send").disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.messages, lang: LANG, conversation_id: state.conversationId, persist: true }),
    });
    removeTyping();
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      addMessage("assistant", "⚠️ " + (err.detail || t("advisor.error")));
      return;
    }
    const data = await res.json();
    state.messages.push({ role: "assistant", content: data.reply });
    addMessage("assistant", data.reply, { markdown: true });
    state.lastPayload = data;
    if (data.conversation_id && data.conversation_id !== state.conversationId) {
      state.conversationId = data.conversation_id;
      loadHistory();
    }
    state.railMode = "sources";
    syncRailTabs();
    renderRail();
  } catch (e) {
    removeTyping();
    addMessage("assistant", "⚠️ " + t("advisor.offline"));
  } finally {
    document.getElementById("chat-send").disabled = false;
  }
}

/* ---------------------------------------------------------------- history */
document.getElementById("history-toggle").addEventListener("click", () =>
  document.getElementById("history").classList.toggle("collapsed")
);
document.getElementById("new-conv").addEventListener("click", () => {
  state.conversationId = null;
  state.messages = [];
  state.lastPayload = null;
  renderGreeting();
  loadBrief().then(renderRail);
  document.querySelectorAll(".conv").forEach((c) => c.classList.remove("active"));
});

async function loadHistory() {
  const list = document.getElementById("history-list");
  const convs = await fetch("/api/conversations").then((r) => r.json()).catch(() => []);
  if (!convs.length) {
    list.innerHTML = `<p class="rail-empty" style="padding:10px">${escapeHtml(t("history.empty"))}</p>`;
    return;
  }
  list.innerHTML = convs
    .map(
      (c) => `<div class="conv ${c.id === state.conversationId ? "active" : ""}" data-cid="${c.id}">
        <span class="txt">${escapeHtml(c.title || t("history.untitled"))}</span>
        <button class="del" data-del="${c.id}" title="${escapeHtml(t("brief.remove"))}">✕</button>
      </div>`
    )
    .join("");
  list.querySelectorAll(".conv").forEach((el) =>
    el.addEventListener("click", (e) => {
      if (e.target.closest("[data-del]")) return;
      openConversation(el.dataset.cid);
    })
  );
  list.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      await fetch("/api/conversations/" + b.dataset.del, { method: "DELETE" });
      if (b.dataset.del === state.conversationId) document.getElementById("new-conv").click();
      loadHistory();
    })
  );
}

async function openConversation(cid) {
  const conv = await fetch("/api/conversations/" + cid).then((r) => r.json()).catch(() => null);
  if (!conv) return;
  state.conversationId = cid;
  state.messages = conv.messages.map((m) => ({ role: m.role, content: m.content }));
  messagesEl.innerHTML = "";
  let lastPayload = null;
  conv.messages.forEach((m) => {
    addMessage(m.role === "user" ? "user" : "assistant", m.content, { markdown: m.role !== "user" });
    if (m.payload) lastPayload = m.payload;
  });
  state.lastPayload = lastPayload;
  state.railMode = "sources";
  syncRailTabs();
  await loadBrief();
  renderRail();
  loadHistory();
}

/* ---------------------------------------------------------------- rail */
const railTabs = document.getElementById("rail-tabs");
railTabs.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-mode]");
  if (!b) return;
  state.railMode = b.dataset.mode;
  syncRailTabs();
  if (state.railMode === "brief") loadBrief().then(renderRail);
  else renderRail();
});
function syncRailTabs() {
  railTabs.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.mode === state.railMode));
}

function renderRail() {
  const el = document.getElementById("rail-body");
  if (state.railMode === "brief") return renderBrief(el);

  const data = state.lastPayload;
  if (!data) {
    el.innerHTML = `<p class="rail-empty">${escapeHtml(t("advisor.rail.empty"))}</p>`;
    return;
  }
  state.pinRefs = [];
  const parts = [];
  const rows = data.chart_rows || [];
  if (rows.length) parts.push(`<div class="rail-sec"><div class="rail-chart"><canvas id="rail-chart" height="150"></canvas></div></div>`);

  if ((data.paper_citations || []).length) {
    parts.push(section(t("advisor.rail.guidance"),
      data.paper_citations.map((p) => srcCard("passage", {
        citation: p.citation, section: p.section, snippet: (p.snippet || "").slice(0, 240),
        url: p.url, doc_short_title: p.doc_short_title, page: p.page,
      }, `<div class="t">${escapeHtml(p.citation || "")}</div>
        <div class="m">${escapeHtml(p.section || "")}</div>
        ${p.snippet ? `<div class="snip">“${escapeHtml(p.snippet.slice(0, 220))}…”</div>` : ""}
        <div class="row"><a href="${p.url}" target="_blank" rel="noopener">${escapeHtml(p.doc_short_title || "source")} ↗</a>
          <span class="pill">${escapeHtml(t("common.page"))} ${escapeHtml(String(p.page ?? ""))}</span></div>`)).join("")));
  }

  const cites = dedupeData(data.citations || []);
  if (cites.length) {
    parts.push(section(t("advisor.rail.data"),
      cites.slice(0, 40).map((c) => srcCard("data", c,
        `<div class="t">${escapeHtml(c.indicator_label || "")} ${c.country_name ? "· " + escapeHtml(c.country_name) : ""} ${c.year ? "· " + c.year : ""}</div>
        <div class="m">${c.value != null ? "<b>" + fmtNum(c.value) + "</b> " + escapeHtml(c.unit || "") : ""}</div>
        <div class="row"><a href="${c.source_url}" target="_blank" rel="noopener">${escapeHtml(c.source_name || "")} ↗</a>
          <span>${escapeHtml(t("common.retrieved"))} ${c.retrieved_at ? String(c.retrieved_at).slice(0, 10) : ""}</span></div>`)).join("")));
  }

  const scores = (data.score_rows || []).filter((s) => s.risk != null || s.vulnerability != null);
  if (scores.length) {
    parts.push(section(t("advisor.rail.scores"),
      scores.slice(0, 24).map((s) => srcCard("score", s,
        `<div class="t">${escapeHtml(s.country_name || s.country_iso3 || "")} · ${escapeHtml(s.pathway || "")} ${s.year ? "· " + s.year : ""}</div>
        <div class="m">${s.risk != null ? "risk <b>" + Number(s.risk).toFixed(2) + "</b>" : ""}
          ${s.vulnerability != null ? " · vuln " + Number(s.vulnerability).toFixed(2) : ""}
          ${s.resilience != null ? " · resil " + Number(s.resilience).toFixed(2) : ""}</div>`)).join("")));
  }

  const gnodes = (data.graph_context?.nodes || []).filter((n) => n.type !== "paper");
  if (gnodes.length) {
    parts.push(section(t("advisor.rail.graph"),
      `<div>${gnodes.slice(0, 24).map((n, i) => {
        const idx = state.pinRefs.push({ kind: "graph_node", ref: { id: n.id, label: n.label, type: n.type, summary: n.summary } }) - 1;
        return `<span class="gnode" data-node="${escapeHtml(n.id)}"><span class="swatch" style="background:${NODE_COLOR[n.type] || "#64748b"}"></span>${escapeHtml(n.label)}<button class="pin ${state.pinned.has("graph_node:" + n.id) ? "done" : ""}" data-pin="${idx}" title="${escapeHtml(t("advisor.rail.pin"))}">📌</button></span>`;
      }).join("")}</div>`));
  }

  if ((data.trace || []).length) {
    parts.push(`<div class="rail-sec trace"><details><summary>${escapeHtml(t("advisor.rail.trace"))}</summary>` +
      data.trace.map((s) => `<div style="margin-top:6px"><b>${escapeHtml(s.specialist)}</b> — ${escapeHtml(s.question || "")}
        ${(s.tools_used || []).map((x) => `<code>${escapeHtml(x)}</code>`).join("")}</div>`).join("") +
      `<div style="margin-top:6px;opacity:.7">lead ${escapeHtml(data.models?.lead || "")} · subagents ${escapeHtml(data.models?.subagent || "")} · ${escapeHtml(data.models?.transport || "")}</div></details></div>`);
  }

  el.innerHTML = parts.join("") || `<p class="rail-empty">${escapeHtml(t("advisor.rail.empty"))}</p>`;
  wireRail(el);
  if (rows.length) drawRailChart(rows);
}

function section(title, inner) {
  return `<div class="rail-sec"><h3>${escapeHtml(title)}</h3>${inner}</div>`;
}
function srcCard(kind, ref, inner) {
  const idx = state.pinRefs.push({ kind, ref }) - 1;
  const key = pinKey(kind, ref);
  return `<div class="src"><button class="pin ${state.pinned.has(key) ? "done" : ""}" data-pin="${idx}" title="${escapeHtml(t("advisor.rail.pin"))}">📌</button>${inner}</div>`;
}
function pinKey(kind, ref) {
  if (kind === "passage") return "passage:" + ref.citation + ref.section;
  if (kind === "data") return `data:${ref.indicator_id}:${ref.country_iso3}:${ref.year}`;
  if (kind === "score") return `score:${ref.country_iso3}:${ref.pathway}:${ref.year}`;
  if (kind === "graph_node") return "graph_node:" + ref.id;
  return kind + ":" + JSON.stringify(ref).slice(0, 40);
}

function wireRail(el) {
  el.querySelectorAll("[data-node]").forEach((b) =>
    b.addEventListener("click", (e) => {
      if (e.target.closest(".pin")) return;
      showTab("graph"); setTimeout(() => selectNode(b.dataset.node), 120);
    })
  );
  el.querySelectorAll(".pin").forEach((b) =>
    b.addEventListener("click", async (e) => {
      e.stopPropagation();
      const { kind, ref } = state.pinRefs[+b.dataset.pin];
      const key = pinKey(kind, ref);
      if (state.pinned.has(key)) return;
      await fetch("/api/brief", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, ref, conversation_id: state.conversationId }),
      });
      state.pinned.add(key);
      b.classList.add("done");
      loadBrief();
    })
  );
}

function dedupeData(cites) {
  const seen = new Set();
  return cites.filter((c) => {
    const k = `${c.indicator_id}|${c.country_iso3}|${c.year}`;
    if (seen.has(k)) return false;
    seen.add(k); return true;
  });
}

function drawRailChart(rows) {
  const canvas = document.getElementById("rail-chart");
  if (!canvas) return;
  if (state.railChart) state.railChart.destroy();
  const series = new Map();
  for (const r of rows) {
    const key = `${r.indicator_label} · ${r.country_name}`;
    if (!series.has(key)) series.set(key, []);
    series.get(key).push({ x: r.year, y: r.value });
  }
  const palette = ["#0f766e", "#b45309", "#0e7490", "#6d28d9", "#be185d", "#15803d", "#ca8a04", "#334155"];
  state.railChart = new Chart(canvas, {
    type: "line",
    data: {
      datasets: [...series.entries()].slice(0, 6).map(([label, pts], i) => ({
        label, data: pts.sort((a, b) => a.x - b.x),
        borderColor: palette[i % palette.length], backgroundColor: palette[i % palette.length],
        tension: 0.25, pointRadius: 2, borderWidth: 1.5,
      })),
    },
    options: {
      responsive: true,
      plugins: { legend: { display: series.size > 1, labels: { font: { size: 9 }, boxWidth: 8 } } },
      scales: {
        x: {
          type: "linear",
          ticks: {
            stepSize: 1,
            format: { useGrouping: false },
            font: { size: 9 },
          },
        },
        y: { ticks: { font: { size: 9 } } },
      },
    },
  });
}

/* ---------------------------------------------------------------- brief */
async function loadBrief() {
  const q = state.conversationId ? "?conversation_id=" + state.conversationId : "";
  state.brief = await fetch("/api/brief" + q).then((r) => r.json()).catch(() => []);
  state.pinned = new Set(state.brief.map((it) => pinKey(it.kind, it.ref)));
  const countBtn = railTabs.querySelector('[data-mode="brief"]');
  countBtn.textContent = t("advisor.rail.brief") + (state.brief.length ? ` (${state.brief.length})` : "");
}

function renderBrief(el) {
  if (!state.brief.length) {
    el.innerHTML = `<div class="brief-actions">
        <button id="brief-export">${escapeHtml(t("brief.export"))}</button>
        <button id="brief-copy">${escapeHtml(t("brief.copy"))}</button></div>
      <p class="rail-empty">${escapeHtml(t("brief.empty"))}</p>`;
    wireBriefActions(el);
    return;
  }
  const groups = { passage: t("advisor.rail.guidance"), data: t("advisor.rail.data"), score: t("advisor.rail.scores"), graph_node: t("advisor.rail.graph") };
  const body = Object.entries(groups).map(([kind, heading]) => {
    const items = state.brief.filter((it) => it.kind === kind);
    if (!items.length) return "";
    return `<div class="rail-sec"><h3>${escapeHtml(heading)}</h3>` + items.map(briefItem).join("") + `</div>`;
  }).join("");
  el.innerHTML = `<div class="brief-actions">
      <button id="brief-export">${escapeHtml(t("brief.export"))}</button>
      <button id="brief-copy">${escapeHtml(t("brief.copy"))}</button></div>` + body;
  wireBriefActions(el);
  el.querySelectorAll("[data-brief-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      await fetch("/api/brief/" + b.dataset.briefDel, { method: "DELETE" });
      loadBrief().then(() => renderBrief(el));
    })
  );
  el.querySelectorAll("[data-brief-note]").forEach((ta) => {
    let tmo;
    ta.addEventListener("input", () => {
      clearTimeout(tmo);
      tmo = setTimeout(() => {
        fetch("/api/brief/" + ta.dataset.briefNote, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: ta.value }),
        });
      }, 500);
    });
  });
}

function briefItem(it) {
  const r = it.ref;
  let head = "";
  if (it.kind === "passage") head = `<div class="t">${escapeHtml(r.citation || "")}</div><div class="m">${escapeHtml(r.section || "")}</div>`;
  else if (it.kind === "data") head = `<div class="t">${escapeHtml(r.indicator_label || "")} · ${escapeHtml(r.country_name || "")} ${r.year || ""}</div><div class="m">${fmtNum(r.value)} ${escapeHtml(r.unit || "")}</div>`;
  else if (it.kind === "score") head = `<div class="t">${escapeHtml(r.country_name || "")} · ${escapeHtml(r.pathway || "")} ${r.year || ""}</div><div class="m">risk ${r.risk != null ? Number(r.risk).toFixed(2) : "—"}</div>`;
  else head = `<div class="t">${escapeHtml(r.label || "")}</div><div class="m">${escapeHtml((r.summary || "").slice(0, 120))}</div>`;
  return `<div class="brief-item">
    <button class="del" data-brief-del="${it.id}">✕</button>
    ${head}
    <textarea data-brief-note="${it.id}" placeholder="${escapeHtml(t("brief.note_ph"))}">${escapeHtml(it.note || "")}</textarea>
  </div>`;
}

function wireBriefActions(el) {
  const q = state.conversationId ? "?conversation_id=" + state.conversationId : "";
  el.querySelector("#brief-export")?.addEventListener("click", async () => {
    const md = await fetch("/api/brief/export" + q).then((r) => r.text());
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "conflict-prevention-brief.md";
    a.click();
    URL.revokeObjectURL(a.href);
  });
  el.querySelector("#brief-copy")?.addEventListener("click", async (e) => {
    const md = await fetch("/api/brief/export" + q).then((r) => r.text());
    await navigator.clipboard.writeText(md);
    e.target.textContent = t("brief.copied");
    setTimeout(() => (e.target.textContent = t("brief.copy")), 1500);
  });
}

window.askAdvisorAbout = function (topic) {
  showTab("advisor");
  const phrasing = {
    en: `What does the evidence say about "${topic}", and which prevention levers address it?`,
    fr: `Que disent les preuves sur « ${topic} », et quels leviers de prévention y répondent ?`,
    ar: `ماذا تقول الأدلة عن «${topic}»، وما أدوات المنع التي تعالجه؟`,
  };
  sendChat(phrasing[LANG] || phrasing.en);
};

/* ---------------------------------------------------------------- explore */
async function loadExplore() {
  const [inds, countries] = await Promise.all([
    fetch("/api/indicators").then((r) => r.json()),
    fetch("/api/countries").then((r) => r.json()),
  ]);
  state.indicators = inds;
  state.countries = countries;
  const sel = document.getElementById("sel-indicator");
  sel.innerHTML = inds.map((i) => `<option value="${escapeHtml(i.indicator_id)}">${escapeHtml(i.pathway)} · ${escapeHtml(i.indicator_label)}</option>`).join("");
  sel.addEventListener("change", () => { updateIndicatorMeta(); runExplore(); });

  const list = document.getElementById("country-list");
  list.innerHTML = countries.map((c) => `<label><input type="checkbox" class="cc" value="${c.country_iso3}" />${escapeHtml(c.country_name)}</label>`).join("");
  ["JOR", "LBN", "TUN", "EGY", "MAR"].forEach((d) => {
    const cb = list.querySelector(`.cc[value="${d}"]`);
    if (cb) cb.checked = true;
  });
  list.querySelectorAll(".cc").forEach((cb) => cb.addEventListener("change", runExplore));
  updateIndicatorMeta();
  runExplore();
}
function updateIndicatorMeta() {
  const id = document.getElementById("sel-indicator").value;
  const ind = state.indicators.find((i) => i.indicator_id === id);
  if (!ind) return;
  document.getElementById("indicator-meta").innerHTML =
    `<b>${escapeHtml(ind.risk_measure)}</b> · ${escapeHtml(ind.theme)}<br/>${escapeHtml(ind.variable)}<br/>
     <span style="color:var(--ink-3)">${escapeHtml(t("explore.col.source"))}: ${escapeHtml(ind.source_name)} — ${escapeHtml(ind.source_dataset)}</span>`;
}
async function runExplore() {
  const id = document.getElementById("sel-indicator").value;
  const sel = [...document.querySelectorAll(".cc:checked")].map((c) => c.value);
  if (!id || !sel.length) return;
  const rows = await fetch(`/api/data?indicator_ids=${encodeURIComponent(id)}&countries=${sel.join(",")}`).then((r) => r.json());
  const byCountry = new Map();
  for (const r of rows) {
    if (!byCountry.has(r.country_name)) byCountry.set(r.country_name, []);
    byCountry.get(r.country_name).push({ x: r.year, y: r.value });
  }
  const palette = ["#0f766e", "#b45309", "#0e7490", "#6d28d9", "#be185d", "#15803d", "#ca8a04"];
  if (state.exploreChart) state.exploreChart.destroy();
  state.exploreChart = new Chart(document.getElementById("explore-chart"), {
    type: "line",
    data: { datasets: [...byCountry.entries()].map(([label, pts], i) => ({
      label, data: pts.sort((a, b) => a.x - b.x), borderColor: palette[i % palette.length], tension: 0.25, pointRadius: 2, borderWidth: 1.5,
    })) },
    options: { responsive: true, scales: { x: { type: "linear", ticks: { stepSize: 2, format: { useGrouping: false } } } } },
  });
  const src = rows[0] || {};
  const latest = [...byCountry.entries()].map(([name, pts]) => { const s = pts.sort((a, b) => b.x - a.x); return { name, ...s[0] }; });
  document.getElementById("explore-table").innerHTML = latest.map((r) => `<tr>
      <td>${escapeHtml(r.name)}</td><td class="num">${r.x}</td><td class="num">${fmtNum(r.y)}</td>
      <td><a href="${src.source_url || "#"}" target="_blank" rel="noopener">${escapeHtml(src.source_name || "")} ↗</a></td></tr>`).join("");
}
window.openExploreIndicator = function (indicatorId) {
  showTab("explore");
  const go = () => {
    const sel = document.getElementById("sel-indicator");
    if (!sel || !sel.options.length) return setTimeout(go, 120);
    sel.value = indicatorId; updateIndicatorMeta(); runExplore();
  };
  if (!state.booted.explore) { state.booted.explore = true; loadExplore().then(go); } else go();
};

/* ---------------------------------------------------------------- graph search */
document.getElementById("graph-search").addEventListener("input", (e) => focusGraph(e.target.value));

/* ---------------------------------------------------------------- methodology */
async function loadMethodology() {
  const papers = await fetch("/api/papers").then((r) => r.json()).catch(() => []);
  const roleLabel = { "prevention-evidence": "Prevention evidence base", framework: "Risk framework" };
  document.getElementById("doc-inner").innerHTML = `
    <h2>${escapeHtml(t("doc.title"))}</h2>
    <p>${t("doc.intro")}</p>
    <h3>${escapeHtml(t("doc.arch.title"))}</h3><p>${t("doc.arch.body")}</p>
    <h3>${escapeHtml(t("doc.graph.title"))}</h3><p>${t("doc.graph.body")}</p>
    <h3>${escapeHtml(t("doc.data.title"))}</h3><p>${t("doc.data.body")}</p>
    <h3>${escapeHtml(t("doc.sources.title"))}</h3>
    <div class="papers">${papers.map((p) => `
      <div class="paper">
        <div class="role">${escapeHtml(roleLabel[p.role] || p.role)}</div>
        <h4><a href="${p.url}" target="_blank" rel="noopener">${escapeHtml(p.title)} ↗</a></h4>
        <p>${escapeHtml(p.authors)} · ${p.year} · ${escapeHtml(p.publisher)} · ${p.chunk_count} passages indexed</p>
      </div>`).join("")}</div>`;
}

/* ---------------------------------------------------------------- init */
applyI18n(LANG);
renderChips();
renderGreeting();
checkHealth();
loadHistory();
loadBrief();
