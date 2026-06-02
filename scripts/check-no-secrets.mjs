#!/usr/bin/env node
/**
 * Pre-push secret leakage check.
 *
 * Run from the repo root:
 *
 *   node scripts/check-no-secrets.mjs
 *
 * This is a fast, deterministic gate that fails (exit 1) if any of the
 * filenames the team has agreed to never publish appear in `git ls-files`.
 *
 * It complements scripts/secret-scan.mjs (which scans content for secret
 * patterns) by catching the most common operational mistake: accidentally
 * `git add`-ing a real `.env`, `data/secrets.enc`, or per-host key file.
 *
 * Why a separate script: secret-scan.mjs already runs in CI; this one is
 * a 50ms local sanity check you can wire into a pre-push git hook. They
 * are intentionally not merged so a regression in one does not silently
 * disable the other.
 */

import { execSync } from "node:child_process";
import { exit } from "node:process";

const NEVER_TRACK = [
  /^\.env$/,
  /^\.env\.[^.]+$/,            // .env.production etc.
  /^data\/secrets\.enc$/,
  /^data\/\.jwt_secret$/,
  /^data\/\.admin_key$/,
  /^uploads\//,
  /\.pem$/,
  /private[_-]?key/i,
];

// Allow the template through; it's the documented safe shape of .env.
const ALLOWLIST = new Set([".env.example"]);

let tracked;
try {
  tracked = execSync("git ls-files", { encoding: "utf8" }).split(/\r?\n/);
} catch (err) {
  console.error("git ls-files failed:", err.message);
  exit(2);
}

const offenders = [];
for (const path of tracked) {
  if (!path || ALLOWLIST.has(path)) continue;
  for (const rule of NEVER_TRACK) {
    if (rule.test(path)) {
      offenders.push({ path, rule: rule.toString() });
      break;
    }
  }
}

if (offenders.length === 0) {
  console.log("Secret-tracking check passed.");
  exit(0);
}

console.error("\nDO NOT push. The following tracked files look like secrets:");
for (const o of offenders) {
  console.error(`  - ${o.path}  (matched ${o.rule})`);
}
console.error(
  "\nNext steps:\n" +
    "  1. git rm --cached <file>      # untrack but keep on disk\n" +
    "  2. add the path to .gitignore\n" +
    "  3. rotate the leaked secret if it ever reached origin\n",
);
exit(1);
