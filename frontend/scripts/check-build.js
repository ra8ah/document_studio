#!/usr/bin/env node
/* Post-build gate: the production index.html must not contain Emergent preview tooling,
 * analytics, or any inline <script> (the CSP only allows script-src 'self'). */
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.resolve(__dirname, "../build/index.html"), "utf8");
const problems = [];
if (/emergent/i.test(html)) problems.push("mentions emergent");
if (/posthog/i.test(html)) problems.push("contains analytics snippet");
if (/fonts\.(googleapis|gstatic)\.com/.test(html)) problems.push("references external fonts");
const inline = [...html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>/g)];
if (inline.length) problems.push(`${inline.length} inline <script> tag(s)`);
if (!/<meta name="description"/.test(html)) problems.push("missing meta description");
if (problems.length) {
  console.error("[check-build] build/index.html failed: " + problems.join("; "));
  process.exit(1);
}
console.log("[check-build] build/index.html OK (no emergent assets, no inline scripts, self-hosted fonts)");
