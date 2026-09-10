/* Risk profile tab: composite vulnerability / resilience / risk scores
   (data/processed/scores.csv, ESCWA Annex 1 method). */

const RISK = {
  rows: null,
  charts: {},
  loaded: false,
  countries: [],
};

const LEVEL_BADGE = {
  "very low": "badge-verylow",
  low: "badge-low",
  moderate: "badge-moderate",
  high: "badge-high",
  "very high": "badge-veryhigh",
};
const LEVEL_FILL = {
  "very low": "#22c55e",
  low: "#10b981",
  moderate: "#f59e0b",
  high: "#ef4444",
  "very high": "#b91c1c",
};

function riskLevel(v) {
  if (v == null) return null;
  if (v >= 0.8) return "very high";
  if (v >= 0.6) return "high";
  if (v >= 0.4) return "moderate";
  if (v >= 0.2) return "low";
  return "very low";
}

async function loadRisk() {
  if (!RISK.loaded) {
    const res = await fetch("/api/scores");
    if (!res.ok) {
      document.getElementById("risk-table").innerHTML =
        `<tr><td colspan="5">${escapeHtml((await res.json().catch(() => ({}))).detail || "Scores not built — run python etl/build_scores.py")}</td></tr>`;
      return;
    }
    RISK.rows = await res.json();
    RISK.loaded = true;

    RISK.countries = [...new Map(RISK.rows.map((r) => [r.country_iso3, r.country_name])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    const sel = document.getElementById("risk-country");
    sel.innerHTML = RISK.countries.map(([iso, name]) => `<option value="${iso}">${escapeHtml(name)}</option>`).join("");
    sel.value = "SYR";

    const years = [...new Set(RISK.rows.map((r) => r.year))].sort();
    const slider = document.getElementById("risk-year");
    slider.min = years[0];
    slider.max = years[years.length - 1];
    slider.value = Math.min(2023, years[years.length - 1]);

    ["risk-country", "risk-year", "risk-rankdim", "risk-rankpathway"].forEach((id) =>
      document.getElementById(id).addEventListener("input", renderRisk)
    );
  }
  renderRisk();
}

function renderRisk() {
  if (!RISK.loaded) return;
  const iso = document.getElementById("risk-country").value;
  const year = +document.getElementById("risk-year").value;
  const dim = document.getElementById("risk-rankdim").value;
  const rankPw = document.getElementById("risk-rankpathway").value;
  document.getElementById("risk-year-val").textContent = year;

  const rowsY = RISK.rows.filter((r) => r.year === year);
  const country = RISK.countries.find(([i]) => i === iso)?.[1] || iso;
  document.getElementById("risk-profile-title").textContent = `${t("risk.profile_of")} ${country} · ${year}`;

  // --- level bars (Overall) --------------------------------------------
  const overall = rowsY.find((r) => r.country_iso3 === iso && r.pathway === "Overall") || {};
  document.getElementById("risk-levels").innerHTML = ["vulnerability", "resilience", "risk"]
    .map((d) => {
      const v = overall[d];
      const lvl = riskLevel(v);
      return `<div class="lvl">
        <span style="width:90px">${escapeHtml(t("risk." + d))}</span>
        <span class="bar"><i style="width:${((v ?? 0) * 100).toFixed(0)}%;background:${lvl ? LEVEL_FILL[lvl] : "#cbd5e1"}"></i></span>
        <span class="num">${v == null ? "—" : v.toFixed(2)}</span>
        <span class="tag ${lvl ? LEVEL_BADGE[lvl] : ""}">${lvl ? escapeHtml(lvl) : ""}</span>
      </div>`;
    })
    .join("");

  // --- pathway breakdown (grouped bars) -------------------------------
  const pathways = ["Conflict", "Climate", "Development"];
  const byPw = Object.fromEntries(pathways.map((p) => [p, rowsY.find((r) => r.country_iso3 === iso && r.pathway === p) || {}]));
  drawBar("risk-radar", {
    labels: pathways,
    datasets: [
      { label: t("risk.vulnerability"), data: pathways.map((p) => byPw[p].vulnerability ?? null), backgroundColor: "#b45309" },
      { label: t("risk.resilience"), data: pathways.map((p) => byPw[p].resilience ?? null), backgroundColor: "#0f766e" },
    ],
  });

  // --- trend ----------------------------------------------------------
  const tr = RISK.rows.filter((r) => r.country_iso3 === iso && r.pathway === "Overall").sort((a, b) => a.year - b.year);
  drawLine("risk-trend", {
    labels: tr.map((r) => r.year),
    datasets: [
      { label: t("risk.vulnerability"), data: tr.map((r) => r.vulnerability), borderColor: "#b45309", tension: 0.25, pointRadius: 0, borderWidth: 1.5 },
      { label: t("risk.resilience"), data: tr.map((r) => r.resilience), borderColor: "#0f766e", tension: 0.25, pointRadius: 0, borderWidth: 1.5 },
      { label: t("risk.risk"), data: tr.map((r) => r.risk), borderColor: "#dc2626", borderDash: [4, 3], tension: 0.25, pointRadius: 0, borderWidth: 1.5 },
    ],
  });

  // --- regional scatter (vulnerability vs resilience) ----------------
  const scatterPw = rankPw;
  const pts = rowsY
    .filter((r) => r.pathway === scatterPw && r.vulnerability != null && r.resilience != null)
    .map((r) => ({ x: r.resilience, y: r.vulnerability, iso: r.country_iso3, name: r.country_name, lvl: r.risk_level }));
  drawScatter("risk-scatter", pts, iso);

  // --- ranking table ------------------------------------------------
  const ranked = rowsY
    .filter((r) => r.pathway === rankPw && r[dim] != null)
    .sort((a, b) => (dim === "resilience" ? a[dim] - b[dim] : b[dim] - a[dim]));
  document.getElementById("risk-table").innerHTML = ranked
    .map((r, i) => {
      const lvl = r[`${dim}_level`] || riskLevel(r[dim]);
      const low = r.n_indicators < 3;
      return `<tr${r.country_iso3 === iso ? ' style="background:var(--brand-wash)"' : ""}>
        <td class="num">${i + 1}</td>
        <td>${escapeHtml(r.country_name)}</td>
        <td class="num">${r[dim].toFixed(3)}</td>
        <td><span class="tag ${LEVEL_BADGE[lvl] || ""}" style="font-size:10px">${escapeHtml(lvl || "")}</span></td>
        <td class="num" title="${low ? escapeHtml(t("risk.low_coverage")) : ""}">${r.n_indicators}${low ? " ⚠" : ""}</td>
      </tr>`;
    })
    .join("");
}

function _destroy(id) {
  if (RISK.charts[id]) RISK.charts[id].destroy();
}
function drawBar(id, data) {
  _destroy(id);
  RISK.charts[id] = new Chart(document.getElementById(id), {
    type: "bar",
    data,
    options: {
      responsive: true,
      scales: { y: { min: 0, max: 1, ticks: { font: { size: 9 } } }, x: { ticks: { font: { size: 10 } } } },
      plugins: { legend: { labels: { font: { size: 10 }, boxWidth: 10 } } },
    },
  });
}
function drawLine(id, data) {
  _destroy(id);
  RISK.charts[id] = new Chart(document.getElementById(id), {
    type: "line",
    data,
    options: {
      responsive: true,
      scales: { y: { min: 0, max: 1, ticks: { font: { size: 9 } } }, x: { ticks: { font: { size: 9 }, maxTicksLimit: 8 } } },
      plugins: { legend: { labels: { font: { size: 10 }, boxWidth: 10 } } },
    },
  });
}
function drawScatter(id, pts, hiIso) {
  _destroy(id);
  RISK.charts[id] = new Chart(document.getElementById(id), {
    type: "scatter",
    data: {
      datasets: [
        {
          data: pts,
          pointRadius: pts.map((p) => (p.iso === hiIso ? 7 : 4)),
          pointBackgroundColor: pts.map((p) => LEVEL_FILL[p.lvl] || "#64748b"),
          pointBorderColor: pts.map((p) => (p.iso === hiIso ? "#17223b" : "transparent")),
          pointBorderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        x: { min: 0, max: 1, title: { display: true, text: t("risk.resilience"), font: { size: 10 } }, ticks: { font: { size: 9 } } },
        y: { min: 0, max: 1, title: { display: true, text: t("risk.vulnerability"), font: { size: 10 } }, ticks: { font: { size: 9 } } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `${c.raw.name}: vuln ${c.raw.y.toFixed(2)}, resil ${c.raw.x.toFixed(2)}` } },
      },
    },
  });
}
