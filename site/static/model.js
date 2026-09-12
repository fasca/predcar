// Model page: three Plotly charts fed by the JSON embedded in #charts-data.
(function () {
  "use strict";
  const node = document.getElementById("charts-data");
  if (!node) return;
  if (typeof Plotly === "undefined") {
    document.querySelectorAll(".chart").forEach((el) => {
      el.innerHTML = '<p class="note" style="padding:1rem">Graphique indisponible : Plotly.js n’a pas pu être chargé depuis le CDN.</p>';
    });
    return;
  }
  const data = JSON.parse(node.textContent);
  const layout = (yTitle, extra) =>
    Object.assign(
      {
        margin: { l: 60, r: 20, t: 10, b: 40 },
        xaxis: { title: "Année", dtick: 1 },
        yaxis: { title: yTitle, rangemode: "tozero" },
        legend: { orientation: "h", y: -0.25 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "system-ui, sans-serif", size: 12 },
      },
      extra || {}
    );
  const config = { displayModeBar: false, responsive: true };

  function lines(traces, fmt) {
    return traces.map((t) => ({
      x: t.years,
      y: t.values,
      name: t.label + (t.series ? " (" + t.series + ")" : ""),
      mode: "lines+markers",
      type: "scatter",
      hovertemplate: "%{x} : " + fmt + "<extra>" + t.label + "</extra>",
    }));
  }

  if (data.stock.length) {
    Plotly.newPlot("chart-stock", lines(data.stock, "%{y:,d}"), layout("Véhicules"), config);
  }
  if (data.attrition.length) {
    Plotly.newPlot(
      "chart-attrition",
      lines(data.attrition, "%{y:.1%}"),
      layout("Attrition / an", { yaxis: { title: "Attrition / an", tickformat: ".0%", rangemode: "normal" } }),
      config
    );
  } else {
    const el = document.getElementById("chart-attrition");
    if (el) el.innerHTML = '<p class="note" style="padding:1rem">Historique trop court pour lisser l’attrition.</p>';
  }
  if (data.retention.length) {
    Plotly.newPlot(
      "chart-retention",
      lines(data.retention, "%{y:.1%}"),
      layout("Rétention", { yaxis: { title: "Rétention", tickformat: ".0%", range: [0, 1.05] } }),
      config
    );
  }
})();
