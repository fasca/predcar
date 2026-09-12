// @ts-check
import { defineConfig } from "astro/config";

// GitHub Pages serves a project site under /<repo>/. Both values are overridable so the
// site can be built for another host (PREDCAR_SITE / PREDCAR_BASE).
const site = process.env.PREDCAR_SITE ?? "https://fasca.github.io";
const base = process.env.PREDCAR_BASE ?? "/predcar";

export default defineConfig({
  site,
  base,
  trailingSlash: "ignore",
  build: { format: "directory" },
});
