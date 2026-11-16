# E4.1 Release Readiness & Assurance Gate

**Target Version:** `regulatory_pack` `0.2.0` (`2026.11-au-banking-v0.2.0`), `obligation_control_mappings` `1.1.0`  
**Branch:** `fix/e41-regulatory-accuracy-remediation`

## 1. Readiness Decision

- **Technical & Engineering Remediation Gate:** **PASS / GO FOR MERGE REVIEW** (pending final green full backend/frontend test suite and PR CI/CodeQL confirmation below).
- **Legal Substantive Approval Gate:** **HUMAN LEGAL SIGN-OFF REQUIRED PRIOR TO CUSTOMER PRODUCTION RELIANCE** (`human_approved = 0`; all `17` sources, `46` obligations, `55` active mappings, and `5` completeness candidates remain in `proposed` status).

## 2. Release Checklist Verification

| Check | Status | Notes |
|---|---|---|
| P0 source & obligation accuracy corrections (`AU-PRIV-APP11-SECURITY`, `APRA-CPS220`, `ASIC-RG271`, `EU-AI-ACT`) | Completed | Verified against FRL (`C2024A00128`, `F2019L00669`, `F2022L00430`) and EUR-Lex (`CELEX:32024R1689`, `CELEX:32026R1744`). |
| EU AI Act Art 50 split & Regulation (EU) 2026/1744 phased applicability rules | Completed | Added `EU-AIA-ART50-TRANSPARENCY` (`2026-08-02`, `MAP-PRIMARY-046`) and updated `_eu` / `_eu_transparency` / `_eu_deployer_high_risk`. |
| Mapping remediation (`MAP-CROSS-007` dedup, `non_equivalent` guards, 5 over-broad `full` downgrades) | Completed | `duplicate_pairs=0`, `non_eq_mapped=0`, `broad_guidance_full=4` (down from 9). |
| Pack version bump & Effective Baseline staleness compatibility | Completed | Pack `0.2.0` invalidates `0.1.0` approvals into stale/unresolved for human re-review. |
| P0 completeness gap candidate register | Completed (Unimported) | `E41_CANDIDATE_REQUIREMENTS_REGISTER.csv` holds 5 candidates (`review_status=proposed`, `imported_to_runtime=false`). |
| Structural QA (`scripts/audit_regulatory_library.py`) | Passed (`12/12`) | Root and `backend/banking_crosswalk/data/` byte-for-byte parity confirmed (`46` obligations, `55` mappings, `126` register rows). |
| Backend test suite (`pytest backend/tests -q`) | Passed (`276` passed, `19` skipped, `0` failed) | Skipped tests are live-Gemini / PostgreSQL integration tests gated by `GEMINI_API_KEY` / `DATABASE_URL` in CI Postgres jobs. |
| Static lint & secret scan (`ruff`, `scripts/check_secrets.py`) | Passed | Zero ruff findings; zero secrets in publishable files. |
| Frontend suite (`npm --prefix web test`, `typecheck`, `build`) | Passed (`79/79` vitest tests; `tsc --noEmit`; `next build`) | Zero regressions on proxy, gateway, or P0/P0.6 security suites. |
| GitHub Actions CI & CodeQL | Pending PR run | Triggered upon branch push and PR creation against `main`. |

## 3. Open Deferred Items

- 3 APRA CPS 230/234 temporal/boundary items (`AU-APRA-CPS230-OPS`, `AU-APRA-CPS230-BCP`, `AU-APRA-CPS234-INCIDENT`) documented in `E41_PENDING_LEGAL_REVIEW.md` and `E4_LEGAL_REVIEW_REGISTER.csv`.
- Legal/compliance scoping decision on importing `E41_CANDIDATE_REQUIREMENTS_REGISTER.csv` (`GAP-FAR-2023`, `GAP-CORP-912A-DDO-BREACH`, `GAP-ASIC-2022-205`) in a subsequent pack release (`0.3.0`).
- Live commercial ISO overlay verification (`ISO-42001`, `ISO-23894`, `ISO-27001`).
