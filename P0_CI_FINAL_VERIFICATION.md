# P0 CI Stabilisation & Security Regression Repair — Verification Summary

## 1. Local Verification Executed (2026-11-16)

| Check | Command | Exact Result |
| :--- | :--- | :--- |
| **Backend Lint** | `.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend scripts` | `All checks passed!` (exit 0) |
| **Secret Scan** | `.venv\Scripts\python.exe scripts/check_secrets.py` | `Secret scan passed: no recognised credential patterns in publishable files.` (exit 0) |
| **Backend Test Suite** | `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest backend/tests -q -rs` | **265 passed, 19 skipped** (skips: 17 `TEST_DATABASE_URL` PostgreSQL-only tests exercised in CI `postgres` jobs, 1 opt-in live Gemini test `RUN_GEMINI_LIVE_TESTS=1`, 1 local AIAF acceptance workbook not present) |
| **E3 Semantic Precedence Tests** | `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest backend/tests/test_e3_semantic_matching.py -q` | **15 passed, 1 skipped** (opt-in live Gemini) |
| **E4 Regulatory Governance Audit** | `.venv\Scripts\python.exe scripts/audit_regulatory_library.py` | **12/12 checks passed**, `human_approved=0`, `deliverables passed=True` |
| **E3 Benchmark Harness (Direct Script)** | `$env:PYTHONPATH=""; .venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py --provider mock --benchmark e31 --split dev` | Exited 0 cleanly with zero `tests` package import errors |
| **Web Unit & Security Matrix** | `npm --prefix web test` | **5 test files passed, 79 passed / 79 total** (including all 51 security matrix checks C1–C6 and 6 cross-process OS concurrency scenarios) |
| **Web Typecheck & Production Build** | `npm --prefix web run typecheck` + `npm --prefix web run build` | Both exited 0 |
| **Playwright Scenario A (Local Prod Build)** | `npx playwright test e2e/scenario_a_public_demo.spec.ts` | **1 passed (1.4s)** against `ENV=production`, `public-demo` |
| **Playwright Scenario B (Local Web Prod + Migrated API)** | `npx playwright test e2e/scenario_b_private_workspace.spec.ts` | **1 passed (1.3s)** against `ENV=production` `next start` + schema-migrated SQLite API (`ci-private-workspace`, ephemeral `scrypt` creds) |

---

## 2. Pull Request & Remote GitHub Actions CI Status

- **PR #36 (Merged early at `78346d4` -> `8fc0b5b`):** Landed core backend test-package isolation, Vitest B8/P0.6 race/timeout fixes, Gemini confidentiality precedence, E4 review lifecycle gate, and Playwright Scenario A/B split.
- **Follow-on PR (`fix/p0-ci-containers-csrf-followon` against `main`):** Lands the remaining three container CI & standalone CSRF origin fixes verified in green CI run [`43789944621`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/43789944621) (`4m59s`, 2026-11-16T02:04:33Z):
  - `backend (3.11)`: passed (`36s`)
  - `backend (3.13)`: passed (`55s`)
  - `postgres (17)`: passed (`46s`)
  - `postgres (18)`: passed (`48s`)
  - `web`: passed (`45s`)
  - `containers` (smoke test + Scenario A + PostgreSQL restart persistence smoke test + Scenario B against PostgreSQL 17 & standalone `0.0.0.0:3000` web): passed (`4m55s`)
  - `CodeQL` (`analyze (python)` + `analyze (javascript-typescript)` on [`43786291416`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/43786291416)): passed (`1m10s`; pending re-check on follow-on PR)

---

## 3. Recommended GitHub Branch Protection / Ruleset Settings (Advisory Only)

Repository settings were **not** modified by this PR. Once PR A is verified green, maintainers should configure branch protection / rulesets on `main` to require PR approval and require all CI jobs to pass before merging:

- `backend (3.11)`
- `backend (3.13)`
- `postgres (17)`
- `postgres (18)`
- `web`
- `containers`
- CodeQL analysis (`Analyze (javascript-typescript)` and `Analyze (python)`)

Disallow admin bypass on failing checks so regressions cannot merge to `main` silently as occurred between PR #25 and PR #35.
