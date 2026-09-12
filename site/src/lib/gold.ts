/** Build-time data layer: the site is generated from the latest committed evidence bundle.
 *
 * reports/<date>/gold/ is versioned, so a build never needs the network, a data/ directory
 * or a pipeline run — and what the site shows is always something the repository can prove.
 * The bundle date is the refresh date displayed on every page (SPEC §6).
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { num, parseCsv } from "./csv.ts";

const ROOT = fileURLToPath(new URL("../../..", import.meta.url));
const REPORTS = join(ROOT, "reports");
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export type Country = "GB" | "NL" | "EU";

export interface RankRow {
  rank: number;
  make: string;
  modelGen: string;
  generation: string;
  segment: string;
  score: number;
  stock: number | null;
  rarity: number | null;
  conservation: number | null;
  sornRatio: number | null;
  recentInflectionPoint: number | null;
  relativeAttrition: number | null;
  inflectionYear: number | null;
  weightCoverage: number | null;
  componentsAvailable: string[];
  slug: string;
}

export interface IndicatorRow {
  make: string;
  modelGen: string;
  generation: string;
  segment: string;
  country: Country;
  level: string;
  series: string;
  latestYear: number | null;
  stock: number | null;
  rarityTier: string;
  cumulativeSales: number | null;
  survival: number | null;
  historyYears: number | null;
  attrition: number | null;
  relativeAttrition: number | null;
  nPeers: number | null;
  inflectionYear: number | null;
  sornRatio: number | null;
}

export interface SeriesPoint {
  country: Country;
  series: string;
  year: number;
  stock: number;
}

/** Latest reports/<YYYY-MM-DD>/ that actually holds a gold ranking. */
function latestBundle(): string {
  if (!existsSync(REPORTS)) throw new Error(`no reports/ directory at ${REPORTS}`);
  const days = readdirSync(REPORTS)
    .filter((d) => DAY.test(d))
    .sort()
    .reverse();
  const found = days.find((d) => existsSync(join(REPORTS, d, "gold", "ranking.csv")));
  if (!found) {
    throw new Error("no evidence bundle with gold/ranking.csv — run `make export` and commit it");
  }
  return found;
}

export const bundleDate = latestBundle();

function read(name: string): Record<string, string>[] {
  const path = join(REPORTS, bundleDate, "gold", `${name}.csv`);
  return existsSync(path) ? parseCsv(readFileSync(path, "utf-8")) : [];
}

/** Stable URL for one target generation. Encodes the full identity key
 * (make, model_gen, generation): two makes share a model label (SPIDER). */
export function slugify(make: string, modelGen: string, generation: string): string {
  return [make, modelGen, generation]
    .join(" ")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export const ranking: RankRow[] = read("ranking").map((r) => ({
  rank: Number(r.rank),
  make: r.make,
  modelGen: r.model_gen,
  generation: r.generation,
  segment: r.segment,
  score: Number(r.score),
  stock: num(r.stock),
  rarity: num(r.rarity),
  conservation: num(r.conservation),
  sornRatio: num(r.sorn_ratio),
  recentInflectionPoint: num(r.recent_inflection_point),
  relativeAttrition: num(r.relative_attrition),
  inflectionYear: num(r.inflection_year),
  weightCoverage: num(r.weight_coverage),
  componentsAvailable: r.components_available ? r.components_available.split("|") : [],
  slug: slugify(r.make, r.model_gen, r.generation),
}));

export const indicators: IndicatorRow[] = read("indicators").map((r) => ({
  make: r.make,
  modelGen: r.model_gen,
  generation: r.generation,
  segment: r.segment,
  country: r.country as Country,
  level: r.level,
  series: r.series,
  latestYear: num(r.latest_year),
  stock: num(r.stock),
  rarityTier: r.rarity_tier,
  cumulativeSales: num(r.cumulative_sales),
  survival: num(r.survival),
  historyYears: num(r.history_years),
  attrition: num(r.attrition),
  relativeAttrition: num(r.relative_attrition),
  nPeers: num(r.n_peers),
  inflectionYear: num(r.inflection_year),
  sornRatio: num(r.sorn_ratio),
}));

const seriesRows = read("stock_series");

/** Annual stock points of one target, grouped by (country, series). */
export function seriesOf(make: string, modelGen: string, generation: string): SeriesPoint[] {
  return seriesRows
    .filter((r) => r.make === make && r.model_gen === modelGen && r.generation === generation)
    .map((r) => ({
      country: r.country as Country,
      series: r.series,
      year: Number(r.year),
      stock: Number(r.stock),
    }))
    .sort((a, b) => a.year - b.year);
}

export function indicatorsOf(make: string, modelGen: string, generation: string): IndicatorRow[] {
  return indicators.filter(
    (r) => r.make === make && r.modelGen === modelGen && r.generation === generation,
  );
}

/** Published targets of the same segment, for the peer comparison. */
export function peersOf(row: RankRow): RankRow[] {
  return ranking.filter((r) => r.segment === row.segment && r.slug !== row.slug);
}

export const segments = [...new Set(ranking.map((r) => r.segment))].sort();
export const makes = [...new Set(ranking.map((r) => r.make))].sort();
