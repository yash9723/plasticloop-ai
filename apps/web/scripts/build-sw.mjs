// Writes public/sw.js from the template with a build-stamped cache version, so every deploy gets fresh caches.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const version = process.env.SW_VERSION ?? new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
const template = readFileSync(new URL("../src/sw/sw.template.js", import.meta.url), "utf8");
mkdirSync(new URL("../public/", import.meta.url), { recursive: true });
writeFileSync(new URL("../public/sw.js", import.meta.url), template.replaceAll("__SW_VERSION__", version));
console.log(`public/sw.js written (cache version ${version})`);
