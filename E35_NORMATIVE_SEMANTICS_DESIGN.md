# DeepAudit Crosswalk — E3.5 Normative Semantics & Assurance Design

**Document ID**: `DEEPAUDIT-E35-NORMATIVE-SEMANTICS-DESIGN-V1`  
**Version**: `1.0.0`  
**Baseline Git Commit**: `b269a691cdd0362d9c6adf205219424715c17d16`  
**Working Branch**: `fix/e35-normative-evidence-assurance`  
**Classification**: Public Engineering Assurance & Architectural Specification  

---

## 1. Executive Summary & Objective

In regulatory crosswalking, semantic similarity models frequently misinterpret normative modalities—conflating discretionary guidance with mandatory rules, declarative institutional commitments with voluntary aspirational goals, and conditional carve-outs with full compliance. 

The primary objective of **E3.5 Normative Semantics Hardening** is to guarantee that the reconciliation engine correctly interprets institutional commitments and regulatory obligations under Australian financial services law (APRA CPS 230, CPS 234, CPS 220; Privacy Act 1988 / APPs; ASIC RG 271, RG 104; NCCP Act), eliminating false equivalence while preventing unsupported conclusions.

### Core Architectural Axioms
1. **Semantic Discovery, Deterministic Assurance**: LLM reasoning and embedding retrieval discover candidate relationships and surface evidence; deterministic rules strictly enforce statutory boundaries, mandatory requirements, and threshold comparisons.
2. **Preservation of Human Agency**: An automated engine must **never** auto-approve regulatory mappings. The match classification (`validated_relationship`) and the human governance decision (`decision_status`) remain strictly decoupled. `decision_status` remains `PROPOSED` or `FLAGGED` pending human sign-off.
3. **Evidence-Preserving Precision**: Candidate evidence, rationale, and missing conditions are explicitly captured across all stages rather than silently dropped.

---

## 2. Normative Semantics Taxonomy & Problem Taxonomy

Prior to E3.5, the reconciliation engine exhibited systematic errors when encountering specific linguistic and structural phenomena common in institutional banking policies:

| Phenomenon | Regulatory Risk | E3.5 Solution |
|---|---|---|
| **Case A: Declarative Institutional Commitments** | Binding policy statements without modal verbs (e.g., *"The bank maintains documented controls..."*) were misclassified as discretionary or non-mandatory, failing equivalence checks. | Recognized via `DECLARATIVE_POLICY_ASSERTION_PATTERN`. Sets `normative_type="declarative_assertion"`, `is_declarative_assertion=True`, and records `modality_comparison="declarative_assertion_aligned"`. |
| **Case B: Explicit Optionality & Discretionary Carve-Outs** | Carve-outs (e.g., *"recommendations are tracked, but formal closure remains optional"*) were matched as equivalent or partial without noting that the enterprise rule is weaker than the statutory mandate. | Detected via `OPTIONALITY_PATTERN`. Classifies as `normative_type="optionality"`; forces `validated_relationship=WEAKER_OR_POTENTIALLY_INSUFFICIENT` against mandatory obligations. |
| **Case C: Conflict via Negative Wording** | Institutional retention directives (e.g., *"personal information must be retained indefinitely and must not be destroyed"*) superficially matched retention keywords but directly violated APP 11.2 destruction duties. | Enforced via `_INDEFINITE_RETENTION_CONFLICT_PATTERN`. Triggers deterministic `POTENTIAL_CONFLICT` with explicit reason recorded in `deterministic_veto_reasons`. |
| **Case D: Protective Prohibitions** | Pre-execution threshold blocks (e.g., *"AI agents must not execute payments above AUD 500 without prior human approval"*) were misread as negative omissions or absences of control. | Captured via `PROHIBITION_BLOCK_PATTERN`. Preserves positive mandate, assigns `pre_execution` timing, and validates as `STRICTER_ENTERPRISE_REQUIREMENT`. |
| **Case E: Permissive Execution Before Review** | Retrospective workflows (e.g., *"payments may be executed before manager review"*) were confused with valid pre-execution approval. | Detected via `PERMISSIVE_EXECUTION_BEFORE_REVIEW_PATTERN`. Prioritizes `approval_timing="post_execution"` and downgrades to `WEAKER_OR_POTENTIALLY_INSUFFICIENT`. |
| **Case F: Unresolved External/Internal Dependencies** | Clauses pointing to external or unparsed attachments (e.g., *"controls must comply with Annexure D2"*, *"subject to Schedule B"*) were prematurely matched without the referenced standard. | Handled via expanded `_INTERNAL_ATTACHMENT_DEPENDENCY_PATTERN`. Correctly halts automatic matching and marks relationship as `UNDETERMINED` with required attachment evidence logged. |

---

## 3. Detailed Component Architecture

### 3.1 Policy Extraction (`backend/banking_crosswalk/policy.py`)
`extract_enterprise_policy` now performs multi-stage normative analysis during clause extraction:
- **`DECLARATIVE_POLICY_ASSERTION_PATTERN`**: Matches institutional present-tense declarative assertions (`The bank maintains`, `The institution enforces`, `Management ensures`, etc.).
- **`OPTIONALITY_PATTERN`**: Matches explicit discretionary carve-outs (`optional`, `at their discretion`, `should endeavour`, `where deemed appropriate`, `may optionally`).
- **`PERMISSIVE_EXECUTION_BEFORE_REVIEW_PATTERN`**: Recognizes execution permitted before supervisor review (`executed before review`, `executed prior to approval`, etc.).
- **Timing Classification (`_detect_approval_timing`)**: Permissive execution patterns take precedence over generic approval keywords, ensuring retrospective sign-offs are never credited as pre-execution controls.

### 3.2 Data Models (`backend/banking_crosswalk/models.py`)
`EnterpriseClause` was extended with backward-compatible normative fields:
```python
normative_type: Optional[str] = None
is_declarative_assertion: bool = False
```
Existing serialization and deserialization remain 100% backward-compatible with pre-E3.5 persisted database records and audit logs.

### 3.3 Reconciliation Engine (`backend/banking_crosswalk/reconciliation.py`)
In `validate_candidate_relationship`:
- If `clause.is_declarative_assertion` is True and the target obligation is mandatory, `dim.modality_comparison` is recorded as `"declarative_assertion_aligned"`, preventing unjustified downgrades.
- If `has_optionality` is True, `dim.modality_comparison` is recorded as `"enterprise_optional_vs_mandatory"`, enforcing `WEAKER_OR_POTENTIALLY_INSUFFICIENT`.
- If `_INDEFINITE_RETENTION_CONFLICT_PATTERN` matches against APP 11.2, `POTENTIAL_CONFLICT` is immediately assigned, with the statutory contradiction recorded.
- If `_INTERNAL_ATTACHMENT_DEPENDENCY_PATTERN` matches, `UNDETERMINED` is assigned with missing evidence specifying the referenced annexure/schedule.

### 3.4 Hybrid & LLM Provider Alignment (`backend/banking_crosswalk/semantic_reconciliation.py` & `providers.py`)
- `_compare_obligation_bound_timeframes`: Enhanced `TIMEFRAME_PATTERN` to capture `"calendar days"`, preventing false timeframe conflicts on statutory provisions like ASIC RG 271.56 ("30 calendar days").
- Mock reasoning provider accurately mirrors the deterministic precheck summary, eliminating false contradictions and ensuring Stage C veto mechanics function deterministically.

---

## 4. Verification and Non-Regression Guarantee

All changes were validated through:
1. Targeted unit and property tests in `backend/tests/test_e35_normative_evidence_assurance.py`.
2. Frozen regression suite on `E34_INDEPENDENT_EVALUATION_DATASET` (showing zero regressions and improved exact accuracy from 17 to 18 deterministic / 18 to 19 hybrid).
3. The new 30-clause, 8-questionnaire engineering reference benchmark in `E35_INDEPENDENT_EVALUATION_DATASET`.
