# DeepAudit Crosswalk — P0.5 Security Hardening & Trust Boundary Audit

**Date:** 2026-11-14  
**Author:** Staff Software Security Reviewer & IAM Assurance Architect  
**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Target Branch:** `fix/p05-identity-session-security-hardening`  
**Base Commit:** `ed3d5a69328df2a0746345a90073ffc7c11b7ab6` (PR #27)

---

## 1. Executive Summary

Following the merge of PR #27 (*P0 Security Remediation: Authenticated Document Workspace & Reviewer Authorisation*), an independent security assurance audit was conducted across the Next.js gateway, FastAPI backend, session management, identity invariants, and PostgreSQL Row-Level Security (RLS) enforcement.

While PR #27 successfully eliminated open unauthenticated access to the private document workspace, our audit identified five critical trust boundary weaknesses, configuration-dependent vulnerabilities, and defense-in-depth gaps that prevented safe production deployment of internet-accessible confidential document processing.

This document classifies these findings into:
1. **Confirmed Vulnerabilities** (remediated in P0.5)
2. **Configuration-Dependent Risks** (hardened with fail-closed gates)
3. **Defense-in-Depth Gaps** (fortified with durable persistence and rate limiting)
4. **Clean & Resilient Areas** (verified and preserved)

---

## 2. Findings Classification

### Category 1: Confirmed Vulnerabilities (Remediated)

#### VULN-P05-1: Insecure Password Storage & Verification in User Store
- **Location:** `web/app/security.ts` (`verifyPassword`, `loadWorkspaceUsers`)
- **Severity:** High
- **Root Cause:** PR #27 accepted plaintext `password` strings or unsalted `password_sha256` hashes in `WORKSPACE_USERS_JSON`. In a production deployment, compromising the environment variable would immediately disclose all user passwords.
- **Remediation:** 
  - Standardised on memory-hard `scrypt` (`scrypt$<salt>$<hash>`, N=16384, r=8, p=1, keylen=64) using Node.js built-in `crypto.scryptSync`.
  - Added support for salted `pbkdf2` (`pbkdf2$<iters>$<salt>$<hash>`) with >= 10,000 iterations.
  - Strict production enforcement: in `ENV=production`, `loadWorkspaceUsers()` drops any user record lacking `password_hash`, and `verifyPassword()` immediately rejects legacy plaintext or unsalted SHA-256 candidates.
  - Created offline operator password hashing utility `scripts/hash_password.js`.

#### VULN-P05-2: Ephemeral In-Memory Session Revocation Vulnerability
- **Location:** `web/app/security.ts` (`revokedSessions = new Set<string>()`)
- **Severity:** High
- **Root Cause:** In PR #27, `revokeSession` recorded revoked session IDs in a local Node process `Set`. In multi-process production deployments (e.g. Next.js multi-worker, PM2, container replicas), logging out on Worker A left the session active on Worker B. Furthermore, server restarts wiped the revocation set, reviving logged-out sessions.
- **Remediation:**
  - Implemented `DurableRevocationStore` with atomic file-backed persistence (`SESSION_REVOCATION_PATH`, default `/tmp/crosswalk_revocations.json`).
  - Writes utilise atomic write-to-temp and rename operations (`fs.writeFileSync` to temp file + `fs.renameSync`).
  - Active sessions revoked on logout persist across process restarts and multi-process worker pools until token expiration.

#### VULN-P05-3: Incomplete OIDC Authentication Boundary
- **Location:** `web/app/api/auth/oidc/route.ts`
- **Severity:** Medium / High
- **Root Cause:** The OIDC endpoint in PR #27 accepted raw ID tokens with custom HMAC verification (`HS256`) against local secrets, rather than executing standard backchannel authorization-code token exchange against a trusted OIDC discovery endpoint (`.well-known/openid-configuration`) and JWKS signature verification (`RS256` / `ES256`).
- **Remediation:**
  - OIDC is explicitly classified as **experimental** and **disabled in hosted production** (`ENV=production` returns `501 Not Implemented`).
  - Production readiness checks (`detectDeploymentSecurityMode`) fail closed (503) if `OIDC_ISSUER_URL` is set without a verified user directory `WORKSPACE_USERS_JSON`.
  - Full JWKS authorization-code exchange is scheduled for a dedicated post-P0.5 OIDC PR.

---

### Category 2: Configuration-Dependent Risks (Hardened)

#### RISK-P05-1: Loopback Dev Bypass Header Injection Spoofing
- **Location:** `web/app/security.ts` (`isLoopbackRequest`)
- **Severity:** Medium
- **Root Cause:** When `ALLOW_LOCAL_DEV_AUTH_BYPASS=true` was enabled, an attacker routing through an edge proxy or manipulating headers could reach loopback routes if the proxy passed external traffic to `localhost:3000`.
- **Remediation:**
  - Hardened `isLoopbackRequest` to inspect proxy headers: if `X-Forwarded-For`, `X-Real-IP`, `Forwarded`, or `X-Forwarded-Host` are present on the incoming request, the request is definitively identified as proxied and loopback bypass is denied (401).

#### RISK-P05-2: Default Test Accounts in Production
- **Location:** `web/app/security.ts` (`loadWorkspaceUsers`)
- **Severity:** High
- **Root Cause:** If `WORKSPACE_USERS_JSON` was inadvertently omitted in production, fallback logic might load default fixture credentials (`analyst`, `reviewer`).
- **Remediation:**
  - In `ENV=production`, `loadWorkspaceUsers()` returns an empty map if `WORKSPACE_USERS_JSON` is missing or invalid.
  - Default fixture accounts are strictly confined to non-production environments (`!isProductionEnv()`).

#### RISK-P05-3: Weak Backend Workspace Context Signing Secret
- **Location:** `backend/banking_crosswalk/api.py` (`_verify_signed_workspace_context`)
- **Severity:** High
- **Root Cause:** Backend trusted gateway assertions (`X-Workspace-Context`) without enforcing secret entropy in production.
- **Remediation:**
  - Backend enforces `len(secret) >= 32` characters in `ENV=production`. If the secret is missing or under 32 characters, private tenant requests fail closed with `503 Service Unavailable`.
  - Missing `X-Workspace-Context` on private tenant requests fails closed with `401 Unauthorized`.

---

### Category 3: Defense-in-Depth Gaps (Fortified)

#### DEFENSE-P05-1: Brute-Force Password Guessing
- **Location:** `web/app/api/auth/login/route.ts`
- **Severity:** Medium
- **Remediation:** Added rate limiting to the login endpoint: 5 failed login attempts per minute per IP/username pair. Subsequent requests return `429 Too Many Requests`.

#### DEFENSE-P05-2: Static Token Over-Privilege
- **Location:** `web/app/security.ts` (`resolveSecurityContext`)
- **Severity:** Medium
- **Remediation:** The automation static bearer token (`WORKSPACE_AUTH_TOKEN`) is restricted to read-only `viewer` permissions. It is explicitly stripped of `clause:review`, `mapping:review`, `baseline:create`, and `policy:delete` permissions.

#### DEFENSE-P05-3: Instant Revocation of User and Tenant Rights
- **Location:** `web/app/security.ts` (`resolveSecurityContext`)
- **Severity:** High
- **Remediation:** JWT signatures are no longer solely trusted for authorization during their lifetime. On every request, the user store is consulted:
  - If a user was deleted: 401 Unauthorized immediately.
  - If a user was disabled: 401 Unauthorized immediately.
  - If a user was removed from the tenant: 403 Forbidden immediately.
  - If a user's role was downgraded: live roles take effect immediately, blocking privileged actions even if the unexpired token claims the higher role.

---

### Category 4: Clean & Resilient Areas (Preserved)

1. **APRA/ASIC Regulatory Library & Unified Control Crosswalk:**
   - Pure read-only regulatory taxonomy (`backend/banking_crosswalk/catalog.py`).
   - Zero algorithmic regressions across coverage evaluation and gap assessment.
2. **Two-Upload Document Workflow:**
   - Both Upload A (Enterprise Policies) and Upload B (Assurance Questionnaires) remain fully functional.
3. **Public Synthetic Demo Isolation:**
   - Anonymous access is strictly confined to stateless evaluation of `DEMO_BANKING_V1` under the isolated `public-demo` tenant (`persist=False` enforced by gateway).
   - Any attempt to use `public-demo` tenant on private workspace endpoints is rejected with 403.
4. **PostgreSQL Row-Level Security (RLS):**
   - Tables `tenant_snapshots` and `enterprise_policies` enforce strict `USING (tenant_id = current_setting('app.current_tenant'))`.
   - Production disallows table owners and superusers from executing runtime queries.
