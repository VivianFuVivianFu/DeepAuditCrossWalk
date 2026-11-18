#!/usr/bin/env node
/**
 * Narrow, time-limited npm audit security gate for web/ (CI).
 *
 * Security Invariants:
 * 1. Production dependencies (`npm audit --omit=dev --audit-level=high`) have ZERO
 *    exceptions and must pass with 0 high/critical vulnerabilities.
 * 2. Full dependency tree (`npm audit --json`) is inspected for all high/critical
 *    vulnerabilities.
 * 3. Only the explicitly documented, time-limited dev-only exception for
 *    GHSA-fc5q-39xc-vjpf (picomatch <= 4.0.7 ReDoS in single-branch repeated extglobs,
 *    pulled in exclusively by the dev-only vitest -> vite -> tinyglobby -> fdir chain,
 *    with no upstream patched version > 4.0.7 published on npm as of 2026-11-18) is
 *    permitted until EXPIRES_AT.
 * 4. Any other high/critical advisory, any production exposure, or expiration of the
 *    exception window fails the CI gate immediately (exit code 1).
 */

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ALLOWED_ADVISORY_URL = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf";
const ALLOWED_ADVISORY_SOURCE = 1247710;
const ALLOWED_CHAIN_PACKAGES = new Set([
  "picomatch",
  "fdir",
  "tinyglobby",
  "vite",
  "@vitest/mocker",
  "vitest",
]);
const EXCEPTION_EXPIRES_AT = new Date("2026-12-18T00:00:00Z");

const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
const cwd = process.cwd();

function validateAuditPayload(payload) {
  if (
    !payload ||
    typeof payload !== "object" ||
    typeof payload.auditReportVersion !== "number" ||
    !payload.vulnerabilities ||
    typeof payload.vulnerabilities !== "object" ||
    payload.error ||
    payload.statusCode
  ) {
    console.error(
      "[SECURITY GATE FAILED] Invalid or failed npm audit response payload:",
      JSON.stringify(payload, null, 2)
    );
    process.exit(1);
  }
  return payload;
}

function runNpmAuditJson(extraArgs = []) {
  try {
    const out = execFileSync(npmCmd, ["audit", "--json", ...extraArgs], {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "pipe"],
      shell: process.platform === "win32",
    });
    return validateAuditPayload(JSON.parse(out));
  } catch (err) {
    if (err && typeof err.stdout === "string" && err.stdout.trim().startsWith("{")) {
      return validateAuditPayload(JSON.parse(err.stdout));
    }
    console.error("Failed to execute npm audit:", err?.stderr || err?.message || err);
    process.exit(1);
  }
}

// 1. Verify exception window has not expired
const now = new Date();
if (now >= EXCEPTION_EXPIRES_AT) {
  console.error(
    `[SECURITY GATE FAILED] Time-limited exception for ${ALLOWED_ADVISORY_URL} expired on ${EXCEPTION_EXPIRES_AT.toISOString()}.`
  );
  process.exit(1);
}

// 2. Verify picomatch is strictly dev-only in package-lock.json
const lockPath = path.resolve(cwd, "package-lock.json");
const lockData = JSON.parse(fs.readFileSync(lockPath, "utf-8"));
const picomatchEntry = lockData.packages?.["node_modules/picomatch"];
if (!picomatchEntry || picomatchEntry.dev !== true) {
  console.error(
    "[SECURITY GATE FAILED] node_modules/picomatch is missing or not marked dev:true in package-lock.json."
  );
  process.exit(1);
}

// 3. Enforce strict zero-exception gate on production dependencies
const prodReport = runNpmAuditJson(["--omit=dev"]);
const prodHighOrCrit =
  (prodReport.metadata?.vulnerabilities?.high || 0) +
  (prodReport.metadata?.vulnerabilities?.critical || 0);
if (prodHighOrCrit > 0) {
  console.error(
    `[SECURITY GATE FAILED] Production dependencies contain ${prodHighOrCrit} high/critical vulnerabilities.`
  );
  console.error(JSON.stringify(prodReport.vulnerabilities, null, 2));
  process.exit(1);
}

// 4. Inspect full dependency graph (prod + dev)
const fullReport = runNpmAuditJson();
const vulns = fullReport.vulnerabilities || {};
const unapproved = [];

for (const [pkgName, vuln] of Object.entries(vulns)) {
  const sev = vuln.severity;
  if (sev !== "high" && sev !== "critical") {
    continue;
  }
  if (!ALLOWED_CHAIN_PACKAGES.has(pkgName)) {
    unapproved.push({ pkgName, reason: "Package not in allowed dev-only vitest/picomatch chain", vuln });
    continue;
  }
  const viaList = Array.isArray(vuln.via) ? vuln.via : [];
  for (const viaItem of viaList) {
    if (typeof viaItem === "string") {
      if (!ALLOWED_CHAIN_PACKAGES.has(viaItem)) {
        unapproved.push({
          pkgName,
          reason: `Transitive via '${viaItem}' outside allowed chain`,
          vuln,
        });
      }
    } else if (viaItem && typeof viaItem === "object") {
      const matchesAdvisory =
        viaItem.url === ALLOWED_ADVISORY_URL || viaItem.source === ALLOWED_ADVISORY_SOURCE;
      if (!matchesAdvisory) {
        unapproved.push({
          pkgName,
          reason: `Unapproved advisory ${viaItem.url || viaItem.source}`,
          vuln,
        });
      }
    }
  }
}

if (unapproved.length > 0) {
  console.error("[SECURITY GATE FAILED] Unapproved high/critical vulnerabilities detected:");
  console.error(JSON.stringify(unapproved, null, 2));
  process.exit(1);
}

console.log(
  `[SECURITY GATE PASSED] Production high/critical vulnerabilities: 0. ` +
    `Dev-only time-limited exception active for ${ALLOWED_ADVISORY_URL} ` +
    `(picomatch@${picomatchEntry.version}, no upstream >4.0.7 fix published; expires ${EXCEPTION_EXPIRES_AT.toISOString()}).`
);
