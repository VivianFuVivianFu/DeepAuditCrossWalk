# DeepAudit Crosswalk — P0.6 Security Release Correction & Deployment Profile Guarantees

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Supersedes / Corrects:** [`P05_SECURITY_RELEASE_READINESS.md`](P05_SECURITY_RELEASE_READINESS.md) (PR #29, `b47f08d8e1de1e351c407f2bc4b4aba72bbb47ca`)  
**Branch:** `fix/p06-cross-process-session-consistency`

---

## 1. Purpose of This Correction

In PR #29 (`b47f08d8e1de1e351c407f2bc4b4aba72bbb47ca`), `P05_SECURITY_RELEASE_READINESS.md` stated that `DurableRevocationStore` provided multi-process session revocation across worker processes. An independent post-merge code review and real multi-process verification revealed that:
1. `DurableRevocationStore.ensureLoaded()` used a read-once guard (`if (this.initialized) return;`) that prevented running peer processes from observing new revocations written to disk.
2. Concurrent revocations across processes lacked file locking and read-modify-write synchronization, permitting lost updates.
3. Read/write errors were caught and silently ignored (`catch {}`), falling open to process-local memory.
4. Runtime user overrides (`runtimeUserOverrides`) and login rate-limit counters (`failedLoginAttempts`) existed only in process-local memory.

This document corrects those release statements and defines the exact, verified security guarantees for each deployment profile after the P0.6 remediation.

---

## 2. Authoritative Deployment Profile Guarantees

### Profile A — Local Single-Process Community Edition
- **Target Use Case:** Single-user local workstation evaluation (`ENV=development`, single Node.js process + local FastAPI backend).
- **Security Store Behaviour:** Uses the local file-backed security state store (`SESSION_REVOCATION_PATH`, defaulting to `$TMPDIR/crosswalk_revocations.json` with `0600` permissions).
- **Explicit Limitations:**
  - Designed strictly for local single-host operation; not intended for internet-exposed public hosting.
  - `ALLOW_LOCAL_DEV_AUTH_BYPASS=true` is restricted to direct loopback (`127.0.0.1` / `localhost` / `::1`) without forwarding headers and is hard-disabled when `ENV=production`.
  - Storage read/write failures fail closed (`503`/`401`) and are never silently described as durable when underlying storage fails.
- **Release Gate Status:** **PASS**

### Profile B — Authenticated Single-Instance Self-Hosted Workspace
- **Target Use Case:** Internal enterprise self-hosted deployment on a **single host / VM / container instance** (which may run one or more local Node.js worker processes sharing the same local OS kernel and local POSIX/NTFS disk alongside a PostgreSQL backend).
- **Verified Guarantees (Post-P0.6 Remediation):**
  - **Cross-Worker Revocation Visibility:** Every session check reads the current persisted state from `SESSION_REVOCATION_PATH`; a logout on Worker Process A is immediately enforced (`401 Unauthorized`) on Worker Process B and survives process restarts.
  - **Zero Lost Updates:** Concurrent writes across worker processes on the same host are serialized via an exclusive lockfile (`${SESSION_REVOCATION_PATH}.lock`, opened with `O_CREAT | O_EXCL` / `"wx"`) performing an atomic Read-Modify-Write (`0600` mode + `fsyncSync` + atomic `renameSync`).
  - **Cryptographic Digest Storage:** Only `SHA-256(sid)` digests are persisted to disk; raw session IDs (`sid`) and bearer tokens are never written to disk.
  - **Cross-Worker Membership & Role Enforcement:** Account disablement, account deletion, tenant membership removal, and role downgrades (`reviewer -> analyst`, `admin -> reviewer`) are persisted in the shared security store and immediately enforced across all worker processes on the host.
  - **Cross-Worker Login Rate Limiting:** Failed login counters are shared across worker processes on the host, enforce a strict per-account ceiling (`acct:<username>`), and ignore spoofed `X-Forwarded-For` headers unless `TRUST_PROXY_HEADERS=true` is explicitly configured behind a trusted reverse proxy.
  - **Fail-Closed Storage Policy:** Any unreadable, truncated, or corrupted security state file throws `SecurityStateStorageError`, causing `isSessionRevoked()` to return `true` and `/api/workspace`, `/api/auth/login`, and `/api/auth/logout` to fail closed with `503 Service Unavailable`.
- **Explicit Boundary:** Do **not** mount `SESSION_REVOCATION_PATH` over network filesystems (NFS, SMB/CIFS, EFS) across multiple distinct servers/nodes and claim multi-node consistency.
- **Release Gate Status:** **PASS (Single-Host / Single-Instance Scope)**

### Profile C — Hosted Multi-Instance (Horizontally Clustered) Workspace
- **Target Use Case:** Horizontally scaled multi-node / multi-container Next.js web tier running across multiple independent machines or serverless isolates.
- **Current Architectural Status:**
  - The Next.js web gateway currently uses the host-local file-backed `SessionSecurityStore` (`web/app/security.ts`) and does not yet connect directly to a central transactional PostgreSQL session/revocation table.
  - Relying on node-local filesystems in a horizontally scaled multi-instance topology would allow a session revoked on Node 1 to remain valid on Node 2.
- **Enforced Safeguard:**
  - `detectDeploymentSecurityMode()` explicitly inspects `DEPLOYMENT_TOPOLOGY` (`multi_instance`, `clustered`, `multi_node`) and `WORKSPACE_MULTI_INSTANCE` (`true` / `1`).
  - When multi-instance topology is configured, the gateway **fails closed at readiness (`ready: false`, HTTP `503 Service Unavailable`)** with:
    > `"Unsupported deployment topology: multi-instance horizontal clustering is disabled because the file-backed security state store only guarantees consistency across worker processes on a single host."`
- **Release Gate Status:** **FAIL / EXPLICITLY DISABLED (Blocked by Readiness Gate until Central Transactional Session Store is Implemented)**

---

## 3. Summary Gate Matrix (Corrected)

| Gate | Deployment Profile | PR #29 Claimed Status | Corrected P0.6 Verified Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Gate A** | Public Synthetic Demo Mode | PASS | **PASS** | Stateless (`persist=False`), `public-demo` strictly isolated from `/api/workspace`. |
| **Gate B** | Local Single-Process Community Edition | PASS | **PASS** | Explicitly single-process local use, restart persistence verified, fail-closed on storage corruption. |
| **Gate C** | Authenticated Single-Instance Self-Hosted Workspace | PASS *(had multi-worker cache flaw in `b47f08d`)* | **PASS** | Verified with 2–4 real OS worker processes (`web/tests/p06_multiprocess_security.test.ts`, Scenarios A–F) + live PostgreSQL 16 RLS. |
| **Gate D1** | Hosted Single-Instance Private Document Upload | CONDITIONAL PASS | **CONDITIONAL PASS** | Supported on a single host with `ENV=production`, `WORKSPACE_SESSION_SECRET >= 32`, salted `scrypt` `WORKSPACE_USERS_JSON`, local `SESSION_REVOCATION_PATH`, and non-owner PostgreSQL RLS. |
| **Gate D2** | Hosted Multi-Instance (Clustered) Private Document Upload | *Not separated from Gate D1* | **FAIL / EXPLICITLY DISABLED (`503`)** | Explicitly disabled in `detectDeploymentSecurityMode()` (`DEPLOYMENT_TOPOLOGY=multi_instance` $\rightarrow$ `503`). Never silently claimed as supported. |
