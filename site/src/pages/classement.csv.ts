/** CSV export of the published ranking (SPEC §6), served as a static file. */
import type { APIRoute } from "astro";

import { bundleDate, ranking } from "../lib/gold.ts";

const COLUMNS = [
  "rank",
  "make",
  "model_gen",
  "generation",
  "segment",
  "score",
  "stock",
  "rarity",
  "conservation",
  "sorn_ratio",
  "recent_inflection_point",
  "relative_attrition",
  "inflection_year",
  "weight_coverage",
  "components_available",
] as const;

function cell(value: string | number | null): string {
  if (value === null) return "";
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export const GET: APIRoute = () => {
  const lines = [COLUMNS.join(",")];
  for (const r of ranking) {
    lines.push(
      [
        r.rank,
        r.make,
        r.modelGen,
        r.generation,
        r.segment,
        r.score,
        r.stock,
        r.rarity,
        r.conservation,
        r.sornRatio,
        r.recentInflectionPoint,
        r.relativeAttrition,
        r.inflectionYear,
        r.weightCoverage,
        r.componentsAvailable.join("|"),
      ]
        .map(cell)
        .join(","),
    );
  }
  return new Response(lines.join("\n") + "\n", {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="predcar-classement-${bundleDate}.csv"`,
    },
  });
};
