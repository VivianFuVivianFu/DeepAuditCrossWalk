# E4.1 Control Mapping Remediation

This report documents the mapping-level and engine-level safeguards applied in E4.1 across `OBLIGATION_CONTROL_MAPPINGS.json` (`1.0.0` -> `1.1.0`), `validation.py`, `reconciliation.py`, and `semantic_reconciliation.py`.

## 1. Duplicate Obligation-Control Pair Elimination

- **Removed Duplicate:** `MAP-CROSS-007` (`ISO23894-AI-RISK-PROCESS -> CTRL-RISK-FRAMEWORK`), which duplicated `MAP-PRIMARY-044` with inconsistent facet counts (`2/3` vs `3/3`).
- **Provenance Preserved:** `MAP-PRIMARY-044` now records `superseded_mapping_ids: ["MAP-CROSS-007"]` and explains the consolidation in `equivalence_rationale`; catalogue metadata records `"superseded_mapping_ids": ["MAP-CROSS-007"]`.
- **Hard Guard Added:** `validation._check_mapping_facet_and_relationship_consistency` now fails validation if any duplicate `(obligation_id, control_id)` pair exists. Current count: **0 duplicates**.

## 2. Preventing `non_equivalent` Coverage Leakage

Previously, `MAP-CROSS-003` (Privacy Act NDB vs APRA CPS 234 72h notification), `MAP-CROSS-004` (APP 8 vs APRA CPS 230 offshoring notification), and `MAP-CROSS-006` (EU AI Act Art 26/27 vs NCCP Act s 128/130) were typed `non_equivalent` yet still populated non-empty `mapped_facets`. Additionally, runtime retrieval/reconciliation indexed all mappings without excluding `NON_EQUIVALENT`.

- **Data Correction:** Emptied `mapped_facets` (`[]`) on `MAP-CROSS-003`, `MAP-CROSS-004`, and `MAP-CROSS-006`, moving all obligation facets to `unmapped_obligation_facets`.
- **Structural Guard (`validation.py`):** Validation now fails whenever any `NON_EQUIVALENT` or `NOT_EQUIVALENT` mapping populates non-empty `mapped_facets`. Current count: **0 violations**.
- **Runtime Engine Guard (`reconciliation.py` & `semantic_reconciliation.py`):**
  - `validate_candidate_relationship`, `rank_reconciliation_candidates_for_clause`, `generate_reconciliation_candidates`, and `generate_hybrid_reconciliation_candidates` now exclude `MappingRelationship.NON_EQUIVALENT` / `NOT_EQUIVALENT` from control-to-obligation lookup graphs and from clause control/facet coverage accumulation.
  - Verified by unit tests in `backend/tests/test_e41_regulatory_remediation.py`.

## 3. Reclassification of Over-Broad `full` Mappings

| Mapping ID | Obligation | Control | Old Rel | New Rel | Basis |
|---|---|---|---:|---:|---|
| `MAP-PRIMARY-023` | `AU-APRA-CPG235-GOV` | `CTRL-DATA-QUALITY-GOV` (`x3` shared) | `full` | `related` | APRA CPG 235 is non-binding supervisory practice guidance, not binding law. |
| `MAP-PRIMARY-027` | `AU-ASIC-RG104-COMPLIANCE-TECH` | `CTRL-AI-GOV-ACCOUNTABILITY` (`x5` shared) | `full` | `partial` | RG 104 is ASIC guidance spanning licensee-wide s 912A(1) compliance beyond AI governance. |
| `MAP-PRIMARY-028` | `AU-ASIC-RG104-REPRESENTATIVES` | `CTRL-HUMAN-OVERSIGHT` (`x3` shared) | `full` | `partial` | RG 104 representative supervision extends beyond AI human-oversight gates. |
| `MAP-PRIMARY-030` | `AU-ASIC-REP798-AI-GAP` | `CTRL-AI-GOV-ACCOUNTABILITY` (`x5` shared) | `full` | `related` | ASIC REP 798 is a non-binding thematic surveillance report. |
| `MAP-PRIMARY-031` | `AU-NCCP-S47-CONDUCT` | `CTRL-AI-GOV-ACCOUNTABILITY` (`x5` shared) | `full` | `partial` | NCCP Act s 47(1) general credit-licensee duties include IDR (RG 271) and broader statutory compliance. |

Note: `broad_or_guidance_full_mappings` diagnostics dropped from **9 -> 4** (`MAP-PRIMARY-006`, `019`, `020`, `024`), which were retained in `requires_legal_interpretation` / E4 audit status as originally triaged pending specialist legal review.

## 4. Composite Facet Decomposition (`EU-AIA-ART26-27-DEPLOYER-CREDIT` & `ART50`)

- Decomposed `deployer_human_oversight_and_6month_log_retention` into separate atomic facets:
  - `deployer_human_oversight_assigned` (mapped in `MAP-CROSS-005` -> `CTRL-HUMAN-OVERSIGHT`, `partial`)
  - `automatic_logs_retained_6months` (unmapped on `CTRL-HUMAN-OVERSIGHT`, preventing false 6-month log retention credit)
- Separated Article 50 interactive/synthetic-content transparency out of `EU-AIA-ART26-27-DEPLOYER-CREDIT` into `EU-AIA-ART50-TRANSPARENCY` with primary mapping `MAP-PRIMARY-046` (`partial`).
