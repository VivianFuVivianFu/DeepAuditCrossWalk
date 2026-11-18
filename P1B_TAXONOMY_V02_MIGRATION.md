# P1B Taxonomy v0.2.0 Migration & Version-Aware Facet Decomposition Specification

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Stage:** Stage A — P1B Taxonomy Compatibility & Experimental Engine Repair  
**Branch:** `fix/p1b-taxonomy-v02-alignment`  
**Target Regulatory Pack:** v0.2.0 (`UNIFIED_CONTROL_LIBRARY.json`, 33 Unified Controls, 11 Domains, 158 Canonical Facets)  
**Historical Baseline Preserved:** Pre-E4.1 `v1.0.0` (33 Unified Controls, 11 Domains, 155 Canonical Facets)  

---

## 1. Executive Summary

Following PR #38 (E4.1 Regulatory Accuracy & Control Mapping Remediation), `UNIFIED_CONTROL_LIBRARY.json` expanded from **155** unique canonical facets to **158** unique canonical facets (`155 - 2 + 5 = 158`) across 33 Unified Controls and 11 governance domains.

To prevent silent taxonomy drift, false control equivalence, or brittle hardcoded count failures, Stage A implements:
1. **Dynamic Canonical Taxonomy Loading** in [`scripts/experiments/canonical_adapter.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/experiments/canonical_adapter.py), verifying unique control IDs, unique snake_case facet IDs, root-vs-backend library parity, and valid alias/catalogue/mapping references.
2. **Version-Aware, Evidence-Gated Facet Migration** (`CanonicalMappingAdapter.migrate_legacy_facet()`), ensuring that a retired coarse facet never automatically credits multiple decomposed v0.2.0 facets unless each replacement facet is independently supported by source text evidence.
3. **Preserved Historical Benchmarks & Versioned v0.2.0 Views**, keeping `P1_EVALUATION_DATASET_V2.json` (`SHA-256: 3ee3241ce557b423...`) immutable for historical `v1.0.0` reproducibility while generating [`P1_EVALUATION_DATASET_V2_PACK_V020.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/P1_EVALUATION_DATASET_V2_PACK_V020.json) (`SHA-256: 0f976d1a7a4d07d6...`) for Regulatory Pack v0.2.0 evaluation.

---

## 2. Exact Reconciliation of the `155 -> 158` Canonical Facet Transition

| Change Type | Facet Identifier | Parent Unified Control | Statutory / Framework Basis | E4.1 / v0.2.0 Rationale |
|---|---|---|---|---|
| **Retired (1)** | `security_controls_defined` | `CTRL-PRIV-SECURITY-RETENTION` | Privacy Act 1988 (Cth) Sch 1 APP 11.1 & APP 11.3 (*POLA Act 2024*, `C2024A00128`) | Overloaded coarse facet replaced by separate technical and organisational security measure facets per APP 11.3. |
| **Retired (2)** | `deployer_human_oversight_and_6month_log_retention` | `CTRL-EU-HIGH-RISK` | Regulation (EU) 2024/1689 (EU AI Act) Art. 26(2) & Art. 26(6) | Composite facet conflated two distinct legal obligations: human oversight assignment (Art. 26(2)) and 6-month automatic log retention (Art. 26(6)). |
| **Added (1)** | `technical_security_measures_implemented` | `CTRL-PRIV-SECURITY-RETENTION` | Privacy Act 1988 Sch 1 APP 11.1 & APP 11.3 (`AU-PRIV-APP11-SECURITY`) | Captures technical safeguards (encryption, key management, VPC/network isolation, cryptographic controls). |
| **Added (2)** | `organisational_security_measures_implemented` | `CTRL-PRIV-SECURITY-RETENTION` | Privacy Act 1988 Sch 1 APP 11.1 & APP 11.3 (`AU-PRIV-APP11-SECURITY`) | Captures organisational safeguards (staff privacy/security training, information handling procedures, access governance). |
| **Added (3)** | `deployer_human_oversight_assigned` | `CTRL-EU-HIGH-RISK` | EU AI Act Art. 26(2) (`EU-AIA-ART26-27-DEPLOYER-CREDIT`) | Captures assignment of natural persons with necessary competence, training, and authority to oversee high-risk AI. |
| **Added (4)** | `automatic_logs_retained_6months` | `CTRL-EU-HIGH-RISK` | EU AI Act Art. 26(6) (`EU-AIA-ART26-27-DEPLOYER-CREDIT`) | Captures retention of automatically generated system logs for at least 6 months under deployer control. |
| **Added (5)** | `synthetic_content_marking_and_disclosure_applied` | `CTRL-EU-HIGH-RISK` | EU AI Act Art. 50(2)–(4) (`EU-AIA-ART50-TRANSPARENCY`) | Separated synthetic content marking and deepfake disclosure from general Art. 50(1) human-interaction transparency. |

---

## 3. Version-Aware Facet Migration Architecture

`CanonicalMappingAdapter.migrate_legacy_facet()` returns an immutable `FacetMigrationRecord` containing:
- `original_facet: str`
- `source_taxonomy_version: str` (`"1.0.0-pre-e4.1"`)
- `target_taxonomy_version: str` (`"0.2.0"`)
- `migration_kind: str`
- `emitted_facets: list[str]` (only facets positively supported by `source_text`)
- `unresolved_candidate_facets: list[str]` (sibling facets from a decomposition not supported by `source_text`)
- `canonical_control_id: str | None`
- `source_text: str`
- `mapping_reason: str`
- `requires_human_review: bool`

### Five Migration Classifications

| Classification (`migration_kind`) | Definition | Emission Rule | Human Review Flag | Example |
|---|---|---|---|---|
| `exact_rename` | 1:1 semantic identity with an active canonical facet or verified 1:1 legacy rename. | Emits `[target_facet]`; `unresolved_candidate_facets = []`. | `False` | `bias_testing` $\rightarrow$ `["fairness_and_explainability_metrics_evaluated"]` |
| `one_to_many_decomposition` | Retired composite/coarse facet where `source_text` evidences one or more specific v0.2.0 replacement facets. | Emits **only** replacement facets matched by evidence in `source_text`; un-evidenced sibling facets placed in `unresolved_candidate_facets`. | `True` if any sibling remains unresolved | `security_controls_defined` on `P1-009` $\rightarrow$ emits `["technical_security_measures_implemented"]`, unresolved `["organisational_security_measures_implemented"]` |
| `ambiguous_legacy_mapping` | Legacy shorthand or generic retired-facet text that spans multiple candidate facets/controls without disambiguating evidence. | Emits `[]`; all candidate targets placed in `unresolved_candidate_facets`. | `True` | `"Maintain reasonable security controls to safeguard personal information"` |
| `missing_evidence` | Known retired/decomposed facet where `source_text` is empty or contains no evidence for any replacement facet. | Emits `[]`; all candidate replacements placed in `unresolved_candidate_facets`. | `True` | `migrate_legacy_facet("security_controls_defined", source_text="")` |
| `unsupported_legacy_facet` | Unknown or fictitious facet identifier absent from both active UCL and legacy migration tables. | Emits `[]`; `unresolved_candidate_facets = []`. | `True` | `migrate_legacy_facet("fictitious_nonexistent_facet")` |

---

## 4. Verification & Regression Safeguards

Verified in [`scripts/experiments/test_canonical_adapter.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/experiments/test_canonical_adapter.py) (13/13 passing) and [`backend/tests/test_regulatory_library.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_regulatory_library.py) (7/7 passing):
- Dynamic count derivation matches `UNIFIED_CONTROL_LIBRARY.json` (33 controls, 158 unique facets).
- Root and `backend/banking_crosswalk/data/` JSON copies of the Unified Control Library, Atomic Obligation Catalogue, and Obligation-Control Mappings are verified identical.
- Every alias in `VERIFIED_CONTROL_ALIASES`, `AMBIGUOUS_CONTROL_ALIASES`, `FACET_TRANSLATIONS`, `EXACT_FACET_RENAMES`, and `RETIRED_FACET_DECOMPOSITIONS` is validated at initialization against the loaded UCL.
