# DeepAudit Crosswalk — P0.6 Cross-Process Revocation, Membership & Rate-Limit Audit

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Base Commit Audited:** `b47f08d8e1de1e351c407f2bc4b4aba72bbb47ca` (PR #29 Merge)  
**Target Remediation Branch:** `fix/p06-cross-process-session-consistency`  
**Priority:** P0 — Authentication Consistency & Security Release Correction

---

## 1. Executive Summary

Following the merge of PR #29 (`b47f08d8e1de1e351c407f2bc4b4aba72bbb47ca`), an independent source-code and multi-process runtime audit was conducted on `web/app/security.ts` and the Next.js authentication routes (`/api/auth/login`, `/api/auth/logout`, `/api/auth/session`, `/api/workspace`).

The audit confirmed **six release-blocking multi-process and fail-open defects** in PR #29's `DurableRevocationStore`, `runtimeUserOverrides`, and login rate-limiting implementation:

| Finding ID | Component (`web/app/security.ts`) | Confirmed Defect in `b47f08d` | Security Impact |
| :--- | :--- | :--- | :--- |
| **F-P06-1** | `DurableRevocationStore.ensureLoaded()` | Read-once initialization guard (`if (this.initialized) return;`) prevented already-running worker processes from ever re-reading `SESSION_REVOCATION_PATH` after initial startup. | **Critical:** A session logged out on Worker Process A remained accepted (`200 OK`) on Worker Process B indefinitely until Process B restarted. |
| **F-P06-2** | `DurableRevocationStore.persist()` | Overwrote the entire revocation file from `this.memory` without a cross-process lock or read-modify-write cycle. | **High:** Concurrent logouts across Process A and Process B overwrote each other on disk (classic lost-update race condition), silently un-revoking previously logged-out sessions. |
| **F-P06-3** | `ensureLoaded()` & `persist()` error handling | Caught all filesystem and JSON parse errors with empty `catch {}` blocks (`// In-memory fallback`). | **High:** Corrupted or unreadable revocation state silently fell back to empty process-local memory (fail-open), re-validating revoked sessions and bypassing disabled/downgraded user states. |
| **F-P06-4** | `RevocationEntry` storage format | Persisted raw session identifiers (`sid`) in plaintext JSON without explicit `0600` file permissions. | **Medium:** Unnecessary exposure of raw session identifiers on disk and lacked explicit owner-only (`0600`) file mode enforcement. |
| **F-P06-5** | `runtimeUserOverrides` (`Map`) | Stored user disablement (`setRuntimeUserDisabled`), role downgrades, and tenant membership removal (`setRuntimeUserTenantRoles`) exclusively in process-local RAM; lacked user deletion (`deleteRuntimeWorkspaceUser`). | **Critical:** Disabling a user, deleting a user, removing tenant membership, or downgrading a `reviewer`/`admin` on Process A had zero effect on Process B, which continued granting full privileges from its stale local state. |
| **F-P06-6** | `failedLoginAttempts` & `getLoginRateLimitKey()` | Stored login failure counters in process-local RAM and unconditionally trusted client-supplied `X-Forwarded-For` headers. | **High:** Attackers could bypass the 5-attempt login rate limit either by hitting multiple worker processes or by rotating a spoofed `X-Forwarded-For` header on every request. |

---

## 2. Why PR #29's Unit Test (`J1`) Missed the Multi-Process Defect

In PR #29 (`web/tests/p0_security_matrix.test.ts`, test `J1`), multi-process durability was tested sequentially within a single process:
1. `storeA` was instantiated and called `storeA.revoke(testSid)`.
2. Only **after** `storeA.revoke(testSid)` wrote to disk was `storeB` instantiated for the first time (`const storeB = new DurableRevocationStore(); storeB.isRevoked(testSid)`).
3. Because `storeB.initialized` was `false` at that moment, `storeB.ensureLoaded()` read the file once and passed.
4. However, in any real multi-process deployment, **both Process A and Process B are already running and initialized** before a user logs out. Once `storeB.initialized` became `true`, `storeB` never read from disk again.

---

## 3. Pre-Fix Reproduction Across Real OS Processes

Before modifying any application code, we created `web/tests/helpers/security_process_worker.cjs` and `web/tests/p06_multiprocess_security.test.ts`, which spawn **real, independent Node.js OS child processes** (`child_process.spawn(process.execPath, ...)`) with distinct OS PIDs (`procA.pid !== procB.pid !== process.pid`) executing the actual Next.js route handlers (`login/route.ts`, `logout/route.ts`, `session/route.ts`, `workspace/route.ts`).

### Verbatim Pre-Fix Failure Output on `b47f08d8e1de1e351c407f2bc4b4aba72bbb47ca`

```text
 RUN  v4.1.12 C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web

 ❯ tests/p06_multiprocess_security.test.ts (5 tests | 5 failed) 3299ms
     × Scenario A: Revocation Visibility Across Running OS Processes & After Process Restarts (plus SHA-256 SID digest storage) 413ms
     × Scenario B: Concurrent Logout Across Separate Processes Preserves Every Revocation (No Lost Updates) 1162ms
     × Scenario C: Cross-Process Membership, Account Disable/Delete & Role Downgrade Enforcement 767ms
     × Scenario D: Cross-Process Login Rate Limiting Cannot Be Bypassed By Worker Distribution Or Spoofed X-Forwarded-For 574ms
     × Scenario E: Fail-Closed Behaviour When Security State Storage Is Corrupted Or Multi-Instance Is Unsafely Configured 381ms

 FAIL  Scenario A: Revocation Visibility Across Running OS Processes & After Process Restarts
AssertionError: expected 200 to be 401 // Object.is equality
 ❯ tests/p06_multiprocess_security.test.ts:222:39
    222|     expect(accessBAfterLogout.status).toBe(401);

 FAIL  Scenario B: Concurrent Logout Across Separate Processes Preserves Every Revocation
AssertionError: expected false to be true // Object.is equality
 ❯ tests/p06_multiprocess_security.test.ts:329:28
    329|       expect(revB.revoked).toBe(true);

 FAIL  Scenario C: Cross-Process Membership, Account Disable/Delete & Role Downgrade Enforcement
AssertionError: expected false to be true // Object.is equality
 ❯ tests/p06_multiprocess_security.test.ts:461:20
    461|     expect(op2.ok).toBe(true);

 FAIL  Scenario D: Cross-Process Login Rate Limiting Cannot Be Bypassed By Worker Distribution Or Spoofed X-Forwarded-For
AssertionError: expected 200 to be 429 // Object.is equality
 ❯ tests/p06_multiprocess_security.test.ts:581:34
    581|     expect(sixthAttemptB.status).toBe(429);

 FAIL  Scenario E: Fail-Closed Behaviour When Security State Storage Is Corrupted Or Multi-Instance Is Unsafely Configured
AssertionError: expected [ 401, 503 ] to include 200
 ❯ tests/p06_multiprocess_security.test.ts:629:24
    629|     expect([401, 503]).toContain(afterCorruptB.status);
```
