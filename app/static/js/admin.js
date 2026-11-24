// Admin analytics charts (Chart.js). Data comes from a JSON script tag (CSP-safe).
(function () {
  "use strict";
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function () {
    var el = document.getElementById("chart-data");
    if (!el || !window.Chart) return;
    var d = JSON.parse(el.textContent);
    var css = getComputedStyle(document.documentElement);
    var text2 = css.getPropertyValue("--text-2").trim() || "#a7b0c0";
    var grid = css.getPropertyValue("--border").trim() || "#1f2a3d";
    // Categorical palette (validated for dark surfaces; distinct in hue + lightness)
    var palette = ["#818cf8", "#22d3ee", "#34d399", "#fbbf24", "#f472b6", "#a78bfa"];
    Chart.defaults.color = text2;
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    Chart.defaults.borderColor = grid;
    var labels = d.labels.map(function (s) { return s.slice(5); });
    var common = { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, ticks: { precision: 0 } } } };

    var mods = Object.keys(d.runs_series);
    var stacked = JSON.parse(JSON.stringify(common));
    stacked.scales.x.stacked = true; stacked.scales.y.stacked = true;
    new Chart(document.getElementById("chart-runs"), { type: "bar", options: stacked, data: { labels: labels,
      datasets: mods.map(function (m, i) { return { label: m.replace(/_/g, " "), data: d.runs_series[m],
        backgroundColor: palette[i % palette.length], borderWidth: 0, maxBarThickness: 22 }; }) } });

    new Chart(document.getElementById("chart-signups"), { type: "bar", data: { labels: labels,
      datasets: [{ label: "Signups", data: d.signups_series, backgroundColor: "#818cf8", borderRadius: 4, maxBarThickness: 18 }] },
      options: Object.assign({}, common, { plugins: { legend: { display: false } } }) });

    var prov = Object.keys(d.cost_by_provider);
    new Chart(document.getElementById("chart-cost"), { type: "bar", data: { labels: prov,
      datasets: [{ label: "USD", data: prov.map(function (p) { return d.cost_by_provider[p]; }),
        backgroundColor: prov.map(function (_, i) { return palette[i % palette.length]; }), borderRadius: 6, maxBarThickness: 48 }] },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, grid: { color: grid } }, y: { grid: { display: false } } } } });
  });
})();
