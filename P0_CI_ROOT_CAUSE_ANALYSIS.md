# P0 CI Root Cause Analysis & Historical Timeline

## 1. Executive Summary

Following merge PR #24 (`42360679890`, `2026-11-07T09:39:53Z` — last completely green `CI` run on `main`), `main` and subsequent pull requests (#25 through #35) accumulated multiple interacting CI failures across `web`, `containers`, and `backend` jobs. These regressions were masked across merges when PRs merged without enforcing all required status checks.

Every failure identified in PR #35 (`43717669287`, `2026-11-15T13:11:09Z`) and its merge commit (`43717835266`, `2026-11-15T13:13:01Z`), as well as earlier PR #25 (`42611379721`), PR #27 (`43015866644`), PR #30 (`43594837296`), PR #33 (`43690843867`), and PR #34 (`43710573491`), has been audited against raw GitHub Actions job logs and classified strictly below.

---

## 2. Historical Timeline (PR #24 → PR #35)

| Milestone | GitHub Actions Run ID(s) | Timestamp (UTC) | Failing Job(s) | Exact Failure & Classification |
| :--- | :--- | :--- | :--- | :--- |
| **PR #24** (Last Green `main`) | `42360679890` | `2026-11-07T09:39:53Z` | *None* (`4m0s` green) | Baseline green `main` before PR #25 regression. |
| **PR #25** (`feat/document-first-two-upload-questionnaire`) | `42604879590`, `42608796064`, `42611379721` | `2026-11-09T10:55–11:44Z` | `web`, `containers` | **Confirmed implementation defect (fixed later in PR #27):** Next.js 15 Route type validation failed `npm run build` (`"MAX_WORKSPACE_UPLOAD_BYTES" is not a valid Route export field` in `web/app/api/workspace/route.ts`). Passed `backend` and `postgres` jobs; failed `web` build and `containers` Docker build. |
| **PR #27 – PR #32** (`fix/p0-authenticated-document-workspace` → `fix/e11-...`) | `43015866644` (PR #27), `43594837296` (PR #30), `43601443782` (PR #31), `43684422465` (PR #32) | `2026-11-11` → `2026-11-15T06:13Z` | `containers` | **Confirmed CI/test specification mismatch:** Security hardening intentionally disabled dev fixture accounts (`analyst` / `analyst-local-pass`) in `ENV=production` and locked `/api/workspace` when `BANKING_CROSSWALK_TENANT_ID=public-demo`. `web/e2e/app.spec.ts:57` still attempted to sign in as `analyst` and assert `session-badge` contained `"analyst"`, receiving `"Sign-In Required for Private Workspace"`. |
| **PR #33 – PR #35** (`feat/e3-...`, `feat/e31-...`, `feat/e4-...`) | `43690843867` (PR #33), `43710573491` (PR #34), `43717669287` (PR #35), `43717835266` (PR #35 merge) | `2026-11-15T07:38Z` → `13:13Z` | `backend (3.11)`, `backend (3.13)`, `containers` | **Confirmed test import/packaging defect + CI matrix cancellation:** `backend/tests/test_e3_semantic_matching.py:93` imported `from tests.e3_benchmark_dataset import ...`, failing pytest collection (`ModuleNotFoundError: No module named 'tests'`) when `backend` is pip-installed (`pip install -e ./backend[dev,postgres]`) without `PYTHONPATH=.`. Default matrix `fail-fast: true` then cancelled the sibling Python version job (`3.11` or `3.13`). |
| **PR #35** (`feat/e4-regulatory-content-validation`) | `43717669287` (PR #35) | `2026-11-15T13:11:09Z` | `web` (in addition to `backend` and `containers`) | **Confirmed test isolation race:** `web/tests/p0_security_matrix.test.ts:319` (B8: revoked user session -> `401`) intermittently failed receiving `502` under parallel Vitest worker execution. |

---

## 3. Detailed Root Cause Classifications & Fixes

### Finding 1 — `backend (Python 3.11 / 3.13)`: `ModuleNotFoundError: No module named 'tests'` & Matrix Cancellation

- **Classification:** Confirmed test import / packaging defect (plus CI `fail-fast` cancellation masking).
- **Root Cause:**
  1. `backend/pyproject.toml` declares `packages.find` restricted to `include = ["banking_crosswalk*"]` and `testpaths = ["tests"]`. With `pytest`'s `importlib`/default path handling inside `python -m pytest backend/tests -q`, `backend/tests/` is on `sys.path`, NOT its parent directory `backend/`, so `from tests.*` raises `ModuleNotFoundError: No module named 'tests'`.
  2. `backend/tests/test_e3_semantic_matching.py`, `backend/tests/e3_benchmark_dataset.py`, and `scripts/evaluate_e3_live_gemini.py` used `from tests.*` imports (`tests.e3_benchmark_dataset`, `tests.e31_calibration_dataset`, and indirectly `tests.test_e11_accuracy_and_effective_baseline_e2e`).
  3. `.github/workflows/ci.yml` omitted `fail-fast: false` on the `backend` Python matrix, cancelling `backend (3.13)` whenever `backend (3.11)` failed first (or vice versa), preventing independent signal across Python 3.11 and 3.13.
  4. Locally, the project `.venv` still had a stale editable `.pth` pointing at an earlier repository directory, masking code vs packaging drift until reinstalled.
- **Remediation (No global `PYTHONPATH` hacks):**
  - Extracted shared E1.1 benchmark clause fixtures and PDF/DOCX byte helpers out of `test_e11_accuracy_and_effective_baseline_e2e.py` into `backend/tests/e11_benchmark_dataset.py` (pytest-side-effect-free).
  - Updated `backend/tests/test_e11_accuracy_and_effective_baseline_e2e.py`, `backend/tests/e3_benchmark_dataset.py`, and `backend/tests/test_e3_semantic_matching.py` to import sibling dataset modules directly (`from e11_benchmark_dataset import ...`, `from e3_benchmark_dataset import ...`, `from e31_calibration_dataset import ...`).
  - Updated `scripts/evaluate_e3_live_gemini.py` to place both `BACKEND_DIR` and `BACKEND_TESTS_DIR` on `sys.path` cleanly.
  - Added `strategy.fail-fast: false` to the `backend` matrix in `.github/workflows/ci.yml`.
  - Refreshed the local editable install (`pip install --no-build-isolation --no-deps -e ./backend`) and verified all tests with `$env:PYTHONPATH=""`.

---

### Finding 2 — `web`: Intermittent B8 `502` vs `401` Race & Multi-Process Test Timeouts

- **Classification:** Confirmed test isolation defect (`DurableRevocationStore` shared default path across parallel Vitest workers) and CPU-contention timeout vulnerability.
- **Root Cause:**
  1. `web/tests/p0_security_matrix.test.ts` and `web/tests/workspace_gateway.test.ts` executed concurrently across separate Vitest worker processes without overriding `SESSION_REVOCATION_PATH`.
  2. Both suites resolved the default fallback path (`/tmp/crosswalk_revocations.json` on Linux, `os.tmpdir()/crosswalk_revocations.json` on Windows) via `DurableRevocationStore.resolveFilePath()`.
  3. `workspace_gateway.test.ts`'s `afterEach` called `clearSecurityStateForTests()`, calling `fs.unlinkSync(...)` on that shared file *during* `p0_security_matrix.test.ts`'s `B8` assertion (`revokeSession(sid)` -> `workspacePOST`), wiping the revocation record before `resolveSecurityContext()` checked it. The revoked request then passed auth and hit unmocked `fetch("http://127.0.0.1:8000/...")` -> `502 Bad Gateway` instead of `401`.
  4. Under parallel CPU load, `web/tests/p06_multiprocess_security.test.ts` Scenarios A and B (spawning real Node subprocesses) hovered near Vitest's default 5000ms timeout (measured up to ~4.98s–5.21s locally before adjustment).
- **Remediation (Security behaviour preserved):**
  - Scoped Vitest's unconfigured fallback path inside `DurableRevocationStore.resolveFilePath()` (`web/app/security.ts`) using `process.env.VITEST_WORKER_ID` (`crosswalk_revocations_vitest_<worker>.json`), leaving non-Vitest runtime paths (`SESSION_REVOCATION_PATH` or `/tmp/crosswalk_revocations.json`) completely unchanged so multi-process production/P0.6 workers still share one revocation store.
  - Isolated `web/tests/p0_security_matrix.test.ts` and `web/tests/workspace_gateway.test.ts` with explicit per-test temp directories via `vi.stubEnv("SESSION_REVOCATION_PATH", ...)` in `beforeEach` and deterministic teardown in `afterEach`.
  - Added explicit `25_000` ms test timeouts to the 6 multi-process OS child-process scenarios in `web/tests/p06_multiprocess_security.test.ts`.

---

### Finding 3 — `containers`: Playwright E2E Failure against Production Security Boundary

- **Classification:** Confirmed CI/test specification mismatch against intentional P0/P0.5/P0.6 security controls.
- **Root Cause:**
  - `containers` booted the Compose stack with `ENV: production` and `BANKING_CROSSWALK_TENANT_ID: public-demo`.
  - Under P0.5/P0.6 security rules, `ENV=production` refuses dev fixture credentials (`analyst` / `analyst-local-pass`) and blocks `/api/workspace` for `public-demo`.
  - `web/e2e/app.spec.ts` tested only dev-fixture login + private upload in that locked-down container, guaranteeing deterministic failure (`session-badge` stayed `"Sign-In Required for Private Workspace"`).
- **Remediation:** Replaced obsolete `web/e2e/app.spec.ts` with two explicit CI scenarios:
  - **Scenario A** (`web/e2e/scenario_a_public_demo.spec.ts`): Validates `ENV=production` + `public-demo` fails closed on `/api/workspace` and dev fixture creds, while anonymous synthetic demo (`DEMO_BANKING_V1`) succeeds end-to-end.
  - **Scenario B** (`web/e2e/scenario_b_private_workspace.spec.ts`): Boots Compose with PostgreSQL 17, non-demo tenant `ci-private-workspace`, `ALLOW_LOCAL_DEV_AUTH_BYPASS=false`, ephemeral runtime `WORKSPACE_SESSION_SECRET`, and scrypt-hashed ephemeral CI credentials in `WORKSPACE_USERS_JSON`; verifies fail-closed 401/403, UI login, `HttpOnly` cookie storage, private policy persistence, logout revocation, and session replay rejection (`401`).

---

### Finding 4 — Additional Pre-Existing Robustness Gaps Resolved in PR A

1. **Gemini Confidentiality vs Configuration Error Precedence:** `semantic_reconciliation.py` initialized `build_provider_bundle(cfg)` / embedded public regulatory obligations before checking `enforce_free_tier_confidentiality`, allowing `ProviderConfigurationError` (503) or real HTTPS embedding requests to pre-empt `ConfidentialityPolicyError` (403) when `GEMINI_API_KEY` was unset on `CONFIDENTIAL_ENTERPRISE` clauses. Extracted and enforced `enforce_runtime_confidentiality(...)` at entry to all three hybrid entry points (`retrieve_reconciliation_candidates_hybrid`, `generate_hybrid_reconciliation_candidates`, `suggest_questionnaire_mappings_hybrid`).
2. **Future E4.1 Human Review Signoff Governance:** `scripts/audit_regulatory_library.py` previously forbade *any* `"approved"` record statically, blocking future qualified human legal sign-off workflows (PR B / E4.1). Added `validate_review_lifecycle_governance(...)` which keeps all E4 records at `proposed` today (`human_approved=0`), while permitting `approved` only when backed by a matching `E4_LEGAL_REVIEW_REGISTER.csv` human review row (`runtime_review_status="approved"`, `signoff_decision` starting with `"APPROVED"`, non-empty reviewer identity/timestamp/rationale, not `source_unavailable`, and not unremediated `P0` `needs_correction`).
3. **PostgreSQL Persistence Smoke Test Masked Tenant Conflict (`containers` job):** Once Playwright Scenario A passed in PR #36, the previously skipped `scripts/persistence_smoke_test.py create` step ran against `ENV=production` with job-level `BANKING_CROSSWALK_TENANT_ID=public-demo` and received `HTTP Error 403: Forbidden` (because `_reject_public_demo_tenant` intentionally restricts `public-demo` to stateless synthetic assessments). Scoped the optional PostgreSQL persistence smoke steps in `.github/workflows/ci.yml` to a dedicated non-demo tenant (`BANKING_CROSSWALK_TENANT_ID: ci-persistence-smoke`).
4. **Standalone Container `0.0.0.0:3000` CSRF Origin Mismatch on Browser Logout & Mutations:** When Playwright Scenario B ran against the Next.js standalone Docker image (`HOSTNAME=0.0.0.0 PORT=3000`), browser `POST /api/auth/logout` (with `Origin: http://localhost:3000` and `Host: localhost:3000`) failed `verifyCsrfProtection` with `403` because `request.url` reported `http://0.0.0.0:3000` while `isLoopback()` did not match `0.0.0.0`, leaving the session cookie unrevoked (`200` on replay after UI sign-out). Updated `verifyCsrfProtection` (`web/app/security.ts`) to resolve the `Host` header when `request.url` uses an unspecified bind host (`0.0.0.0` / `::`), forwarded `ENV` to `web` in `compose.yaml`, added `C6` test coverage in `web/tests/p0_security_matrix.test.ts`, and asserted `/api/auth/logout` HTTP `200` in Scenario B.
