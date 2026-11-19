# E3.3 Evidence Preservation & Deterministic Veto Verification Report

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Stage:** Stage B (`fix/e33-evidence-preserving-matching`)  
**Regulatory Library Baseline:** Regulatory Pack `v0.2.0` (`17` sources, `46` atomic obligations, `33` unified controls, `158` canonical control facets, `55` active mappings, `0` human-approved mappings)

---

## 1. Objective & Design Principle

Prior to E3.3, when deterministic validation vetoed or downgraded an AI-proposed or semantically retrieved obligation-to-clause relationship (for example, downgrading `EQUIVALENT` or `PARTIALLY_ADDRESSED` to `INSUFFICIENT_EVIDENCE` or `UNRESOLVED`), the reconciliation result collapsed into an undifferentiated state that did not explicitly distinguish:
1. Whether a relevant regulatory candidate or internal clause was actually retrieved,
2. What relationship the semantic/LLM layer originally proposed (`ai_proposed_relationship`),
3. Why the deterministic guardrail vetoed or downgraded that proposal (`deterministic_veto_reasons`), and
4. What specific conditions, evidence artefacts, or facet dimensions were missing (`missing_conditions_or_evidence`).

In E3.3, **deterministic rules act as a formal guardrail and evidence verifier, not an evidence destructor**. When a candidate obligation is retrieved by deterministic or hybrid semantic matching, its trace, supporting passages, missing facet/evidence checklist, and explicit relevance state are preserved in `ReconciliationDecision` for human reviewer decision support.

---

## 2. Extended `ReconciliationDecision` Schema (`backend/banking_crosswalk/models.py`)

`ReconciliationDecision` has been extended with backward-compatible fields (all defaulted so existing API consumers and persistence layers remain unaffected):

| Field | Type | Default | Purpose |
|---|---|---|---|
| `relationship` | `ReconciliationRelationship` | *(required)* | Final validated relationship (`EQUIVALENT`, `PARTIALLY_ADDRESSED`, `MORE_STRINGENT`, `LESS_STRINGENT`, `CONFLICTING`, `NOT_ADDRESSED`, `INSUFFICIENT_EVIDENCE`, `UNRESOLVED`, `AMBIGUOUS`) |
| `review_status` | `ReviewStatus` | `ReviewStatus.PROPOSED` | Always `PROPOSED` for automated outputs; never auto-approved |
| `ai_proposed_relationship` | `Optional[ReconciliationRelationship]` | `None` | Relationship originally proposed by the semantic/hybrid reasoning layer before deterministic validation |
| `deterministic_veto_applied` | `bool` | `False` | `True` whenever deterministic validation modifies, caps, or vetoes the semantic/AI proposal |
| `deterministic_veto_reasons` | `list[str]` | `[]` | Auditable rule triggers explaining why the AI proposal was downgraded or vetoed |
| `missing_conditions_or_evidence` | `list[str]` | `[]` | Specific missing facets, scope gaps, timeframe mismatches, or operational evidence omissions |
| `candidate_relevance_state` | `str` | `"no_relevant_requirement_found"` | Explicit 8-state relevance classification distinguishing no match from relevant-but-incomplete or contradicted candidates |
| `preserved_candidate_evidence` | `list[str]` | `[]` | Verbatim supporting passages, matched obligation IDs, and clause excerpts preserved even when vetoed |

---

## 3. Explicit 8-State Candidate Relevance Taxonomy

Every `ReconciliationDecision` produced by `reconcile_obligation()` (`backend/banking_crosswalk/reconciliation.py`) and `validate_hybrid_candidate_relationship()` (`backend/banking_crosswalk/semantic_reconciliation.py`) populates `candidate_relevance_state` into one of eight mutually exclusive states:

| `candidate_relevance_state` | Meaning | Typical Trigger | Governance / Reviewer Action |
|---|---|---|---|
| `no_relevant_requirement_found` | No regulatory obligation or internal clause met the minimum lexical or semantic relevance threshold | Non-regulatory corporate admin/catering noise (`E32-HOLDOUT-13`) or unmapped policy domain (`NOT_ADDRESSED`) | Confirm out-of-scope or log true policy gap |
| `potentially_relevant_requirement_identified` | Candidate obligation or clause was retrieved and shares domain/control context, but relationship remains `UNRESOLVED` or `AMBIGUOUS` pending human review | Cross-framework annex ambiguity (`E32-HOLDOUT-01`), waived/aspirational controls (`E32-HOLDOUT-02`), or multi-obligation clause requiring decomposition | Reviewer inspects `preserved_candidate_evidence` and `deterministic_veto_reasons` to classify |
| `partially_addressed_requirement` | Internal clause addresses a subset of the obligation's required dimensions (`PARTIALLY_ADDRESSED`, `MORE_STRINGENT`, or `LESS_STRINGENT`) | Missing technical vs organisational security dimension (`OBL-OAIC-APP11-01`), narrower scope (`E32-HOLDOUT-07`), or frequency gap (`E32-HOLDOUT-10`) | Reviewer inspects `missing_conditions_or_evidence` to remediate specific gap |
| `apparently_contradicted_requirement` | Internal clause contains an active normative contradiction against the obligation (`CONFLICTING`) | Indefinite retention vs deletion duty (`E32-HOLDOUT-11`), prohibited override (`E32-HOLDOUT-14`), or relaxed notification deadline (`E32-HOLDOUT-12`) | Escalate policy conflict; block coverage confirmation |
| `evidence_insufficient_for_equivalence` | Candidate is relevant (`INSUFFICIENT_EVIDENCE`), or an AI `EQUIVALENT` proposal was downgraded because mandatory evidence/condition checks were not satisfied | AI proposed `EQUIVALENT` without full facet coverage or operational evidence | Reviewer requests missing artefacts listed in `missing_conditions_or_evidence` |
| `equivalent_pending_human_review` | All deterministic equivalence preconditions and facet checks passed (`EQUIVALENT`, `review_status == ReviewStatus.PROPOSED`) | Complete, mandatory, unexcepted policy clause matching all obligation dimensions (`E32-HOLDOUT-03`, `E32-HOLDOUT-05`) | Human reviewer verifies citation and approves to confirm coverage |
| `human_approved_relationship` | A qualified human reviewer has explicitly approved the reconciliation decision (`review_status == ReviewStatus.APPROVED`) | Post-review state via human review workflow (never emitted automatically) | Eligible for confirmed coverage calculation |
| `irrelevant_candidate_dismissed` | A low-similarity semantic candidate was retrieved by top-$k$ vector search but dismissed by the relevance gate | Out-of-domain embedding neighbor rejected by `_NON_REGULATORY_CORPORATE_NOISE_PATTERN` or low lexical/control overlap | Suppressed from active proposals while retaining audit trace |

---

## 4. Verification in `validate_hybrid_candidate_relationship()`

In `backend/banking_crosswalk/semantic_reconciliation.py`, `validate_hybrid_candidate_relationship()` enforces six deterministic guardrails while preserving full candidate evidence:

1. **Citation & Grounding Gate:** Verifies that `reasoning.citations` and `supporting_passages` reference verbatim text from the source clause and obligation. If grounding fails, `deterministic_veto_applied = True`, `deterministic_veto_reasons` records `"missing_or_ungrounded_citation"`, and `preserved_candidate_evidence` retains the clause text and obligation reference.
2. **Equivalence Precondition Gate:** When the LLM/semantic layer proposes `EQUIVALENT` (`ai_proposed_relationship = ReconciliationRelationship.EQUIVALENT`), deterministic validation checks whether `deterministic_decision.relationship` is also `EQUIVALENT` or whether mandatory dimensions (modality, scope, numeric thresholds, facet completeness) are missing. If deterministic rules found `PARTIALLY_ADDRESSED`, `UNRESOLVED`, or `CONFLICTING`, the AI `EQUIVALENT` proposal is vetoed (`deterministic_veto_applied = True`), downgraded to the deterministic guardrail state, and both `deterministic_veto_reasons` and `missing_conditions_or_evidence` are populated.
3. **Weak Modality / Waiver / Permissive Omission Gate:** Clauses with aspirational (`should`, `endeavour to`), discretionary (`may at its discretion`), or permissive omission (`may deploy without...`) language cannot be elevated to `EQUIVALENT` or `PARTIALLY_ADDRESSED` by semantic similarity. They are deterministically routed to `UNRESOLVED` with `candidate_relevance_state = "potentially_relevant_requirement_identified"` and full supporting passages preserved.
4. **Normative Contradiction Priority Gate:** If deterministic conflict detection identifies a timeframe violation (`_compare_obligation_bound_timeframes`), retention vs deletion contradiction, or control prohibition, `CONFLICTING` takes precedence over any semantic `PARTIALLY_ADDRESSED` or `UNRESOLVED` proposal (`candidate_relevance_state = "apparently_contradicted_requirement"`).
5. **Corporate Noise Suppression Gate:** Clauses matching `_NON_REGULATORY_CORPORATE_NOISE_PATTERN` with zero regulatory anchor overlap are deterministically kept at `NOT_ADDRESSED` (`candidate_relevance_state = "no_relevant_requirement_found"`), preventing false-positive semantic proposals.
6. **Human Review Invariant:** All reconciled decisions retain `review_status = ReviewStatus.PROPOSED`. No semantic or deterministic path can emit `ReviewStatus.APPROVED`.

---

## 5. Automated Test Verification

Verified via `pytest backend/tests/test_e33_evidence_preserving_matching.py -q`:

- **`test_e33_clause_extraction_does_not_default_partial_matches_to_full`**: Verifies that partial keyword matches emit `MappingRelationship.PARTIAL`, ambiguous legacy umbrella controls (`CTRL-GOV-FRAMEWORK`, `CTRL-TECH-OBSERVABILITY`, `CTRL-OPS-OUTSOURCING`) emit `MappingRelationship.RELATED`, and `MappingRelationship.FULL` requires all control facets on a mandatory unexcepted clause.
- **`test_e33_evidence_preservation_when_deterministic_veto_downgrades_ai_proposal`**: Constructs an AI `EQUIVALENT` proposal on a clause with an exception/scope gap and verifies that `validate_hybrid_candidate_relationship()` sets:
  - `ai_proposed_relationship == ReconciliationRelationship.EQUIVALENT`
  - `relationship != ReconciliationRelationship.EQUIVALENT`
  - `deterministic_veto_applied is True`
  - `len(deterministic_veto_reasons) >= 1`
  - `len(missing_conditions_or_evidence) >= 1`
  - `len(preserved_candidate_evidence) >= 1`
  - `candidate_relevance_state in {"partially_addressed_requirement", "potentially_relevant_requirement_identified", "evidence_insufficient_for_equivalence"}`
  - `review_status == ReviewStatus.PROPOSED`
- **`test_e33_protective_prohibition_not_misclassified_as_control_waiver`**: Verifies that `"Staff must not deploy high-risk AI models without human oversight and kill-switch testing"` is recognized as a protective prohibition rather than a control waiver.
- **`test_e33_blinded_evaluation_suite_across_all_configs`**: Verifies `8/8 (100.00%)` relationship accuracy and `8/8` evidence-preservation state assignments across `disabled`, `embedding_only`, and `hybrid` modes.
