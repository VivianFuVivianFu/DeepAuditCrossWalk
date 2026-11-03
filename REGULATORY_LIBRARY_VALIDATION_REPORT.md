# Australian Banking AI Governance — Regulatory Library Validation Report (Phase 8)

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Validation Date:** 2026-11-02  
**Validation Module:** [`backend/banking_crosswalk/validation.py`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/validation.py)  
**Active Pack Version:** `AU-BANKING-REG-PACK-0.1` (`0.1.0`, `library_release: 2026.10-au-banking-v1`)

---

## 1. Critical Differentiation: Automated Technical Validation vs. Expert Legal Review

> **IMPORTANT GOVERNANCE NOTICE**  
> Automated validation in `DeepAuditCrossWalk` verifies **technical and structural invariants only**: schema integrity, source register completeness, citation formatting, facet-to-control mapping coverage, effective-date consistency, authority classification boundaries, and deterministic engine execution.  
>  
> **Automated technical validation does NOT constitute legal advice and does NOT approve candidate regulatory obligations.**  
> All **46 atomic obligations**, **33 unified controls**, and **57 obligation-to-control mappings** are published with `review_status = "proposed"` (`approved_obligations_count = 0`). Promotion from `proposed` to `approved` requires explicit sign-off by qualified Australian financial-services legal and compliance reviewers.

---

## 2. Library Summary Metrics

| Metric | Count | Status / Notes |
|---|---:|---|
| **Official Regulatory & Framework Sources** | **18** | Recorded in [`REGULATORY_SOURCE_REGISTER.csv`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/REGULATORY_SOURCE_REGISTER.csv) |
| **Provisions / Clauses Reviewed & Extracted** | **46** | Recorded in [`ATOMIC_OBLIGATION_CATALOGUE.json`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/ATOMIC_OBLIGATION_CATALOGUE.json) |
| **Proposed Candidate Obligations** | **46** | `review_status = "proposed"` (100%) |
| **Approved Obligations** | **0** | Zero auto-approved obligations (enforced by automated gate) |
| **Unified Controls (11 Domains)** | **33** | Recorded in [`UNIFIED_CONTROL_LIBRARY.json`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/UNIFIED_CONTROL_LIBRARY.json) |
| **Obligation-to-Control Crosswalk Mappings** | **57** | 46 primary + 11 cross-framework mappings in [`OBLIGATION_CONTROL_MAPPINGS.json`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/OBLIGATION_CONTROL_MAPPINGS.json) |
| — `full` mappings | **25** | Primary control directly operationalises all extracted facets |
| — `partial` mappings | **11** | Control covers a subset of facets or requires statutory/scope qualification |
| — `related` mappings | **18** | Non-binding guidance or voluntary standard alignment |
| — `non_equivalent` mappings | **3** | Explicit legal non-equivalence guardrails (e.g. `CPS 234` 72h APRA notice vs `Privacy Act Part IIIC` OAIC/individual NDB notice) |

---

## 3. Automated Technical Validation Results (`validate_regulatory_library()`)

| Check ID | Validation Rule | Result | Errors | Details |
|---|---|---|---:|---|
| `missing_source_references` | Every obligation and mapping `source_id` exists in `pack.sources` and `REGULATORY_SOURCE_REGISTER.csv` | **PASSED** | 0 | All 18 sources cross-referenced across JSON and CSV |
| `invalid_provision_references` | Every obligation has a valid statutory/standard clause token, `exact_clause_reference`, `source_citation`, and `https://` `source_url` | **PASSED** | 0 | 46/46 obligations verified |
| `duplicate_obligations` | No duplicate `obligation_id` or duplicate `(source_id, exact_clause_reference, title)` | **PASSED** | 0 | 46 unique obligation IDs and clause signatures |
| `unmapped_control_facets` | Every obligation maps to a valid `UnifiedControl`, all `coverage_facets` exist in `control_facets` and `facet_keywords`, and primary mappings cover 100% of facets | **PASSED** | 0 | 150+ granular control facets mapped across 33 controls |
| `conflicting_effective_dates` | Valid ISO dates, `effective_to >= effective_from`, and child obligation dates reconciled with parent source or registered phased commencements | **PASSED** | 0 | Phased dates verified for `APP 1.7–1.9` (`2026-12-10`) and `EU AI Act` (`2025-02-02` / `2026-08-02`) |
| `incorrect_legal_authority_classification` | `authority` matches `legal_authority_classification`; non-binding guidance (`CPG 235`, `OAIC APP Guidelines`, `REP 798`, `AI6`) and voluntary standards (`NIST`, `ISO`) are never classified as binding | **PASSED** | 0 | All 5 authority classifications strictly enforced |
| `unreviewed_mappings` | Candidate obligations and crosswalk mappings are not auto-approved (`approved == 0`, `requires_human_validation == True`) | **PASSED** | 0 | 46 proposed obligations and 57 proposed mappings flagged for human review |
| `unsupported_applicability_decisions` | Every `applicability_key` is registered in `RULES` and returns a valid 4-state decision in both `enterprise_baseline()` and use-case modes | **PASSED** | 0 | 19/19 deterministic applicability rules verified |
| `broken_existing_analysis_behaviour` | `evaluate_questionnaire_coverage()` and `assess_policy_gaps()` run deterministically without LLM APIs and populate `by_authority_layer` / `gaps_by_authority_layer` | **PASSED** | 0 | Backward-compatible with all existing tests and API contracts |

---

## 4. Synthetic Evaluation Suite Results (`run_synthetic_evaluation_suite()`)

| Scenario | Description | Result | Key Verified Outcome |
|---|---|---|---|
| `questionnaire_coverage_examples` | Evaluates a synthetic 3-question bank using `use_case=None` (`enterprise_baseline()`) | **PASSED** | Separates coverage across `binding_regulatory` (29 applicable), `regulatory_guidance` (10 applicable), `voluntary_frameworks` (7 applicable), and `enterprise_internal_controls` (1 covered). |
| `enterprise_policy_gap_examples` | Evaluates a partial privacy-only enterprise policy against the full Australian banking pack | **PASSED** | Detects missing policy clauses for `AU-APRA-CPS234-INCIDENT`, `AU-APRA-CPS230-SP`, `AU-ASIC-RG271-COMPLAINT`, and `AU-NCCP-S128-131-LENDING` across all 4 authority layers. |
| `correct_and_incorrect_control_mappings` | Audits `OBLIGATION_CONTROL_MAPPINGS.json` across `full`, `partial`, `related`, and `non_equivalent` relationships | **PASSED** | Verifies 3 critical `non_equivalent` guardrails: (`MAP-CROSS-003`: CPS 234 72h APRA security notice != Privacy Act Part IIIC NDB OAIC/individual notice; `MAP-CROSS-004`: CPS 230 prior APRA offshoring notice != APP 8 cross-border privacy; `MAP-CROSS-006`: EU AI Act Annex III credit AI != Australian NCCP Act ss 128–131 responsible lending). |
| `inapplicable_obligations` | Evaluates an internal-only, onshore, non-credit staff policy search assistant with no PII and no third-party vendor | **PASSED** | Correctly marks `EU-AIA-ART2-HIGH-RISK`, `AU-NCCP-S128-131-LENDING`, `AU-PRIV-APP8-CROSSBORDER`, `AU-APRA-CPS230-SP`, and `ENT-AI-DELEGATED-APPROVAL` as `not_applicable` while keeping `AU-APRA-CPS220-RMF` `applicable`. |
| `conditional_obligations` | Tests future-dated `AU-PRIV-APP1.7-AUTOMATED` before (`2026-10-27`) and after (`2026-12-15`) commencement, plus unknown third-party data residency | **PASSED** | `AU-PRIV-APP1.7-AUTOMATED` transitions deterministically from `conditional` (`2026-10-27`) to `applicable` (`2026-12-15`); `AU-PRIV-APP8-CROSSBORDER` evaluates to `conditional` when a third-party AI vendor is used with unconfirmed residency. |
| `conflicting_policy_and_system_thresholds` | Compares an enterprise policy requiring human approval above `AUD 500` against a workflow configured with `approval_threshold_aud = 2500.0` | **PASSED** | Raises a `critical` `control_conflict` (`missing_facets=["approval_threshold_aligned"]`) and a `questionnaire_gap` if the questionnaire does not test the exact `AUD 500` boundary. |

---

## 5. Unresolved Mapping Uncertainties & Copyright / Licensing Posture

1. **Proprietary ISO/IEC Standards (`ISO/IEC 42001:2023`, `ISO/IEC 23894:2023`, `ISO/IEC 27001:2022`):**
   - Full normative text is copyrighted by ISO/IEC and Standards Australia. No copyrighted standard text is committed to this repository.
   - Public records contain bibliographic identifiers, clause numbers, and independently authored control summaries (`legal_note` and `extraction_uncertainty` explicitly recorded).
   - Licensed organisations can inject their privately licensed clause text at runtime by setting `BANKING_CROSSWALK_PRIVATE_OVERLAY_PATH` to a local JSON overlay file outside version control.
2. **Legal Interpretation Uncertainties Flagged for Human Review:**
   - **Privacy Act APP 8 (`AU-PRIV-APP8-CROSSBORDER`):** Distinguishing cross-border "use" (where an Australian bank retains strict technical control over offshore cloud infrastructure) from "disclosure" under OAIC Chapter 8 v1.3 (March 2026) requires contract-specific legal review.
   - **Privacy Act APP 1.7–1.9 (`AU-PRIV-APP1.7-AUTOMATED`):** Commences **10 December 2026**; interpretation of what constitutes a thing "substantially and directly related to making" a significant decision follows OAIC Chapter 1 v2.0 (30 September 2026) guidance.
   - **APRA CPS 230 (`AU-APRA-CPS230-SP`):** Whether a foundation-model API provider constitutes a "material service provider" under CPS 230 para 49/50 depends on whether the AI service supports a critical operation or exposes the ADI to material operational risk.
   - **EU AI Act (`EU-AIA-*`):** Extraterritorial nexus under Article 2(1)(c) ("output produced by the AI system is used in the Union") and Annex III point 5(b) creditworthiness vs. financial-fraud detection carve-outs require legal sign-off per use case.

