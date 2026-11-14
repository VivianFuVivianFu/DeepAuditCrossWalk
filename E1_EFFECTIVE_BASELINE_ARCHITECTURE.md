# E1 — Effective Assessment Baseline Architecture

## 1. Architectural Pipeline

```
Shared Regulatory Library (Immutable, Versioned)
        +
Confirmed Applicability Context (BankingUseCase)
        +
Optional Approved Enterprise Baseline (Tenant-Owned, SHA-256 Fingerprinted)
        +
Versioned Requirement Reconciliation Decisions (Stage A + Stage B + Human Review)
        ↓
Effective Assessment Baseline Composition Service (compose_effective_assessment_baseline)
        ↓
Deterministic EffectiveAssessmentBaseline (effective_baseline_sha256)
        ↓
Downstream Document Coverage Assessment (Questionnaire Coverage Engine)
```

---

## 2. Two-Stage Reconciliation Engine

### Stage A: Candidate Relationship Generation (`generate_reconciliation_candidates`)
1. **Input Filtering**:
   - Excludes `REJECTED` enterprise clauses and clauses from `superseded` or `retired` policies.
   - Excludes `PROPOSED` (unapproved) enterprise clauses from active baseline candidate generation unless explicitly requested for diagnostic inspection.
   - Filters external obligations to those applicable (or `human_confirmation_required`) for the supplied `BankingUseCase`.
2. **Candidate Linking Signals**:
   - **Signal 1 (Canonical Control Mapping)**: Links non-rejected `ClauseControlMapping` records (bridging policy extractor aliases and Unified Control Library IDs) to associated external obligations.
   - **Signal 2 (Coverage Facet Overlap)**: Links enterprise clauses sharing one or more `control_facets` with `AtomicObligation.coverage_facets`.
   - **Signal 3 (Instrument Citation & Negative-Obligation Topic Match)**: Matches explicit regulatory citations (`APP 8`, `CPS 234`, `RG 271`, `NCCP`) and exemption/absence-of-control clauses against target obligations so conflicts are never missed.
   - **Signal 4 (Internal Enterprise-to-Enterprise Conflict Detection)**: Compares pairs of approved enterprise clauses sharing controls or facets within the same baseline to detect conflicting monetary thresholds, operators, approval timings, or requirement polarities.
   - **Standalone Fallback**: Approved clauses with no external obligation match are passed to Stage B with `obligation=None` to classify as `additional_enterprise_requirement` or `unmapped_no_reliable_relationship`.

### Stage B: Multi-Dimension Relationship Validation (`validate_candidate_relationship`)
Stage B evaluates 12 distinct governance dimensions before assigning `validated_relationship`:
1. **Clause Review Status**: Unapproved clauses cannot be validated as `equivalent` (`undetermined`).
2. **Control Mapping Review Status**: A `proposed` control mapping caps the relationship at `partially_overlapping` (`decision_status = needs_review`) with an explicit uncertainty warning.
3. **Indeterminate Language Check**: Vague deferrals (`as determined from time to time`, `in accordance with Schedule X`) are classified as `undetermined`.
4. **Operational & Transaction Scope**: Disjoint scopes (e.g., `refunds` vs `credit_decisions`) are flagged as `scope_match = "mismatch"` and never equated.
5. **Action Polarity**: Distinguishes protective prohibitions (`must not` -> `prohibition`) from absence of control (`does not require` -> `absence_of_control` -> `potential_conflict`).
6. **Currency Compatibility**: Mismatched currencies (`USD` vs `AUD`) are classified as `undetermined` (`currency_mismatch`).
7. **Monetary Threshold & Operator Boundary**:
   - Identical threshold with different operator (`> 500` vs `>= 500`) is flagged as `operator_boundary_difference` (`weaker_or_potentially_insufficient` when missing boundary `500`, `stricter_enterprise_requirement` when adding boundary `500`).
   - Lower approval trigger (`AUD 500` vs `AUD 1,000`) -> `stricter_enterprise_requirement`.
   - Higher approval trigger (`AUD 5,000` vs `AUD 1,000`) -> `weaker_or_potentially_insufficient`.
8. **Timeframe Deadlines**: Shorter mandatory notification/response window (`24 hours` vs `72 hours`) -> `stricter_enterprise_requirement`; longer deadline exceeding statutory limit (`14 days` vs `72 hours`) -> `potential_conflict`.
9. **Approval Timing**: `post_execution` review against a `pre_execution` requirement -> `weaker_or_potentially_insufficient`.
10. **Approval Actor**: `dual_approval` (two-up sign-off) -> `stricter_enterprise_requirement`; lower/different actor (`Senior Manager` vs `Authorised Officer` / `Responsible Manager` / `Board`) -> `weaker_or_potentially_insufficient` or `partially_overlapping`.
11. **Conditions & Exceptions**: Exception carve-outs (`has_exception_clause=True`) -> `weaker_or_potentially_insufficient`; conditional triggers (`is_conditional=True`) -> `partially_overlapping`.
12. **Facet Completeness**: Shared `control_id` with unaddressed obligation facets -> `partially_overlapping` (never `equivalent`).

---

## 3. Effective Assessment Baseline Composition Rules

`compose_effective_assessment_baseline()` enforces the 11 non-negotiable composition invariants:

1. **Preserve Every Applicable External Obligation**: Every applicable `AtomicObligation` in the active `RegulatoryPack` is included as an `external_obligation` item in `requirements`.
2. **Preserve Additional Approved Enterprise Requirements**: Approved enterprise requirements with `additional_enterprise_requirement` or `partially_overlapping` relationships are included as `additional_enterprise_requirement` items.
3. **Retain Stricter Enterprise Conditions**: Approved `stricter_enterprise_requirement` decisions attach `stricter_conditions` to the external obligation and create a traceable `stricter_enterprise_condition` item and `stricter_overlay_group`.
4. **Preserve Unmapped Approved Enterprise Clauses**: Approved enterprise clauses with `unmapped_no_reliable_relationship` are retained as `unmapped_enterprise_requirement` items and never silently dropped.
5. **Retain Unresolved Conflicts & Uncertain Relationships**: Any `potential_conflict`, `weaker_or_potentially_insufficient`, `undetermined`, `stale`, or unapproved (`proposed`/`needs_review`) reconciliation decision is surfaced in `unresolved_items` (and `potential_conflicts`).
6. **Reviewed Equivalence Presentation Grouping Without Deletion**: Only when an authorised reviewer approves `decision_status = approved` with `approved_relationship = equivalent` does the composer create a `reviewed_equivalence_group` in `presentation_groups` that links the external obligation and enterprise clause while preserving both underlying `source_references`.
7. **Strict Authority Separation**:
   - Statutory and prudential obligations (`binding_legal_or_prudential_obligation`, `enforceable_regulatory_requirement`) have `is_legally_binding = True`.
   - Voluntary frameworks (`voluntary_framework`) and regulatory guidance (`regulatory_guidance_and_expectation`) always retain `is_legally_binding = False`.
   - Enterprise policies (`enterprise_policy`) always retain `is_legally_binding = False` and are never elevated to statutory law.
8. **Deterministic Cryptographic Reproducibility**: The entire composed baseline is canonically serialized and hashed into `effective_baseline_sha256` (`EBL-<16-HEX>`).
