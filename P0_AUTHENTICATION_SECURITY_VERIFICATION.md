# P0 Authentication & Security Verification Report

## 1. Security Invariants Preserved (Zero Weakening)

No security boundary, credential hash policy, revocation mechanism, or confidentiality control was relaxed to restore green CI. Specifically:

1. **Fail-Closed Production Boundaries (`ENV=production`):**
   - Missing `WORKSPACE_SESSION_SECRET` or missing `CROSSWALK_API_KEY` fails closed (`503`).
   - `ALLOW_LOCAL_DEV_AUTH_BYPASS=true` is ignored in `ENV=production`.
   - Default development fixture users (`analyst`, `reviewer`, `viewer`, `admin` and plaintext/unsalted SHA-256 credentials) are never loaded or accepted in `ENV=production`.
   - Private workspace routes (`/api/workspace` GET/POST) reject `public-demo` and unauthenticated sessions (`401`/`403`).
   - Only `scrypt` and `PBKDF2` password hashes are accepted for provisioned `WORKSPACE_USERS_JSON` identities in production.
2. **Cross-Process Durable Revocation & Membership Integrity:**
   - `DurableRevocationStore` (`web/app/security.ts`) continues using atomic file-locked updates and SHA-256 session ID digests across separate OS worker processes in runtime and `p06_multiprocess_security.test.ts`.
   - Vitest-only worker isolation in `DurableRevocationStore.resolveFilePath()` triggers only when `VITEST_WORKER_ID` is defined and `SESSION_REVOCATION_PATH` is unset, preventing unrelated Vitest files from unlinking each other's temp store while leaving `SESSION_REVOCATION_PATH` multi-process behaviour (verified by P0.6 Scenarios A–F) 100% intact.
3. **CSRF, Origin & RBAC Enforcement:**
   - Cookie-authenticated state mutations require valid `X-CSRF-Token` and same-origin headers (`403` otherwise).
   - Live role downgrades, disabled/deleted accounts, and tenant membership removals invalidate active session tokens immediately on next request.
4. **LLM Confidentiality Policy Precedence (Gemini E3):**
   - `enforce_runtime_confidentiality(config, *, data_classification, tenant_id=None)` (`backend/banking_crosswalk/llm/security.py`) runs at the entry of `retrieve_reconciliation_candidates_hybrid`, `generate_hybrid_reconciliation_candidates`, and `suggest_questionnaire_mappings_hybrid` **before** `build_provider_bundle(cfg)` or any provider HTTP / credential check.
   - Confidential enterprise text (`CONFIDENTIAL_ENTERPRISE`) paired with Gemini free tier (whether via `embedding_provider == "gemini"` or `reasoning_provider == "gemini"` in `HYBRID` mode, and regardless of `GEMINI_API_KEY` presence) deterministically raises `ConfidentialityPolicyError` -> HTTP **403**, never falling through to HTTP 503 (`ProviderConfigurationError`) or transmitting regulatory/enterprise strings over HTTPS.
   - Verified in `backend/tests/test_e3_semantic_matching.py::test_e3_06b_confidentiality_vs_config_precedence_matrix` across all 6 precedence combinations.

---

## 2. Authentication Security Verification Matrix

| Security Group / Check | Suite / Test | Observed Result |
| :--- | :--- | :--- |
| Anonymous private workspace blocking (A1–A12) | `web/tests/p0_security_matrix.test.ts` | Passed (`401`, backend never called) |
| Token/session integrity, B8 revocation under parallel Vitest workers (B1–B10) | `web/tests/p0_security_matrix.test.ts` | Passed (`401`; zero B8 `502` races) |
| CSRF & `Origin` checks, cookie attributes `HttpOnly; SameSite=Lax` (C1–C5) | `web/tests/p0_security_matrix.test.ts` | Passed |
| RBAC viewer/analyst/reviewer separation & live downgrade (D1–D11) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Cross-tenant isolation & `public-demo` boundary on `/api/workspace` (E1–E9) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Anonymous stateless `/api/analysis` (`DEMO_BANKING_V1` only) (F1–F6) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Production fail-closed `ENV=production` secret/bypass checks (G1–G4) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Scrypt/PBKDF2 verification & login 429 rate limiting (H1–H4) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Production fixture-user absence & proxy-header bypass denial (I1–I2) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Durable disk revocation, deleted user, tenant removal & role downgrade (J1–J4) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Static token viewer-only cap & OIDC production readiness fail-closed (K1–K2, L1–L2) | `web/tests/p0_security_matrix.test.ts` | Passed |
| Cross-process OS subprocess revocation, concurrency, rate-limit & migration (Scenarios A–F) | `web/tests/p06_multiprocess_security.test.ts` | 6/6 passed |
| Web gateway / proxy / analysis unit suites | `workspace_gateway.test.ts`, `proxy.test.ts`, `analysis.test.ts` | 22/22 passed |
| Live Chromium E2E Production Public Demo security lock + anonymous demo | `web/e2e/scenario_a_public_demo.spec.ts` | Passed locally (`1.4s`) |
| Live Chromium E2E Private Workspace ephemeral scrypt sign-in + logout replay 401 | `web/e2e/scenario_b_private_workspace.spec.ts` | Passed locally (`1.3s`) |
| Backend E3 Gemini 403 Confidentiality vs 503 Configuration precedence matrix | `test_e3_06b_confidentiality_vs_config_precedence_matrix` | Passed |
| Repository hardcoded-secret scan | `scripts/check_secrets.py` | Passed (0 findings) |

---

## 3. E4 Governance Boundary Check (No Premature Auto-Approval)

`scripts/audit_regulatory_library.py` includes `validate_review_lifecycle_governance(...)`, ensuring:
- Zero runtime records in `atomic_obligation_catalogue.json` or `obligation_control_mappings.json` are `approved` without explicit human legal sign-off (`human_approved=0` today, all runtime records remain `proposed`).
- Future legal approvals require a matching `E4_LEGAL_REVIEW_REGISTER.csv` record with `runtime_review_status == "approved"`, `signoff_decision` beginning with `"APPROVED"`, non-empty reviewer identity/timestamp/rationale, non-`source_unavailable` validation status, and no unremediated `P0` `needs_correction`.
