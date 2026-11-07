# P1-S0 Coverage Status Contract

## Executive Summary

This document defines the multi-dimensional coverage model and status contract implemented in **DeepAudit Crosswalk** under **Prompt Revised P1-S0: Coverage Confirmation Safety & Mapping Approval Integrity**.

To prevent false assurance conclusions, the coverage engine strictly separates **requirement applicability**, **clause approval**, **control mapping approval**, **questionnaire-to-facet mapping approval**, **confirmed content coverage**, **implementation evidence**, and **operational control effectiveness**.

---

## 1. Seven Orthogonal Assurance Dimensions

In [`EnterpriseClauseCoverage`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L629-L654) and [`ObligationCoverage`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L485-L505), the platform preserves separate fields for each assurance dimension rather than collapsing them into a single boolean:

| Dimension | Model Field (`EnterpriseClauseCoverage` / `ObligationCoverage`) | Purpose |
|:---|:---|:---|
| **1. Requirement Applicability** | `applicability_status: ApplicabilityStatus` (`applicable`, `not_applicable`, `conditional`, `undetermined`) | Determines whether the regulatory obligation or enterprise clause applies to the use case scope. |
| **2. Clause Approval** | `clause_approval_status: ClauseReviewStatus` (`unreviewed`, `proposed`, `approved`, `confirmed`, `rejected`) | Tracks human governance approval of the extracted enterprise requirement text. |
| **3. Control Mapping Approval** | `control_mapping_approval_status: ClauseReviewStatus` | Tracks independent human review of the Clause-to-Unified-Control relationship. |
| **4. Questionnaire-to-Facet Approval** | `questionnaire_to_facet_approval_status: ReviewStatus` (`unreviewed`, `proposed`, `approved`, `rejected`) | Tracks whether candidate questionnaire items have been verified as covering required facets. |
| **5. Confirmed Content Coverage** | `coverage_status: CoverageStatus` | Classifies substantive questionnaire coverage of the requirement's facets and constraints. |
| **6. Implementation Evidence** | `implementation_evidence_status: Literal["not_assessed", "unverified", "implemented", "unimplemented"]` | Tracks whether technical implementation evidence exists (questionnaire coverage never implies implementation). |
| **7. Operational Effectiveness** | `operational_effectiveness_status: Literal["not_assessed", "unverified"]` | Explicitly records that questionnaire/document review does not establish runtime control effectiveness. |

---

## 2. Canonical `CoverageStatus` States & Decision Rules

[`CoverageStatus`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L83-L91) defines eight distinct states:

| `CoverageStatus` Enum Value | Semantic Definition | Deterministic Assignment Rule |
|:---|:---|:---|
| `covered` (**Confirmed Covered**) | All relevant required facets and numeric/timing/role constraints have sufficient confirmed coverage evidence under the assessment's approved validation policy. | Assigned only when: (1) required facets are resolved (`resolved_facets` non-empty), (2) every required facet and constraint (`thresholds_aud`, `threshold_operator`, `threshold_currency`, `required_approval_role`, `approval_timing`) is deterministically satisfied by non-negated questionnaire items, AND (3) both the clause and its control mapping are `approved`/`confirmed`. |
| `partial` (**Confirmed Partial**) | Some—but not all—required facets have confirmed coverage evidence, and remaining facets have no ambiguous candidate matches requiring review. | Assigned when `covered_facets` is non-empty, `missing_facets` is non-empty, and `needs_review_facets` is empty. |
| `missing` (**Confirmed Missing**) | The requirement is applicable, required facets are known, and the questionnaire has been examined and contains no non-negated candidate questions addressing the requirement. | Assigned when `covered_facets` is empty, `needs_review_facets` is empty, and `candidate_question_ids` is empty (including when the only matching text is an explicit negation such as *"human approval is not required"*). |
| `needs_review` (**Needs Review**) | Candidate evidence exists in the questionnaire, but its semantic or constraint sufficiency has not been established (or mapping approval is still pending). | Assigned when: (a) a question touches related concepts (e.g., `"human oversight"` instead of `"human approval"`, `"application logging"` instead of `"prompt logging"`, missing threshold/role/operator, or post-execution wording), OR (b) facets are satisfied by questions while clause or control mapping review is still `proposed`. |
| `mapping_incomplete` (**Mapping Incomplete**) | The required facet or control relationship cannot yet be reliably resolved. | Assigned when: (a) an enterprise clause is unmapped (`is_unmapped=True` or `control_mappings=[]`), OR (b) a clause has control mappings but neither `clause.control_facets` nor approved `mapped_facets` specify which facets apply. |
| `applicability_undetermined` (**Applicability Undetermined**) | Insufficient facts exist to establish whether the requirement applies. | Preserved for obligations/requirements whose applicability predicates cannot be resolved from provided context. |
| `not_applicable` (**Not Applicable**) | A justified and traceable applicability decision (or policy exemption / non-mandatory clause) establishes exclusion. | Assigned when an obligation is excluded by `decide_applicability()` or when an enterprise clause is non-mandatory / an explicit exemption (`clause.mandatory == False`). |
| `not_assessed` (**Not Assessed**) | The requirement has not been evaluated within the current assessment scope. | Default state for out-of-scope or unassessed items. |

---

## 3. Deterministic Constraint Validation Rules (`coverage.py`)

Keyword retrieval alone cannot establish `CoverageStatus.COVERED`. In [`_question_satisfies_enterprise_facet()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py#L1140-L1315), each enterprise facet undergoes deterministic constraint verification:

1. **Negation & Prohibition Gate (`_is_question_negated_for_facet`)**:
   - Questions matching `ABSENCE_OF_CONTROL_PATTERN` (e.g., *"does not require"*, *"is not required"*) or `NEGATION_OR_EXEMPTION_PATTERN` without a mandatory pre-execution prohibition block (`PROHIBITION_BLOCK_PATTERN`) are immediately disqualified from both confirmed coverage and candidate status.
2. **Human Approval (`human_approval_required`)**:
   - Requires explicit approval/authorisation language (`"human approval"`, `"manual approval"`, `"approved by a human"`, `"human sign-off"`, `"dual sign-off"`, `"manager approval"`, `"authorised officer approval"`, etc.).
   - Generic phrases (`"human oversight"`, `"human review"`, `"manual review"`, `"monitoring"`) do **not** satisfy `human_approval_required`; they are classified as weak candidates (`CoverageStatus.NEEDS_REVIEW`).
3. **Approval Authority Role (`clause.required_approval_role`)**:
   - When a clause specifies a required approval role (e.g., `Senior Manager`, `Authorised Officer`, `Two-Up / Dual Sign-off`), a non-negated question must explicitly test that role (`_question_satisfies_approval_role`). Specifying a lower role (e.g., `Customer Service Agent`) or omitting the role prevents confirmed coverage and records `"approval_authority_role"` in `missing_facets`.
4. **Monetary Thresholds & Operators (`approval_threshold_defined`)**:
   - When `clause.thresholds_aud` is present, the question must specify a matching currency (`AUD`, `USD`, etc.), a numeric threshold `<=` the required policy threshold, and a compatible boundary operator (`>=` vs `>`). Asking about `"defined high-value transactions"` without the numeric amount or checking `> AUD 500` when the policy requires `>= AUD 500` fails deterministic validation.
5. **Pre-Execution Blocking (`pre_execution_block`)**:
   - Disqualifies questions describing post-execution review (`"post-execution"`, `"after execution"`, `"after payment"`, `"retrospective"`).
   - Requires explicit pre-execution gating phrases (`"before execution"`, `"prior to execution"`, `"before payment"`, `"prior to payment"`, `"must not execute"`, `"cannot proceed"`, `"blocked prior to"`, `"pre-execution block"`).

---

## 4. Backward Compatibility & Schema Documentation

All existing fields on `CoverageAssessment`, `CoverageMetrics`, `ObligationCoverage`, and `GapRecord` are preserved:
- `CoverageAssessment.enterprise_clause_coverage: List[EnterpriseClauseCoverage]` is added with `Field(default_factory=list)` (empty `[]` in `regulatory_only` mode).
- `GapRecord.coverage_status: Optional[CoverageStatus] = None` is added to link each enterprise questionnaire gap directly to its resolved `CoverageStatus` (`missing`, `needs_review`, `mapping_incomplete`, `partial`).
- `EnterpriseBaseline.approved_clause_ids: List[str]` is added with `Field(default_factory=list)` to track approved clauses independently of `confirmed_control_ids`.

