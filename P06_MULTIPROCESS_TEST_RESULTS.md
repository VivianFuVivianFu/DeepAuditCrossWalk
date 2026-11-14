# DeepAudit Crosswalk — P0.6 Multi-Process Integration & Regression Test Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Branch:** `fix/p06-cross-process-session-consistency`  
**Test Suite:** [`web/tests/p06_multiprocess_security.test.ts`](web/tests/p06_multiprocess_security.test.ts)  
**OS Worker Harness:** [`web/tests/helpers/security_process_worker.cjs`](web/tests/helpers/security_process_worker.cjs)

---

## 1. Real Multi-Process Execution Methodology

Unlike single-process mocks or multiple class instances sharing one Node.js heap, `web/tests/p06_multiprocess_security.test.ts` spawns **independent operating-system Node.js child processes** via `child_process.spawn(process.execPath, [WORKER_SCRIPT])`.

Each worker process:
- Runs in its own isolated V8 heap and OS process (`procA.pid !== procB.pid !== process.pid`).
- Loads the actual Next.js App Router route handlers (`app/api/auth/login/route.ts`, `app/api/auth/logout/route.ts`, `app/api/auth/session/route.ts`, `app/api/workspace/route.ts`) and `app/security.ts`.
- Communicates only through standard HTTP `Request`/`Response` objects and the shared filesystem path (`SESSION_REVOCATION_PATH`).

---

## 2. Multi-Process Scenario Matrix (Scenarios A–F)

| Scenario | Description | Processes Spawned | Pre-Fix Result (`b47f08d`) | Post-Fix Result |
| :--- | :--- | :--- | :--- | :--- |
| **Scenario A: Revocation Visibility & Restart Persistence** | Login on Process A $\rightarrow$ verify `200 OK` on Process A & Process B $\rightarrow$ logout on Process A $\rightarrow$ replay session on Process B (`POST /api/workspace`, `GET /api/workspace`, `GET /api/auth/session`) $\rightarrow$ verify `401` rejection & raw `sid` absent from disk $\rightarrow$ kill and restart Process A2 & B2 $\rightarrow$ verify `401` persists. | 4 OS processes (`A`, `B`, `A2`, `B2`) | **FAIL** (Process B returned `200 OK` after logout on Process A) | **PASS** (`401` on Process B, `401` after restart, only `sha256(sid)` stored on disk) |
| **Scenario B: Concurrent Logout (No Lost Updates)** | Issue 16 distinct sessions $\rightarrow$ warm up Process A & B $\rightarrow$ concurrently execute 16 parallel logouts split across Process A (even sessions) and Process B (odd sessions) $\rightarrow$ verify all 16 revocations are preserved across Process A, Process B, and a newly spawned Process C. | 3 OS processes (`A`, `B`, `C`) | **FAIL** (Concurrent writes clobbered each other; `isRevoked` returned `false`) | **PASS** (16/16 revocations preserved across `A`, `B`, and `C`; zero lost updates) |
| **Scenario C: Cross-Process Membership, Disable, Delete & Role Downgrades** | Issue 5 sessions $\rightarrow$ verify initial privileged access (`review_clause`, `delete_policy`) on Process B $\rightarrow$ on Process A: (1) disable user, (2) delete user, (3) remove `tenant-beta` membership, (4) downgrade Reviewer $\rightarrow$ Analyst, (5) downgrade Admin $\rightarrow$ Reviewer $\rightarrow$ verify immediate enforcement on Process B without restart. | 2 OS processes (`A`, `B`) | **FAIL** (`runtimeUserOverrides` was process-local; `deleteRuntimeWorkspaceUser` missing) | **PASS** (Disabled $\rightarrow$ `401`, Deleted $\rightarrow$ `401`, Tenant removed $\rightarrow$ `403`, Reviewer downgrade $\rightarrow$ `403` on review & `X-Role: analyst`, Admin downgrade $\rightarrow$ `403` on `delete_policy`) |
| **Scenario D: Cross-Process Login Rate Limiting & Header Spoofing** | Send 3 failed logins to Process A + 2 failed logins to Process B for `analyst` while rotating spoofed `X-Forwarded-For` headers (`203.0.113.10`..`14`) $\rightarrow$ verify 6th attempt on Process B and 7th attempt on Process A are rejected with `429 Too Many Requests`. | 2 OS processes (`A`, `B`) | **FAIL** (6th attempt returned `200 OK` due to per-process Map and `X-Forwarded-For` spoofing) | **PASS** (6th and 7th attempts rejected with `429 Too Many Requests` across both processes) |
| **Scenario E: Fail-Closed on Storage Corruption & Multi-Instance Guard** | Establish valid session $\rightarrow$ corrupt `SESSION_REVOCATION_PATH` with invalid JSON $\rightarrow$ verify Process B fails closed (`503`/`401`) instead of falling back to memory; verify `DEPLOYMENT_TOPOLOGY=multi_instance` returns `503` (`ready: false`). | 3 OS processes (`A`, `B`, `Multi`) | **FAIL** (Corrupted file fell back to memory and returned `200 OK`) | **PASS** (Corrupted storage returns `503` fail-closed; `multi_instance` returns `503` `ready: false`) |
| **Scenario F: Legacy v1 Migration & Expiration Pruning** | Seed `SESSION_REVOCATION_PATH` with v1 array containing active and expired raw `sid` entries $\rightarrow$ verify Process A & B enforce active entry and ignore expired entry $\rightarrow$ trigger write on Process A $\rightarrow$ verify upgrade to `version: 2` with raw `sid` replaced by SHA-256 digest. | 2 OS processes (`A`, `B`) | N/A | **PASS** (Seamless v1 $\rightarrow$ v2 migration, raw `sid` hashed, expired entries pruned) |

---

## 3. Full Verification Suite Output

### 3.1 Frontend Security & Multi-Process Suite (`pnpm --dir web test`)

```text
 RUN  v4.1.12 C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web

 ✓ tests/analysis.test.ts (8 tests) 6ms
 ✓ tests/proxy.test.ts (4 tests) 17ms
 ✓ tests/workspace_gateway.test.ts (9 tests) 120ms
 ✓ tests/p0_security_matrix.test.ts (50 tests) 1094ms
 ✓ tests/p06_multiprocess_security.test.ts (6 tests) 5024ms
     ✓ Scenario A: Revocation Visibility Across Running OS Processes & After Process Restarts (plus SHA-256 SID digest storage)  961ms
     ✓ Scenario B: Concurrent Logout Across Separate Processes Preserves Every Revocation (No Lost Updates)  1645ms
     ✓ Scenario C: Cross-Process Membership, Account Disable/Delete & Role Downgrade Enforcement  867ms
     ✓ Scenario D: Cross-Process Login Rate Limiting Cannot Be Bypassed By Worker Distribution Or Spoofed X-Forwarded-For  584ms
     ✓ Scenario E: Fail-Closed Behaviour When Security State Storage Is Corrupted Or Multi-Instance Is Unsafely Configured  608ms
     ✓ Scenario F: Backward-Compatible Migration From Legacy v1 Revocation Format & Expired Entry Pruning  358ms

 Test Files  5 passed (5)
      Tests  77 passed (77)
```

### 3.2 Production Build & TypeScript Verification (`pnpm --dir web build`)

```text
   ▲ Next.js 15.5.28
   Creating an optimized production build ...
 ✓ Compiled successfully in 1539ms
   Linting and checking validity of types ...
 ✓ Generating static pages (10/10)
```

### 3.3 Backend FastAPI & Live PostgreSQL 16 RLS Suite (`pytest backend/tests`)

```text
218 passed, 3 skipped, 36 warnings in 12.96s
```
