// Ranking page: client-side filters (segment, decade, country), sort and top-50 limit.
// The table is fully rendered at build time; this script only hides/reorders rows.
(function () {
  "use strict";
  const table = document.getElementById("ranking");
  if (!table) return;
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const controls = {
    segment: document.getElementById("f-segment"),
    decade: document.getElementById("f-decade"),
    country: document.getElementById("f-country"),
    sort: document.getElementById("f-sort"),
    top50: document.getElementById("f-top50"),
    count: document.getElementById("f-count"),
  };

  function num(row, key) {
    const v = row.dataset[key];
    return v === "" || v === undefined || v === "None" ? null : Number(v);
  }

  const sorters = {
    score: (a, b) => num(a, "rank") - num(b, "rank"),
    "attrition-desc": (a, b) => (num(b, "attrition") ?? -Infinity) - (num(a, "attrition") ?? -Infinity),
    "attrition-asc": (a, b) => (num(a, "attrition") ?? Infinity) - (num(b, "attrition") ?? Infinity),
    "stock-asc": (a, b) => num(a, "stock") - num(b, "stock"),
  };

  function apply() {
    const segment = controls.segment.value;
    const decade = controls.decade.value;
    const country = controls.country.value;
    const limit = controls.top50.checked ? 50 : Infinity;
    const sorted = rows.slice().sort(sorters[controls.sort.value] || sorters.score);
    let shown = 0;
    sorted.forEach((row) => {
      const ok =
        (!segment || row.dataset.segment === segment) &&
        (!decade || row.dataset.decade === decade) &&
        (!country || row.dataset.countries.split(" ").includes(country)) &&
        shown < limit;
      row.hidden = !ok;
      if (ok) shown += 1;
      tbody.appendChild(row);
    });
    controls.count.textContent = shown + " / " + rows.length + " générations affichées";
  }

  Object.values(controls).forEach((el) => {
    if (el && el.tagName !== "SPAN") el.addEventListener("change", apply);
  });
  apply();
})();
