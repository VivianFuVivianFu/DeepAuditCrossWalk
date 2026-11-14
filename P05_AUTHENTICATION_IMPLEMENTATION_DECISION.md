# DeepAudit Crosswalk — P0.5 Authentication Implementation Decision Record

**Status:** Approved & Implemented  
**Date:** 2026-11-14  
**Context:** Release Blocking Hardening following PR #27  
**Branch:** `fix/p05-identity-session-security-hardening`

---

## 1. Architectural Decisions Summary

| Decision ID | Topic | Decision | Rationale |
|---|---|---|---|
| **ADR-P05-1** | **Password Hashing Algorithm** | Adopt **`scrypt`** (N=16384, r=8, p=1, keylen=64) as default; support salted **`pbkdf2`** (iters >= 10000). Reject plaintext and unsalted SHA-256 in production. | Memory-hard key derivation provides resistance against ASIC and GPU hardware brute-forcing. Zero external npm dependencies (uses native `node:crypto`). |
| **ADR-P05-2** | **Operator Tooling for Credential Generation** | Provide `scripts/hash_password.js` using Node.js standard library. | Enables secure generation of operator password hashes without introducing external build dependencies or third-party cloud tools. |
| **ADR-P05-3** | **OpenID Connect (OIDC) Strategy** | Mark current OIDC implementation as **Experimental / Non-Production**; disable with `501 Not Implemented` in `ENV=production`. | PR #27 used symmetric HMAC (`HS256`) against local secret instead of full standards-compliant authorization-code flow with JWKS key rotation (`RS256`). A dedicated enterprise OIDC PR is scheduled. |
| **ADR-P05-4** | **Static Automation Token Privilege Boundary** | Restrict `WORKSPACE_AUTH_TOKEN` strictly to `viewer` permissions. Block human reviewer actions (`clause:review`, `mapping:review`, `baseline:create`). | Automated CI pipelines and probes should read inventory and status, but must never masquerade as human reviewers or commit regulatory compliance approvals. |
| **ADR-P05-5** | **Session Revocation Durability** | Transition from in-memory `Set` to atomic file-backed `DurableRevocationStore` (`SESSION_REVOCATION_PATH`). | Multi-worker gateways and server restarts must not revive revoked sessions. Uses atomic write-to-temp + rename to prevent corruption under concurrent read/write. |
| **ADR-P05-6** | **Apache-2.0 Community Edition Independence** | Zero mandatory paid external cloud services; 100% self-hostable. | The open-source community edition must run completely offline and self-contained on developer workstations and local air-gapped infrastructure. |
| **ADR-P05-7** | **Login Rate Limiting** | Enforce client rate limiting: 5 failed attempts per minute per IP:username pair (`429 Too Many Requests`). | Prevents online password brute-force guessing attacks while allowing legitimate operators to retry after a reasonable cooldown. |

---

## 2. Detailed Decision Analysis

### ADR-P05-1: Scrypt Password Storage
- **Context:** Storing plaintext passwords or unsalted SHA-256 hashes in `WORKSPACE_USERS_JSON` presents an unacceptable vulnerability for confidential enterprise document handling.
- **Decision:** All production password hashes must follow the format:
  `scrypt$<16_byte_hex_salt>$<64_byte_derived_hex_key>`
  - CPU/Memory cost $N = 16384$ (16 MiB RAM per hash)
  - Block size $r = 8$
  - Parallelization $p = 1$
  - Key length = 64 bytes
- **Verification:** Implemented in `web/app/security.ts:hashPassword` and `verifyPassword`. Verified by Vitest test group `H1–H3`.

### ADR-P05-2: CLI Operator Password Tool
- **Command:** `node scripts/hash_password.js "YourStrongPassword"`
- **Output:** Produces formatted `scrypt$...` string ready for pasting into `WORKSPACE_USERS_JSON`.
- **Verification flag:** `node scripts/hash_password.js --verify "CandidatePassword" "scrypt$..."` returns validation result.

### ADR-P05-3: OIDC Production Deferral
- **Context:** Enterprise identity integration requires robust OpenID Connect. However, accepting custom HMAC signed ID tokens without standard JWKS cryptographic signature verification against the Identity Provider's discovery endpoint violates enterprise zero-trust principles.
- **Decision:**
  - In `ENV=production`, any request to `/api/auth/oidc` immediately returns `501 Not Implemented`.
  - Deployment readiness check `detectDeploymentSecurityMode` fails with `503` if only `OIDC_ISSUER_URL` is configured in production.
  - Development and testing environments may continue using the local OIDC flow for integration testing.

### ADR-P05-4: Static Token Privilege Reduction
- **Context:** `WORKSPACE_AUTH_TOKEN` was previously used as a blanket bearer token.
- **Decision:** Service automation tokens are assigned `user_id = svc-<actor>` and granted strictly `["viewer"]` roles. Permissions `clause:review`, `mapping:review`, `baseline:create`, and `policy:delete` are explicitly stripped from static tokens.

### ADR-P05-5: Durable Session Revocation Store
- **Context:** Single-process memory stores are incompatible with containerised microservices or multi-worker Node.js architectures.
- **Decision:** `DurableRevocationStore` synchronises revocations to a durable path. On startup or read, it loads active revocations; on revocation, it updates memory and persists an atomic snapshot. Expired entries are pruned during read cycles.
