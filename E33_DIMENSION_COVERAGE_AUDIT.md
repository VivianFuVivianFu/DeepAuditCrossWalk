# E3.3 Deterministic Comparison Dimension Coverage Audit

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Stage:** Stage B — E3.3 Production Extraction & Matching Accuracy (B6)  
**Branch:** `fix/e33-evidence-preserving-matching`  

---

## 1. Audit of the 13 Deterministic Comparison Dimensions

Every candidate pair `(EnterpriseClause, AtomicObligation)` evaluated by `validate_candidate_relationship()` ([`backend/banking_crosswalk/reconciliation.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py)) and `validate_hybrid_candidate_relationship()` ([`backend/banking_crosswalk/semantic_reconciliation.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/semantic_reconciliation.py)) is checked across 13 explicit governance dimensions stored in `ReconciliationDimensionComparison`:

| # | Dimension | Field(s) in `ReconciliationDimensionComparison` | Extraction & Comparison Mechanism | Veto / Downgrade Power over `EQUIVALENT` | E3.3 Hardening Status |
|---:|---|---|---|---|---|
| 1 | **Scope** | `scope_match`, `enterprise_scope`, `external_scope` | `_detect_operational_scopes()` (8 domain regexes: refunds, credit, IDR, cross-border, collection, PIA, security incident, third-party MSP). | `scope_match == "mismatch"` vetoes `EQUIVALENT` $\rightarrow$ `PARTIALLY_OVERLAPPING` or `UNMAPPED`. | Verified: prevents refund rules from claiming NCCP credit or APP 3/8 equivalence. |
| 2 | **Applicability** | `select_applicable_obligations()` / `decide_applicability()` | Pre-filters obligations by jurisdiction, entity type, AI role, and effective date before Stage A/B. | Non-applicable obligations (e.g. EU AI Act for domestic-only AU use cases) are excluded unless `include_non_applicable=True`. | Verified: preserves E4.1 temporal and territorial applicability rules. |
| 3 | **Subject / Control Objective** | `subject_match` | `"aligned"` when `shared_facets` is non-empty, `"partial"` otherwise; `"enterprise_only"` when `obligation=None`. | Without shared facets (`subject_match != "aligned"`), `EQUIVALENT` is impossible (Rule 9). | Overlap note: `subject_match` is derived from `shared_facets`; kept lightweight without adding redundant subject classifiers. |
| 4 | **Actor** | `actor_comparison`, `enterprise_actor`, `external_actor` | `_normalize_actor()` & `ACTOR_RANK` hierarchy (`team_leader=1` $\dots$ `board_or_committee=6`, `dual_approval=7`). | Lower-ranked enterprise actor (`ext_rank > ent_rank`) downgrades to `WEAKER_OR_POTENTIALLY_INSUFFICIENT`; different actor downgrades to `PARTIALLY_OVERLAPPING` (`NEEDS_REVIEW`). | Verified: dual sign-off (`actor_comp == "stricter_actor"`) is recognized as `STRICTER_ENTERPRISE_REQUIREMENT`. |
| 5 | **Action Polarity** | `action_polarity` | `_detect_action_polarity()` distinguishing `positive_requirement`, `prohibition` (protective), `absence_of_control` (including permissive omission), and `permissive`. | `absence_of_control` forces `POTENTIAL_CONFLICT` (`NEEDS_REVIEW`). Protective `prohibition` with full facets and approved control link can establish `STRICTER_ENTERPRISE_REQUIREMENT`. | **Hardened in E3.3:** Added `PERMISSIVE_CONTROL_OMISSION_PATTERN` and `PROTECTIVE_STAFF_PROHIBITION_CUES`. |
| 6 | **Modality** | `modality_comparison` | Compares `clause.mandatory` and `CUSTOMER_RIGHT_GRANT_PATTERN` against external binding/guidance/voluntary authority. | `enterprise_discretionary_vs_mandatory` downgrades to `WEAKER_OR_POTENTIALLY_INSUFFICIENT` (`NEEDS_REVIEW`). | Verified: customer right grants (*"customers have the right to..."*) are recognized as `customer_right_grant_aligned`. |
| 7 | **Threshold & Operator** | `threshold_comparison`, `enterprise_threshold`, `enterprise_operator`, `external_threshold`, `external_operator` | `_extract_currency_and_amounts()` & `_detect_threshold_operator()` (`>`, `>=`, `<`, `<=`). | `weaker_enterprise` or `>` vs `>=` boundary gap downgrades to `WEAKER_OR_POTENTIALLY_INSUFFICIENT`; lower approval trigger (`< ext_threshold`) classifies as `STRICTER_ENTERPRISE_REQUIREMENT`. | Verified across 12 numeric boundary scenarios in `test_false_coverage_remediation.py`. |
| 8 | **Currency** | `enterprise_currency`, `external_currency` | `CURRENCY_AMOUNT_PATTERN` (`AUD`, `USD`, `EUR`, `GBP`, `NZD`, `A$`, `US$`). | `currency_mismatch` (e.g. `USD 5,000` vs `AUD`) forces `UNDETERMINED` (`NEEDS_REVIEW`). | Verified on `E32-HO-09` (`USD 5,000`) and `E11` currency mismatch fixtures. |
| 9 | **Timing & Deadlines** | `timing_comparison`, `enterprise_timing`, `external_timing` + SLA hours | `_detect_approval_timing()` (`pre_execution` vs `post_execution`) + `_compare_obligation_bound_timeframes()`. | `weaker_post_execution` downgrades to `WEAKER_OR_POTENTIALLY_INSUFFICIENT`; `timeframe_conflict` (`ent_hours > ext_hours`) escalates to `POTENTIAL_CONFLICT`. | **Hardened in E3.3:** Sub-clause-bound timeframe extraction prevents cross-obligation false conflicts on compound sentences (`E32-HO-15`). |
| 10 | **Conditions** | `condition_status` | `_detect_conditions()` (`in the event of`, `provided that`, `where`). | `clause.is_conditional` caps relationship at `PARTIALLY_OVERLAPPING` (`NEEDS_REVIEW`). | Verified: records conditional qualification in `missing_conditions_or_evidence`. |
| 11 | **Exceptions** | `exception_status` | `_detect_exceptions()` (`unless`, `except where`, `exempt for`, `exempt from`). | `enterprise_exception_weakens` downgrades to `WEAKER_OR_POTENTIALLY_INSUFFICIENT` (`NEEDS_REVIEW`). | Verified: records exception description in `missing_conditions_or_evidence`. |
| 12 | **Legal Authority** | `authority_comparison` | Compares external `LegalAuthorityClassification` (`binding`, `enforceable_guidance`, `guidance`, `voluntary`) against `clause.authority_level`. | Preserves strict separation of binding statutes, regulatory guidance, voluntary frameworks, and internal controls. | Verified: voluntary standards never masquerade as statutory compliance. |
| 13 | **Facet Completeness** | `shared_control_ids`, `shared_facets`, `enterprise_only_facets`, `external_unaddressed_facets` | Compares `candidate_facets` (explicit + approved/proposed mapping facets + `_infer_canonical_obligation_facets_for_clause`) against `obligation.coverage_facets`. | Any non-empty `external_unaddressed_facets` or unapproved control link blocks `EQUIVALENT` $\rightarrow$ `PARTIALLY_OVERLAPPING`. | **Hardened in E3.3:** Local-window normalized stem matching improves paraphrase recall without causing false equivalence (`0` false equivalence across 138 benchmark clauses). |

---

## 2. Specific Five-Question Assurance Verification (B6)

1. **Does the system mistakenly reject valid protective controls?**
   - *Before E3.3:* Yes — `STAFF_PROHIBITION_PATTERN` in `policy.py` stripped `control_facets=[]` on protective staff prohibitions, and `EngineA1` suppressed all `PROHIBITION_ABSOLUTE_PATTERN` clauses.
   - *After E3.3:* Fixed — `PROTECTIVE_STAFF_PROHIBITION_CUES` in `policy.py` and `PROTECTIVE_PROHIBITION_PATTERN` in `engine_a1.py` preserve protective prohibitions (encryption, pre-execution approval blocks, statutory consent, data retention limits) as valid candidate controls.
2. **Does the system attribute one obligation's timing to another?**
   - *Before E3.3:* Yes — `_extract_timeframe_hours(clause.text)` applied a single numeric deadline across all obligations matched by a compound sentence (`E32-HO-15`).
   - *After E3.3:* Fixed — `_compare_obligation_bound_timeframes()` isolates compound sub-clauses (`;`, `while`, `whereas`) and binds timeframes only to the sub-clause matching the target obligation's domain.
3. **Does the system convert missing evidence into definite non-coverage?**
   - *Verified:* No — missing facets, conditional scope, or unresolved internal annexures (`Annexure G`) produce `PARTIALLY_OVERLAPPING` or `UNDETERMINED` with `ReconciliationDecisionStatus.NEEDS_REVIEW` / `PROPOSED` and `candidate_relevance_state in {"requirement_partially_addressed", "evidence_insufficient"}`, keeping the requirement open for human review rather than silently deleting it or marking it non-applicable.
4. **Does the system accept unsupported equivalence?**
   - *Verified:* No — `False Equivalence = 0` across all `138` historical/holdout benchmark clauses (`e11=0/36`, `e3=0/60`, `e31=0/24`, `e32=0/18`) and `0/8` on the new `E33_BLINDED_EVALUATION_SUITE`.
5. **Does the system lose valid semantic retrieval candidates before human review?**
   - *Before E3.3:* When Stage C downgraded or dismissed a Stage A/B candidate, or when `_is_ambiguous_clause()` short-circuited a clause, candidate details were not structured in a dedicated audit list.
   - *After E3.3:* Fixed — `ReconciliationDecision.preserved_candidate_evidence`, `ai_proposed_relationship`, `deterministic_veto_applied`, `deterministic_veto_reasons`, and `missing_conditions_or_evidence` preserve every candidate and veto rationale for human reviewers.
