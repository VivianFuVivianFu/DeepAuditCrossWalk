# E3.4 Final Supply-Chain, CI Verification & Release Decisions

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Audit Date:** 2026-11-20  
**Regulatory Library Baseline:** `AU-BANKING-REG-PACK-0.1` v`0.2.0` (`17` sources, `46` atomic obligations, `33` unified controls, `158` canonical facets, `55` active mappings v`1.1.0`, **`0` human-approved mappings**)  
**Branches Covered:** PR #39 (`1f4a367`), PR #40 (`fa3a7be`), PR #41 (`e74aeaf`), E3.4 Assurance PR (`fix/e34-integration-evaluation-assurance`)

---

## 1. Phase 7 — Supply-Chain Security & Dependency Audit

### 1.1 `picomatch` Advisory Exception Re-Verification (`GHSA-fc5q-39xc-vjpf`)
Executed `node ../scripts/check_web_npm_audit.mjs` and `npm view picomatch versions --json` on **2026-11-20**:
- **Advisory:** `GHSA-fc5q-39xc-vjpf` (`source: 1247710`, ReDoS in `picomatch <= 4.0.7` via single-branch repeated extglobs).
- **Upstream Availability:** Highest published version on npm remains **`4.0.7`** (no upstream fix `> 4.0.7` available).
- **Production Dependency Exposure:** `npm audit --omit=dev --json` reports **`0` high/critical vulnerabilities**.
- **Scope Containment:** `web/package-lock.json` (`packages["node_modules/picomatch"]`) confirms `"dev": true` (`vitest -> vite -> tinyglobby -> fdir -> picomatch`).
- **Exception Guardrails Verified in [`scripts/check_web_npm_audit.mjs`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/check_web_npm_audit.mjs):**
  - Strictly validates npm audit JSON payload (fails closed on network error/403/malformed output).
  - Hard-coded to allow **only** `GHSA-fc5q-39xc-vjpf` / source `1247710` inside `{"picomatch", "fdir", "tinyglobby", "vite", "@vitest/mocker", "vitest"}` when `dev === true`.
  - Any other high/critical advisory remains strictly blocking.
  - Enforced hard expiration: **`2026-12-18T00:00:00Z`** (`exit 1` automatically once reached; never silently renewed or broadened).

### 1.2 Python Dependency Audit (`pip_audit`)
- Local `.venv` scan (`2026-11-20`): flagged stale pre-existing `.venv` packages `pypdf==6.21.3` (`CVE-2026-119203`, `CVE-2026-119204`, `CVE-2026-119205`, fixed in `6.21.4`) and `opentelemetry-api==1.45.1` (`CVE-2026-126360`, fixed in `1.45.2`).
- **Remediation Applied:** Tightened [`backend/pyproject.toml`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/pyproject.toml) dependency floor from `pypdf>=6.21.2,<7` to **`pypdf>=6.21.4,<7`**. Clean CI runners install fresh PyPI wheels (`pip install -e './backend[dev,postgres]'`) and enforce blocking `python -m pip_audit --local --skip-editable`.

---

## 2. Complete Test & CI Verification Evidence

### 2.1 Local Verification Suite on `fix/e34-integration-evaluation-assurance` (`2026-11-20`)
| Verification Check | Observed Result | Scope / Notes |
|---|---|---|
| `pytest backend/tests -q -rs` (Python 3.13) | **`292 passed, 19 skipped`** (`0` failed) | `19` skipped are expected environment-gated tests: `17` PostgreSQL (`TEST_DATABASE_URL` absent), `1` live Gemini (`RUN_GEMINI_LIVE_TESTS` / key absent), `1` local AIAF workbook |
| `pytest scripts/experiments -q` (P1B experimental) | **`25 passed`** (`0` failed) | Canonical adapter (13), `EngineA1` (7), evaluator (4), `EngineA0` (1) against 158 facets |
| `pytest` E1–E4.1 & E3.4 subset (`test_e1*`, `e11`, `e3*`, `e32`, `e33`, `e34`, `e4*`, `regulatory_library`) | **`93 passed, 1 skipped`** (`0` failed) | `1` skipped is live Gemini gated test |
| `python scripts/audit_regulatory_library.py` | **`12/12` checks passed (`valid=True`)** | `17` sources, `46` obligations, `33` controls, `55` mappings, `human_approved=0`, `6/6` synthetic scenarios |
| `ruff check backend scripts/experiments` | **`All checks passed!`** | Zero lint or undefined-name issues |
| `python scripts/check_secrets.py` | **Passed** | Zero recognised credential patterns |
| `web`: `node ../scripts/check_web_npm_audit.mjs` | **Passed** | `0` prod vulnerabilities; `picomatch@4.0.7` dev-only exception expires `2026-12-18` |
| `web`: `npm test -- --run` (Vitest) | **`5 files, 79 passed`** (`0` failed) | Security matrix (`51`), multiprocess auth (`6`), gateway (`10`), analysis (`8`), proxy (`4`) |
| `web`: `npm run typecheck` (`tsc --noEmit`) | **Passed (`0` errors)** | — |
| `web`: `npx next build` | **Passed (`10/10` static pages, `0` errors)** | Clean production Next.js `15.5.28` build |
| Live Gemini evaluation (`--provider gemini`) | **NOT RUN — CREDENTIALS UNAVAILABLE** | Fail-closed exit `2`; simulated HTTP pipeline tested offline |

### 2.2 Recorded GitHub Actions & CodeQL Runs Across PR #39, PR #40 & PR #41
All three prerequisite PRs passed every CI matrix job (`backend (3.11)`, `backend (3.13)`, `postgres (17)`, `postgres (18)`, `web`, `containers` [Docker Compose + Playwright Scenario A Public Demo & Scenario B Authenticated Private Workspace], `CodeQL python`, `CodeQL javascript-typescript`):

| PR | Head Commit | Key CI & CodeQL Run URLs (All Passing) |
|---|---|---|
| **PR #39** (`feat/e32-live-gemini-accuracy-validation`) | `1f4a367` | CI Run `44293715896` ([`backend 3.11`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715896/job/134765195729), [`3.13`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715896/job/134765195612), [`pg 17`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715896/job/134765195633), [`pg 18`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715896/job/134765195706), [`web`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715896/job/134765195804), [`containers`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715896/job/134765195402)); CodeQL `44293715947` ([`js/ts`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715947/job/134765196016), [`py`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44293715947/job/134765195412)) |
| **PR #40** (`fix/p1b-taxonomy-v02-alignment`) | `fa3a7be` | CI Run `44281393852` ([`backend 3.11`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393852/job/134722692959), [`3.13`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393852/job/134722690343), [`pg 17`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393852/job/134722695605), [`pg 18`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393852/job/134722691271), [`web`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393852/job/134722692231), [`containers`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393852/job/134722692285)); CodeQL `44281393369` ([`js/ts`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393369/job/134722695152), [`py`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44281393369/job/134722691963)) |
| **PR #41** (`fix/e33-evidence-preserving-matching`) | `e74aeaf` | CI Run `44650861009` ([`backend 3.11`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861009/job/136005090803), [`3.13`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861009/job/136005090675), [`pg 17`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861009/job/136005090732), [`pg 18`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861009/job/136005090853), [`web`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861009/job/136005090794), [`containers`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861009/job/136005090522)); CodeQL `44650861021` ([`js/ts`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861021/job/136005090523), [`py`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/44650861021/job/136005090264)) |
| **E3.4 PR** (`fix/e34-integration-evaluation-assurance`) | Final integrated branch | GitHub Actions CI (`3.11`/`3.13`, `pg 17/18`, `web`, `containers` Playwright A & B) and `CodeQL` triggered upon PR creation and recorded on the PR before maintainer merge |

---

## 3. Phase 8 — Independent Release Decisions

Technical test passage is **strictly separated** from live AI validation, legal compliance sign-off, and external customer release readiness:

### A. Deterministic Crosswalk Engine
- **Decision: `CONDITIONAL GO`** *(Controlled internal assurance / pilot use with mandatory human review)*
- **Rationale:**
  - All `E1`/`E1.1`/`E3`/`E3.1`/`E3.2` regressions introduced in E3.3 were diagnosed and resolved (`e11=31/36`, `e31=15/24`, `e32=17/18`).
  - Evidence preservation (`ReconciliationDecision`), `PROPOSED`/`NEEDS_REVIEW` gating, `0` false coverage confirmations (`False Cov = 0`), tenant isolation, RBAC, and baseline SHA-256 integrity are verified across `292` backend + `79` frontend tests.
- **Conditions / Limits:**
  1. Un-tuned independent accuracy (`56.67%`, `17/30`; facet micro F1 `56.07%`) confirms that indicative present-tense policies (`mandatory=False`), sub-clause optionality (`"remains optional"` causing `1/30` false equivalence), and `"must not be destroyed"` deletion prohibitions require human review of all outputs.
  2. Outputs remain advisory (`review_status=proposed`/`needs_review`) until a qualified human reviewer approves mappings and reconciliations.

### B. Hybrid Semantic Matching
- **Decision: `NO-GO`** *(for production / autonomous customer workflows)* \| **`CONDITIONAL GO` strictly for offline/synthetic operator live-Gemini benchmarking**
- **Rationale:**
  - **`LIVE GEMINI: NOT RUN — CREDENTIALS UNAVAILABLE`** — real `gemini-embedding-001` and `gemini-2.5-flash` / `gemini-3.5-flash-lite` accuracy, token latency, 429 behavior, and citation-grounding failure rates have **not** been measured.
  - Mock-model scores (`60.00%`, `18/30` on frozen `e34` with `2/30` false equivalence) **cannot** establish real Gemini performance.
  - Default `gemini-2.5-flash` reaches its deprecation/migration cutoff on `2026-12-01`.
- **Gate to Unlock:** Operator must supply credentials and execute live Gemini evaluation against synthetic `e34` and `e32` datasets (`--model gemini-3.5-flash-lite`), demonstrating net accuracy/F1 lift over `deterministic_only` without increasing false equivalence or false-positive coverage proposals.

### C. Customer-Facing Release
- **Decision: `NO-GO`**
- **Unmet Blocking Requirements:**
  1. **Zero Legal / Regulatory Sign-Off:** Regulatory Pack `v0.2.0` still carries **`human_approved = 0`** across all `17` sources, `46` obligations, and `55` active mappings (per `audit_regulatory_library.py`: `pending_expert_human_review`; `10` obligations flagged `requires_legal_interpretation`, `4` `incomplete`, `3` `needs_correction`, `4` `source_unavailable`). Technical tests cannot substitute for legal counsel review.
  2. **Unvalidated Live Semantic AI & Confidentiality Policy:** Public Hybrid Matching and confidential customer AI processing must remain **disabled** (`SEMANTIC_MATCHING_ENABLED=false`) until live Gemini accuracy is proven on synthetic benchmarks, `GEMINI_BILLING_TIER=paid` (or private customer VPC endpoint) is verified, and data-processing governance is signed off.
  3. **Production Extraction Coverage Gaps:** `35/158` canonical facets remain unvalidated (`33` with `0` positive test cases, `1` `approval_logs_retained` unimplemented in enterprise policy extraction, `1` regression-only edge), and independent sentence-level extraction accuracy is `56.67%–60.00%`.
  4. **Final Sequential PR Merge & Post-Merge CI Verification:** PRs must integrate cleanly via `PR #39` $\rightarrow$ `PR #40` $\rightarrow$ `PR #41` $\rightarrow$ `E3.4 PR`, with final `main` CI + Playwright + CodeQL green before any external deployment consideration.
