#!/usr/bin/env node
/*
 * Vercel install step (runs before `yarn install`, see vercel.json "installCommand").
 *  1. Refuses to deploy while vercel.json still points /api at the placeholder backend.
 *  2. Drops @emergentbase/* (Emergent preview tooling, fetched from a tarball URL) from
 *     package.json for this build only. yarn 1 aborts the whole install when ANY dependency
 *     tarball fails to download -- even an optional one -- so they must not be fetched at all.
 * Outside Vercel (VERCEL unset) this script does nothing unless FORCE_PREPARE=1.
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
if (!process.env.VERCEL && process.env.FORCE_PREPARE !== "1") {
  console.log("[prepare-vercel-install] not on Vercel - nothing to do");
  process.exit(0);
}

const vercel = JSON.parse(fs.readFileSync(path.join(root, "vercel.json"), "utf8"));
const api = (vercel.rewrites || [])[0];
if (!api || api.source !== "/api/(.*)" || /REPLACE-WITH-BACKEND-HOST/.test(api.destination || "")) {
  console.error("[prepare-vercel-install] vercel.json: first rewrite must proxy /api/(.*) to your backend URL " +
    "(replace REPLACE-WITH-BACKEND-HOST, see DEPLOY.md)");
  process.exit(1);
}

const pkgPath = path.join(root, "package.json");
const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
const dropped = [];
for (const field of ["dependencies", "devDependencies", "optionalDependencies"]) {
  for (const name of Object.keys(pkg[field] || {})) {
    if (name.startsWith("@emergentbase/")) { delete pkg[field][name]; dropped.push(name); }
  }
}
fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n");
const lock = path.join(root, "yarn.lock");
if (dropped.length && fs.existsSync(lock)) {
  // a lockfile entry for a removed package is harmless for yarn 1, but strip it to avoid a fetch
  const kept = fs.readFileSync(lock, "utf8").split(/\n(?=\S)/).filter((b) => !/^"?@emergentbase\//.test(b));
  fs.writeFileSync(lock, kept.join("\n"));
}
console.log(`[prepare-vercel-install] backend proxy: ${api.destination}; dropped: ${dropped.join(", ") || "none"}`);
