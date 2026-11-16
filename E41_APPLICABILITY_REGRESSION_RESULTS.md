# E4.1 Applicability, Structural & Regression Validation Results

## 1. E4.1 Applicability Behaviour Verified (`backend/banking_crosswalk/applicability.py`)

Verified by `backend/tests/test_e41_regulatory_remediation.py`:

| Scenario | As-Of Date | EU Obligation | Expected & Observed Outcome |
|---|---|---|---|
| Purely domestic Australian AI (`eu_establishment_or_market=False`, `eu_output_used=False`) | `2026-10-15` | All 4 EU AI Act obligations | `NOT_APPLICABLE` ("No Article 2 EU establishment, market or output-use nexus is indicated.") |
| EU nexus present, confirmed `eu_operator_role="none"` | Any | All 4 EU AI Act obligations | `NOT_APPLICABLE` |
| EU nexus present (`deployer` / consumer credit) before Art 4/5 (`2025-02-02`) | `2024-12-01` | `EU-AIA-ART4-5-PROHIBITED-LITERACY` | `CONDITIONAL` citing phased `2025-02-02` commencement |
| EU nexus present before Art 50 (`2026-08-02`) | `2026-06-01` | `EU-AIA-ART50-TRANSPARENCY` | `CONDITIONAL` citing `2026-08-02` (unaffected by Reg 2026/1744) |
| EU nexus present in window between Art 50 (`2026-08-02`) and Annex III deferral (`2027-12-02`) | `2026-10-15` | `EU-AIA-ART50-TRANSPARENCY` vs `EU-AIA-ART2-HIGH-RISK` / `ART26-27` | Art 50 active-phase `CONDITIONAL` (`2 Aug 2026`); Annex III obligations report phased deferral to **`2027-12-02`** under Regulation (EU) 2026/1744 |
| Unknown entity & business context (`BankingUseCase()`) | Current | All 46 obligations | `UNDETERMINED` or `CONDITIONAL` — zero obligations silently default to `APPLICABLE` |

## 2. Structural Validation & Deliverable Audit (`scripts/audit_regulatory_library.py`)

Observed run on remediated branch:
- **Structural checks:** `12/12` passed (`overall_structural_audit_passed=true`)
- **Legal review status:** `pending_expert_human_review` (`human_approved=0`)
- **Synthetic scenarios:** `6/6` passed (`all_passed=true`)
- **Diagnostics:**
  - `duplicate_obligation_control_pairs`: `0` (was `1`)
  - `non_equivalent_with_mapped_facets`: `0` (was `3`)
  - `broad_or_guidance_full_mappings`: `4` (was `9`)
  - `proprietary_unavailable_sources`: `3` (`ISO-42001`, `ISO-23894`, `ISO-27001`)

## 3. E1.1, E3, E3.1 & Questionnaire Regression (`scripts/evaluate_e3_live_gemini.py --provider mock --benchmark all --split all`)

All safety invariants held after E4.1 pack `0.2.0` remediation (zero benchmark ground-truth labels were modified):

| Benchmark (`combined`, Mock Hybrid) | Recall@1 | Recall@5 | Rel Accuracy | Macro F1 | False Eq | False Cov | Unresolved Flagged | Citations Accurate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **`e11` (N=36)** | 27/30 (90.00%) | 30/30 (100.00%) | 34/36 (94.44%) | 97.05% | 0/36 | 0/36 | 17/17 | 36/36 |
| **`e3` (N=60)** | 34/48 (70.83%) | 46/48 (95.83%) | 43/60 (71.67%) | 81.40% | 0/60 | 0/60 | 20/20 | 60/60 |
| **`e31` (N=24, Multi-Ob 3/3/3)** | 13/18 (72.22%) | 17/18 (94.44%) | 16/24 (66.67%) | 64.24% | 0/24 | 0/24 | 15/15 | 24/24 |

- **Section 7 Questionnaire (`hybrid`):** Dev R@1 `7/9`, Dev R@3 `9/9`, Holdout R@1 `7/9`, Holdout R@3 `7/9`, **Confirmed Covered `0`** (all mappings remain unapproved).
- **Important E4.1 Diagnostic Note:** Removing the `security_controls_defined` facet from `AU-PRIV-APP11-SECURITY` in favour of split APP 11.3 facets (`technical_security_measures_implemented`, `organisational_security_measures_implemented`) required updating `DeterministicMockSemanticProvider` cues in `providers.py` so mock semantic reasoning continues recognising role-based encryption and retention-schedule destruction on multi-obligation clause `E31-DEV-08`.
