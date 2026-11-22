# E3.5 Baseline & Architecture Gap Audit

**Date:** 2026-11-20  
**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Working Branch:** `fix/e35-normative-evidence-assurance`  
**Verified Baseline Commit SHA:** `b269a691cdd0362d9c6adf205219424715c17d16`  
**Role:** Principal Software Engineer, AI Governance Architect, Independent AI Assurance Evaluator  

---

## 1. Executive Summary & Verification

This audit establishes the pre-implementation technical baseline and architecture gap analysis for **E3.5 — Normative Semantics, Evidence Sufficiency & Assurance Decision Integrity**.

- **Branch:** `fix/e35-normative-evidence-assurance`
- **Working Tree:** Clean (verified via `git status`, 0 uncommitted changes)
- **Baseline Commit:** `b269a691cdd0362d9c6adf205219424715c17d16` (sequential integration of PR #39, PR #40, PR #41, and PR #42 into `main`)
- **CI / Quality Gate Status on Baseline:** All 15 checks passing in GitHub Actions (Run `44733320007`) and CodeQL (Run `44733320030`). Local automated test suite: 292 passed, 19 skipped, 0 failed in backend; 25 passed in experiments; 79 passed in web (Vitest).
- **Core Principle:** Improve accuracy, defensibility, and traceability of crosswalk conclusions while minimising false equivalence and false coverage. Maintain deterministic-first architecture; do not auto-approve decisions or inflate matches.

---

## 2. Production Execution Path

The end-to-end production pipeline from document ingestion to crosswalk API output spans the following modules:

```
[Uploaded Enterprise Policy / Document]
                  │
                  ▼ (api.py: POST /v1/policies/upload, POST /v1/baselines)
[Text Extraction & Sanitisation]
                  │
                  ▼ (policy.py: extract_enterprise_policy)
[_split_clauses -> Regex Category Filtering -> Facet/Threshold Extraction -> EnterpriseClause creation]
                  │
                  ▼ (api.py: POST /v1/reconciliation/candidates)
[Candidate Retrieval (Stage A)]
  ├── Deterministic: reconciliation.py: rank_reconciliation_candidates_for_clause
  └── Optional Hybrid: semantic_reconciliation.py: retrieve_reconciliation_candidates_hybrid
                  │
                  ▼
[Relationship Validation (Stage B)]
  └── reconciliation.py: validate_candidate_relationship
      (11-step dimension comparison: scope, actor, polarity, modality, threshold, timing, conditions, facets)
                  │
                  ▼
[Stage C Deterministic Veto (Hybrid Mode Only)]
  └── semantic_reconciliation.py: validate_hybrid_candidate_relationship
      (Enforces hard vetoes on AI-proposed equivalence, checks contradictions, caps unverified claims)
                  │
                  ▼
[ReconciliationDecision Output]
  └── Emits structured decision with decision_status=PROPOSED|NEEDS_REVIEW,
      dimension_comparison, missing_conditions_or_evidence, candidate_relevance_state
```

### Detailed Execution Trace:

1. **Ingestion & Sanitisation (`backend/banking_crosswalk/api.py:1455-1540`):**
   - Endpoints receive multipart file uploads (`.pdf`, `.docx`, `.txt`, `.md`).
   - File bytes are hashed (SHA-256), checked against size limits (10 MB), and passed to `extract_enterprise_policy`.

2. **Policy Extraction (`backend/banking_crosswalk/policy.py:801-1055`):**
   - Checks prompt injection patterns (`INJECTION_PATTERNS`, inert handling).
   - Checks shared library duplication (`check_shared_library_duplicate`).
   - `_split_clauses` normalises bullets and splits sentences.
   - Evaluates deterministic clause categories:
     - Category A: Absence of required control (`ABSENCE_OF_CONTROL_PATTERN`) -> `mandatory=False, is_unmapped=True`.
     - Category B: Staff prohibitions (`STAFF_PROHIBITION_PATTERN`) -> distinguishes protective staff prohibitions (`PROTECTIVE_STAFF_PROHIBITION_CUES`) vs unhelpful prohibitions.
     - Category E: Policy exemptions (`EXEMPTION_PATTERN`) -> `mandatory=False, is_unmapped=True`.
     - Category F: Mere topic references (`MERE_TOPIC_REFERENCE_PATTERN`) -> `mandatory=False`.
   - Extracts generic facets via `ENTERPRISE_FACET_PATTERNS`, thresholds via `AUD_PATTERN`, approval timing via `_detect_approval_timing`, approval roles via `_detect_approval_role`, conditions via `_detect_conditions`, exceptions via `_detect_exceptions`, implementation status via `_detect_implementation_status`.
   - Instantiates `EnterpriseClause` with candidate `ClauseControlMapping` records (all defaulting to `review_status=PROPOSED`).

3. **Candidate Retrieval — Stage A (`backend/banking_crosswalk/reconciliation.py:1460-1650`):**
   - Filters applicable obligations against the use case (`select_applicable_obligations`).
   - Computes multi-signal score: control mapping link (0.36), direct facet overlap (0.38), lexical facet match via `_infer_canonical_obligation_facets_for_clause` (0.48), topic matches (0.34), explicit statutory citations (e.g. APP 1, APP 11, CPS 234, RG 271).
   - Ranks top-K candidates without requiring manual target obligation assignment.

4. **Relationship Validation — Stage B (`backend/banking_crosswalk/reconciliation.py:740-1350`):**
   - `validate_candidate_relationship` runs an 11-step deterministic dimension comparison:
     1. Review status & ambiguity check: unapproved or ambiguous clauses resolve to `UNDETERMINED` (`decision_status=NEEDS_REVIEW`).
     2. Scope comparison: aligned vs narrower vs mismatch (`refunds` vs `credit`).
     3. Conflict check: absence of control or statutory timeframe violations -> `POTENTIAL_CONFLICT`.
     4. Threshold operator boundary mismatch -> `WEAKER_OR_POTENTIALLY_INSUFFICIENT` or `STRICTER_ENTERPRISE_REQUIREMENT`.
     5. Weaker requirement: higher threshold, post-execution timing, weakening exceptions, discretionary modality -> `WEAKER_OR_POTENTIALLY_INSUFFICIENT`.
     6. Conditional enterprise requirement -> `PARTIALLY_OVERLAPPING`.
     7. Governance actor rank comparison -> `WEAKER_OR_POTENTIALLY_INSUFFICIENT` if lower actor rank.
     8. Stricter requirement: lower threshold, dual approval, shorter SLA, strict prohibition -> `STRICTER_ENTERPRISE_REQUIREMENT`.
     9. Unaddressed external facets -> `PARTIALLY_OVERLAPPING` (sharing a Control ID never establishes equivalence!).
     10. Proposed-only control link -> `PARTIALLY_OVERLAPPING` (`decision_status=NEEDS_REVIEW`).
     11. Full facet coverage, approved clause, approved mapping, aligned scope/timing/modality -> `EQUIVALENT` (`decision_status=PROPOSED`, never auto-approved).

5. **Deterministic Veto — Stage C (`backend/banking_crosswalk/semantic_reconciliation.py:378-550`):**
   - Enforces deterministic vetoes over optional LLM predictions.
   - Any LLM claim of `EQUIVALENT` without full deterministic facet alignment is vetoed to `PARTIALLY_OVERLAPPING` or rejected.
   - LLM-detected contradictions or weakening are escalated to `POTENTIAL_CONFLICT` or `WEAKER_OR_POTENTIALLY_INSUFFICIENT`.
   - `decision_status` is never automatically set to `APPROVED`.

---

## 3. Existing Models, Utilities, and Safeguards Available for Reuse

| Component | Location | Reusable Capabilities |
|---|---|---|
| `EnterpriseClause` | `models.py:650-699` | Stores text, `mandatory`, `control_facets`, `thresholds_aud`, `threshold_operator`, `threshold_currency`, `approval_timing`, `required_approval_role`, `is_conditional`, `has_exception_clause`, `implementation_status`. |
| `ReconciliationDimensionComparison` | `models.py:843-870` | 19 dimension fields capturing scope, subject, actor, polarity, modality, threshold, timing, condition, exception, authority, and facet sets. |
| `ReconciliationDecision` | `models.py:884-950` | Full provenance: `enterprise_clause_id`, `external_obligation_id`, `external_source_id`, `external_source_version`, `external_provision`, `external_legal_authority`, `regulatory_pack_id`, `regulatory_pack_version`, `decision_status`, `candidate_relevance_state`, `missing_conditions_or_evidence`. |
| `compute_clause_sha256` | `reconciliation.py:243-260` | Deterministic fingerprinting of clause text and approved mappings. |
| `_is_ambiguous_clause` | `reconciliation.py:482-508` | Detects vague internal dependencies, unquantified discretion, and unresolved attachments. |
| `_compare_obligation_bound_timeframes` | `reconciliation.py:380-425` | Extracts and compares statutory vs enterprise SLA hours. |
| Tenant Isolation & RLS | `sql_store.py:45-120` | Enforces PostgreSQL tenant isolation via `app.current_tenant_id` session setting on all queries. |
| Confidentiality Gate | `llm/security.py:30-85` | Blocks non-synthetic customer data from unapproved external LLM providers. |

---

## 4. Current Regulatory Library & Baseline Verification

- **Regulatory Pack:** `AU-BANKING-REG-PACK-0.1` Version `0.2.0`
  - `17` regulatory/framework sources
  - `46` atomic obligations
  - `33` unified controls across `11` domains
  - `158` canonical control facets (0 duplicate IDs, 0 facets shared across controls)
  - `55` active mappings (`22` full, `12` partial, `18` related, `3` non-equivalent)
  - Superseded mappings: `MAP-CROSS-007` retired and inactive.
- **Human Approval Status:**
  - `0` human-approved regulatory records (100% of obligations and mappings have `review_status="proposed"`).
  - All mappings require human validation (`requires_human_validation=True`).
- **File Parity:** Verified byte-for-byte identical between root and `backend/banking_crosswalk/data/`.

---

## 5. Frozen E3.4 Benchmark Reproduction

Before any matching or parsing modifications, the frozen E3.4 benchmark suite was executed on the baseline commit (`b269a69`):

Command:
```powershell
python scripts/evaluate_e3_live_gemini.py --provider mock --benchmark e34
```

### Reproducible E3.4 Baseline Results:

| Mode | Recall@1 | Recall@5 | Relationship Accuracy (N=30) | Macro F1 | False Equivalence | False Coverage | Unresolved Reference Recall | Citations |
|---|---|---|---|---|---|---|---|---|
| **Deterministic (`disabled`)** | 21/25 (84.00%) | 25/25 (100.00%) | **17/30 (56.67%)** | 59.01% | 1/30 | 0/30 | 16/22 | 30/30 |
| **Embedding-Only** | 22/25 (88.00%) | 25/25 (100.00%) | **17/30 (56.67%)** | 58.89% | 2/30 | 0/30 | 15/22 | 30/30 |
| **Hybrid (Mock)** | 22/25 (88.00%) | 25/25 (100.00%) | **18/30 (60.00%)** | 71.76% | 2/30 | 0/30 | 20/22 | 30/30 |

### Section 7 Questionnaire Matching:
- Dev R@1: 0/0, Holdout R@1: 8/8 (100%), Holdout R@3: 8/8 (100%).

*Note: All current evaluations use deterministic rules and deterministic mock models. Real Gemini has not been executed in customer production. Customer-facing Hybrid Matching remains NO-GO.*

---

## 6. Architecture Gap Analysis & Target Gaps for E3.5

### Gap 1: Stale Canonical Facet Bridges (`reconciliation.py:550-573`)
- **Finding:** `GENERIC_TO_CANONICAL_FACET_BRIDGES` maps 6 generic facets to 9 target facets. However, 6 of those 9 targets are pre-v0.2.0 retired strings:
  - `human_oversight_and_override_defined` (retired)
  - `human_oversight_for_high_risk` (retired)
  - `adverse_impact_intervention_mechanism` (retired)
  - `bias_and_fairness_testing` (retired)
  - `ai_inventory_and_classification` (retired)
  - `ai_use_case_register_maintained` (retired)
- **Impact:** Lexical facet bridge never triggers for these facets because the destination strings do not exist in the 158-facet canonical UCL.
- **Solution:** Re-anchor active bridge mappings to the verified canonical facets in UCL v0.2.0 (`fairness_and_explainability_metrics_evaluated`, `use_case_registered_in_enterprise_ai_inventory`, `ai_assets_classified_by_criticality_and_sensitivity`, etc.) following the audited decompositions in `canonical_adapter.py`.

### Gap 2: Missing `approval_logs_retained` in Enterprise Clause Extractor (`policy.py:925-930`)
- **Finding:** `approval_logs_retained` is defined in `GENERIC_FACET_PATTERNS` (line 219) and exists as a canonical facet on `CTRL-DELEGATED-AUTHORITY-THRESHOLD`, but is omitted from `ENTERPRISE_FACET_PATTERNS` (line 740).
- **Impact:** Clauses describing approval log retention cannot extract this canonical facet during production enterprise policy extraction.
- **Solution:** Wire `approval_logs_retained` into `ENTERPRISE_FACET_PATTERNS` with appropriate phrase cues (`"approval log"`, `"audit log"`, `"record approval"`, `"retain approval logs"`, `"traceability log"`).

### Gap 3: Declarative Enterprise Policy Assertions Treated as Discretionary (`policy.py:51-54, 958`)
- **Finding:** `MANDATORY_PATTERN` relies almost entirely on modal verbs (`must`, `shall`, `required`). Present-tense declarative assertions (e.g. *"The bank maintains documented information security controls"*) fail `MANDATORY_PATTERN` and are marked `mandatory=False`. In `reconciliation.py:923`, this results in `modality_comp="enterprise_discretionary_vs_mandatory"` and downgrades the relationship to `WEAKER_OR_POTENTIALLY_INSUFFICIENT`.
- **Impact:** Misinterprets declarative institutional commitments as discretionary guidelines, causing false weaker classifications.
- **Solution:** Introduce normative modality classification that recognises present-tense institutional commitments (`"maintains"`, `"enforces"`, `"implements"`, `"operates"`, `"retains"`, `"applies"`) when used as binding policy assertions, while distinguishing them from verified operational effectiveness evidence.

### Gap 4: Explicit Optionality and Discretion Not Isolated (`policy.py`, `reconciliation.py`)
- **Finding:** When a policy clause couples an affirmative process with explicit optionality (e.g. *"PIA recommendations are documented, but formal closure remains optional"*), the affirmative keywords match the facet, while the optionality is not recognized as weakening or negating the required control closure.
- **Impact:** False positive coverage / false equivalence for discretionary processes.
- **Solution:** Add explicit optionality detection (`OPTIONALITY_PATTERN`: `"optional"`, `"at discretion"`, `"may optionally"`, `"remains optional"`, `"not mandatory to close"`) and ensure it flags the modality as non-binding and prevents equivalence for mandatory obligations.

### Gap 5: Retention / Deletion Normative Conflict Unrecognized (`reconciliation.py:1123-1137`)
- **Finding:** A policy stating *"Personal information must be retained indefinitely and must not be destroyed"* expresses an affirmative retention requirement, but directly contradicts the statutory destruction/de-identification mandate under APP 11.2 / `AU-PRIV-APP11-SECURITY`.
- **Impact:** May be scored as partial overlap instead of `POTENTIAL_CONFLICT`.
- **Solution:** Detect indefinite retention clauses (`"retained indefinitely"`, `"never destroy"`, `"must not be destroyed"`, `"permanent retention"`) when evaluated against obligations mandating destruction or de-identification (`destruction_or_deidentification_verified`), classifying them as `POTENTIAL_CONFLICT`.

### Gap 6: Unresolved Reference Detection Gap (`reconciliation.py:99-103, 482-508`)
- **Finding:** `_INTERNAL_ATTACHMENT_DEPENDENCY_PATTERN` required lead-in prepositions like `"in accordance with"`, `"under"`, `"per"`. Phrasings like *"Controls must comply with Annexure D2"* or *"subject to Appendix 4"* were not captured, preventing the clause from resolving safely to `UNDETERMINED`.
- **Impact:** Unresolved dependencies fail to trigger the `UNDETERMINED` safety gate.
- **Solution:** Expand attachment dependency regex to include `"comply with"`, `"in compliance with"`, `"subject to"`, `"pursuant to"`.

---

## 7. Plan for Phases 1–5

1. **Phase 1:** Repair `GENERIC_TO_CANONICAL_FACET_BRIDGES`, wire `approval_logs_retained` into `ENTERPRISE_FACET_PATTERNS`, add CI taxonomy integrity test ensuring zero dead bridge targets.
2. **Phase 2:** Implement normative semantics hardening (declarative policy assertion recognition, optionality detection, indefinite retention conflict detection, expanded attachment dependency cues).
3. **Phase 3:** Reinforce evidence sufficiency and provenance separation in `ReconciliationDecision`.
4. **Phase 4:** Ensure assurance decision gates maintain strict separation between relationship classification and human approval status.
5. **Phase 5:** Build independent E3.5 evaluation holdout, execute full regression suite, and report findings.
