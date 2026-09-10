/* Knowledge-graph tab: a d3-force view of data/graph/knowledge_graph.json.
   Click a node -> inspector panel with its relationships, linked Arab Risk
   Monitor indicators, and the passages in the papers that support it. */

const GRAPH = {
  raw: null,
  sim: null,
  svg: null,
  g: null,
  nodeSel: null,
  linkSel: null,
  labelSel: null,
  selected: null,
  loaded: false,
};

const NODE_COLOR = {
  concept: "#17223b",
  pathway_element: "#6d28d9",
  arena: "#0e7490",
  risk_factor: "#b45309",
  policy_lever: "#0f766e",
  actor: "#be185d",
  indicator: "#15803d",
  paper: "#94722f",
};

const NODE_RADIUS = {
  concept: 13,
  pathway_element: 11,
  arena: 11,
  paper: 10,
  risk_factor: 8,
  policy_lever: 8,
  actor: 7,
  indicator: 6,
};

async function loadGraph() {
  if (GRAPH.loaded) return;
  const res = await fetch("/api/graph");
  if (!res.ok) {
    document.getElementById("graph-inspector").innerHTML =
      `<p class="rail-empty">${escapeHtml((await res.json().catch(() => ({}))).detail || "Graph not built. Run python etl/build_graph.py")}</p>`;
    return;
  }
  GRAPH.raw = await res.json();
  GRAPH.loaded = true;
  renderLegend();
  drawGraph();
}

function renderLegend() {
  const el = document.getElementById("graph-legend");
  el.innerHTML = Object.keys(NODE_COLOR)
    .map(
      (type) =>
        `<div><span class="swatch" style="background:${NODE_COLOR[type]}"></span>${escapeHtml(t("legend." + type))}</div>`
    )
    .join("");
}

function drawGraph() {
  const wrap = document.querySelector(".graphwrap");
  const W = wrap.clientWidth || 900;
  const H = wrap.clientHeight || 600;

  const nodes = GRAPH.raw.nodes.map((n) => ({ ...n }));
  const links = GRAPH.raw.edges.map((e) => ({ ...e }));

  const svg = d3.select("#graph-svg").attr("viewBox", [0, 0, W, H]);
  svg.selectAll("*").remove();
  const g = svg.append("g");
  GRAPH.svg = svg;
  GRAPH.g = g;

  svg.call(
    d3.zoom().scaleExtent([0.3, 3]).on("zoom", (ev) => g.attr("transform", ev.transform))
  );

  GRAPH.linkSel = g
    .append("g")
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("class", "link")
    .attr("stroke-width", 1);

  const node = g
    .append("g")
    .selectAll("g")
    .data(nodes)
    .join("g")
    .attr("class", "node")
    .call(drag())
    .on("click", (ev, d) => selectNode(d.id));

  node
    .append("circle")
    .attr("r", (d) => NODE_RADIUS[d.type] || 6)
    .attr("fill", (d) => NODE_COLOR[d.type] || "#64748b");

  node
    .append("title")
    .text((d) => `${d.label}\n${d.type}`);

  GRAPH.labelSel = node
    .append("text")
    .attr("x", (d) => (NODE_RADIUS[d.type] || 6) + 3)
    .attr("y", 3)
    .text((d) => (d.degree >= 3 || d.type === "arena" || d.type === "concept" ? d.label : ""));

  GRAPH.nodeSel = node;

  GRAPH.sim = d3
    .forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id).distance((l) => (l.rel === "measured_by" ? 45 : 90)).strength(0.4))
    .force("charge", d3.forceManyBody().strength(-260))
    .force("center", d3.forceCenter(W / 2, H / 2))
    .force("collide", d3.forceCollide().radius((d) => (NODE_RADIUS[d.type] || 6) + 10))
    .on("tick", ticked);

  function ticked() {
    GRAPH.linkSel
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);
    node.attr("transform", (d) => `translate(${d.x},${d.y})`);
  }
}

function drag() {
  return d3
    .drag()
    .on("start", (ev, d) => {
      if (!ev.active) GRAPH.sim.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    })
    .on("drag", (ev, d) => {
      d.fx = ev.x;
      d.fy = ev.y;
    })
    .on("end", (ev, d) => {
      if (!ev.active) GRAPH.sim.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    });
}

function neighbourIds(id) {
  const set = new Set([id]);
  GRAPH.raw.edges.forEach((e) => {
    if (e.source === id) set.add(e.target);
    if (e.target === id) set.add(e.source);
  });
  return set;
}

async function selectNode(id, _tries = 0) {
  if (!GRAPH.loaded || !GRAPH.nodeSel) {
    if (_tries > 40) return;
    return setTimeout(() => selectNode(id, _tries + 1), 100);
  }
  if (!GRAPH.raw.nodes.some((n) => n.id === id)) return;
  GRAPH.selected = id;
  const near = neighbourIds(id);
  GRAPH.nodeSel.classed("dim", (d) => !near.has(d.id));
  GRAPH.linkSel
    .classed("dim", (d) => d.source.id !== id && d.target.id !== id)
    .classed("hl", (d) => d.source.id === id || d.target.id === id);
  GRAPH.labelSel.text((d) => (near.has(d.id) ? d.label : d.degree >= 3 ? d.label : ""));

  const panel = document.getElementById("graph-inspector");
  panel.innerHTML = `<p class="rail-empty">…</p>`;
  const res = await fetch("/api/graph/node/" + encodeURIComponent(id));
  if (!res.ok) {
    panel.innerHTML = `<p class="rail-empty">not found</p>`;
    return;
  }
  const node = await res.json();
  panel.innerHTML = renderInspector(node);
  panel.querySelector("[data-ask]")?.addEventListener("click", () => {
    window.askAdvisorAbout(node.label);
  });
  panel.querySelectorAll("[data-goto]").forEach((b) =>
    b.addEventListener("click", () => selectNode(b.dataset.goto))
  );
  panel.querySelectorAll("[data-indicator]").forEach((b) =>
    b.addEventListener("click", () => window.openExploreIndicator(b.dataset.indicator))
  );
}

function relLabel(key) {
  const [rel, dir] = key.split(":");
  const map = {
    drives: dir === "out" ? "drives →" : "← driven by",
    mitigates: dir === "out" ? "mitigates →" : "← mitigated by",
    strengthens: dir === "out" ? "strengthens →" : "← strengthened by",
    undermines: dir === "out" ? "undermines →" : "← undermined by",
    contested_in: dir === "out" ? "contested in →" : "← contests",
    measured_by: dir === "out" ? "measured by →" : "← measures",
    monitored_by: dir === "out" ? "monitored by →" : "← monitors",
    part_of: dir === "out" ? "part of →" : "← contains",
    intersects: "intersects",
    evidence_in: "evidence in →",
    recommended_in: "recommended in →",
  };
  return map[rel] || rel;
}

function renderInspector(node) {
  const evidence = (node.evidence || [])
    .map(
      (e) => `<div class="src">
        <div class="t">${escapeHtml(e.citation)}</div>
        <div class="m">${escapeHtml(e.section || "")}</div>
        <div class="snip">“${escapeHtml((e.snippet || "").slice(0, 240))}”</div>
        <div class="row"><a href="${e.url}" target="_blank" rel="noopener">${escapeHtml(e.doc_short_title)} ↗</a></div>
      </div>`
    )
    .join("");

  const indicators = (node.indicators || [])
    .map(
      (i) => `<button class="gnode" data-indicator="${escapeHtml(i.id.replace("indicator:", ""))}">
        <span class="swatch" style="background:${NODE_COLOR.indicator}"></span>${escapeHtml(i.label)}</button>`
    )
    .join("");

  const rels = Object.entries(node.neighbors || {})
    .map(([key, list]) => {
      const items = list
        .map(
          (nb) =>
            `<button class="gnode" data-goto="${escapeHtml(nb.id)}"><span class="swatch" style="background:${NODE_COLOR[nb.type] || "#64748b"}"></span>${escapeHtml(nb.label)}</button>`
        )
        .join("");
      return `<div class="rel"><b>${escapeHtml(relLabel(key))}</b><div style="margin-top:5px">${items}</div></div>`;
    })
    .join("");

  return `
    <button class="close" onclick="window.clearGraphSelection()">✕</button>
    <div class="kicker" style="color:${NODE_COLOR[node.type] || "#64748b"}">${escapeHtml(t("legend." + node.type))}</div>
    <h2>${escapeHtml(node.label)}</h2>
    <div class="body">${escapeHtml(node.summary || "")}</div>
    ${node.status === "planned" ? `<div class="body" style="color:var(--accent);margin-top:6px">${escapeHtml(t("common.planned"))}</div>` : ""}
    <button class="linkbtn" data-ask>${escapeHtml(t("graph.ask"))}</button>
    ${indicators ? `<h4>${escapeHtml(t("graph.indicators"))}</h4>${indicators}` : ""}
    ${evidence ? `<h4>${escapeHtml(t("graph.evidence"))}</h4>${evidence}` : ""}
    ${rels ? `<h4>${escapeHtml(t("graph.connections"))}</h4>${rels}` : ""}
  `;
}

window.clearGraphSelection = function () {
  GRAPH.selected = null;
  if (GRAPH.nodeSel) GRAPH.nodeSel.classed("dim", false);
  if (GRAPH.linkSel) GRAPH.linkSel.classed("dim", false).classed("hl", false);
  if (GRAPH.labelSel) GRAPH.labelSel.text((d) => (d.degree >= 3 || d.type === "arena" || d.type === "concept" ? d.label : ""));
  document.getElementById("graph-inspector").innerHTML = `<p class="rail-empty">${escapeHtml(t("graph.hint"))}</p>`;
};

function focusGraph(query) {
  if (!GRAPH.raw) return;
  const q = query.trim().toLowerCase();
  if (!q) {
    window.clearGraphSelection();
    return;
  }
  const match = GRAPH.raw.nodes.filter(
    (n) => n.label.toLowerCase().includes(q) || (n.summary || "").toLowerCase().includes(q)
  );
  const ids = new Set(match.map((n) => n.id));
  GRAPH.nodeSel.classed("dim", (d) => !ids.has(d.id));
  GRAPH.linkSel.classed("dim", (d) => !ids.has(d.source.id) || !ids.has(d.target.id));
  GRAPH.labelSel.text((d) => (ids.has(d.id) ? d.label : ""));
  if (match.length === 1) selectNode(match[0].id);
}
