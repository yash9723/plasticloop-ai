// Localization completeness check:
//  1. every locale has exactly the keys of en.json, with non-empty values and matching {placeholders}
//  2. every literal t("key") used in src/ exists in en.json
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const msgDir = join(root, "src/i18n/messages");
const locales = ["en", "hi", "te"];

const flatten = (obj, prefix = "", out = {}) => {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") flatten(v, key, out);
    else out[key] = v;
  }
  return out;
};
const placeholders = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");

const dicts = Object.fromEntries(locales.map((l) => [l, flatten(JSON.parse(readFileSync(join(msgDir, `${l}.json`), "utf8")))]));
const base = dicts.en;
const problems = [];

for (const l of locales.slice(1)) {
  for (const k of Object.keys(base)) {
    if (!(k in dicts[l])) problems.push(`[${l}] missing key: ${k}`);
    else if (!String(dicts[l][k]).trim()) problems.push(`[${l}] empty value: ${k}`);
    else if (placeholders(dicts[l][k]) !== placeholders(base[k])) problems.push(`[${l}] placeholder mismatch: ${k}`);
  }
  for (const k of Object.keys(dicts[l])) if (!(k in base)) problems.push(`[${l}] extra key not in en: ${k}`);
}

const walk = (dir) =>
  readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : /\.(tsx?|ts)$/.test(f) ? [p] : [];
  });
const used = new Set();
for (const file of walk(join(root, "src"))) {
  for (const m of readFileSync(file, "utf8").matchAll(/\bt\(\s*["'`]([a-zA-Z0-9_.]+)["'`]/g)) used.add(m[1]);
}
for (const k of used) if (!(k in base)) problems.push(`[src] t("${k}") is not defined in en.json`);

if (problems.length) {
  console.error(problems.join("\n"));
  console.error(`\n${problems.length} localization problem(s).`);
  process.exit(1);
}
console.log(`i18n OK: ${Object.keys(base).length} keys × ${locales.length} locales, ${used.size} keys referenced in src.`);
