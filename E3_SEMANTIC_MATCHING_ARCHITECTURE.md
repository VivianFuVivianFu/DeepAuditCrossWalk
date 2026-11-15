# E3 Semantic Matching Architecture

> **Status**: Implemented as an **optional, opt-in** backend capability (`SEMANTIC_MATCHING_ENABLED=false` by default). Preserves E1 and E1.1 deterministic safety boundaries and requires human review before any requirement relationship or questionnaire coverage confirmation becomes binding.

---

## 1. Design Goal & Non-Negotiable Safety Boundaries

DeepAudit Crosswalk's core pipeline stays strictly unchanged:

**Shared Regulatory Library + Optional Approved Enterprise Baseline → Requirement Reconciliation → Effective Assessment Baseline → Document Coverage Assessment**

E3 inserts an optional semantic matching accelerator inside **Requirement Reconciliation** (and optional advisory candidate retrieval inside Questionnaire Mapping) using a four-stage gated pipeline:

**Embedding (Stage A) → LLM Semantic Analysis (Stage B) → Deterministic Validation / Stage C Veto Power → Human Review (Stage D)**

Key safety invariants enforced in code (`backend/banking_crosswalk/semantic_reconciliation.py`):

1. **Deterministic Stage C has veto power**:
   - Deterministic reconciliation rules are always evaluated on the unmodified extracted `EnterprisePolicyClause` (`validate_hybrid_candidate_relationship()`). LLM-suggested `inferred_covered_facets` are **never** injected into deterministic facet matching, so an LLM cannot conjure an `EQUIVALENT` classification from paraphrased prose alone.
   - Paraphrase recoveries where Stage B flags semantic overlap but deterministic facets do not prove full equivalence are capped at `PARTIALLY_OVERLAPPING` and forced to `decision_status="needs_review"` (`NEEDS_REVIEW`).
   - Quantitative threshold, approval-timing, and authority-level conflicts (`CONFLICTS_WITH`) are always determined by the deterministic engine; an LLM cannot override or soften a deterministic conflict.
   - `UNRELATED` / `NONE` dismissal from the LLM is honoured only when the deterministic comparator does not hold a substantive relationship (`EQUIVALENT`, `STRICTER_THAN`, `CONFLICTS_WITH`, `PARTIALLY_OVERLAPPING`, `DUPLICATES_INTERNAL`).
2. **Never auto-approves**: Hybrid candidates enter storage only as `PROPOSED` or `NEEDS_REVIEW`. Effective Assessment Baseline composition still consumes only approved non-stale `ReconciliationDecision` records.
3. **Never inflates confirmed questionnaire coverage**: `suggest_questionnaire_mappings_hybrid()` creates `PROPOSED` suggestions only (`Confirmed Covered = 0 (0.0%)` across all evaluated Section 7 runs).
4. **Shared Regulatory Library untouched**: `regulatory_pack.v0.1.json`, unified control catalog, and existing E1/E1.1 ground-truth datasets were not altered.
5. **Fail-closed security vs. resilient provider degradation**:
   - Policy and misconfiguration errors (`ConfidentialityPolicyError`, `ProviderConfigurationError`) **always propagate fail-closed** (HTTP `403` / `503`) and never silently fall back.
   - Transient runtime provider errors (`ProviderQuotaError`, `ProviderTimeoutError`, `ProviderUnavailableError`, `ProviderOutputError`) degrade cleanly to deterministic-only reconciliation (`matching_mode="deterministic_fallback"`), recording fallback diagnostics rather than crashing or hanging.

---

## 2. Stage-by-Stage Pipeline Architecture

### Stage A — Hybrid Candidate Retrieval (`retrieve_hybrid_candidates`)
1. Runs existing deterministic candidate retrieval first so every rule-based control, facet, and legal-provision match is preserved.
2. When `SemanticMatchingMode` is `EMBEDDING_ONLY` or `HYBRID` and an `EmbeddingProvider` is active, embeds obligation texts and clause texts via `EmbeddingProvider.embed()` with normalized dimensions (default `256` for Gemini `gemini-embedding-001`) and `APICallBudgetTracker` enforcement.
3. Scores cosine similarity between clause embeddings and obligation embeddings, augmenting top-$k$ retrieval candidates without discarding any deterministic hits.

### Stage B — Structured LLM Semantic Analysis
1. Runs only when `SemanticMatchingMode == HYBRID` and a `ReasoningProvider` is available.
2. Sanitizes all untrusted enterprise policy text and external descriptions via `sanitize_untrusted_text()`, replacing prompt-injection directives with `"[sanitized-untrusted-directive]"`.
3. Requests strict schema-validated JSON conforming to `SemanticRelationshipAnalysis` (`extra="forbid"`), capturing:
   - `semantic_relevance`
   - proposed relationship / semantic overlap assessment
   - `inferred_covered_facets`, `missing_requirement_facets`
   - verbatim `supporting_quote` / citations
   - `uncertainty_flags` and concise rationale
4. Validates every `supporting_quote` against the source clause text using `validate_semantic_citation()`, rejecting fabricated or out-of-bounds citations (`CitationVerificationError` → `ProviderOutputError`).

### Stage C — Deterministic Validation (`validate_hybrid_candidate_relationship`)
1. Executes deterministic dimension and relationship evaluation over `(clause, obligation, use_case)`.
2. Applies Stage C veto rules:
   - Conflicting deterministic thresholds/timing/authority always force `CONFLICTS_WITH` + `NEEDS_REVIEW`.
   - Unproven `EQUIVALENT` claims without deterministic canonical facet proof are capped at `PARTIALLY_OVERLAPPING` + `NEEDS_REVIEW`.
   - Paraphrase-only semantic recoveries without deterministic equivalence proof are capped at `PARTIALLY_OVERLAPPING` + `NEEDS_REVIEW`.
   - Internal enterprise telemetry/provenance vault clauses are distinguished from APRA CPS 234 / APP 11 security/privacy obligations via explicit scope/context rules.
3. Records provenance fields on `ReconciliationDecision`:
   - `matching_mode`: `"deterministic_only" | "embedding_plus_deterministic" | "hybrid_embedding_llm_deterministic" | "deterministic_fallback"`
   - `embedding_similarity`: `Optional[float]` in `[-1.0, 1.0]`
   - `semantic_analysis`: sanitized structured analysis metadata
   - `semantic_provider_meta`: non-secret provider, model, lifecycle warning, and fallback telemetry

### Stage D — Human Review & Effective Baseline Binding
All hybrid decisions require reviewer sign-off (`PUT /v1/enterprise/reconciliations/{reconciliation_id}/review`) with revision optimistic locking before `POST /v1/enterprise/baselines/{baseline_id}/effective-baseline` can include them.

---

## 3. Code Modules Added / Updated

- [llm/\_\_init\_\_.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/__init__.py) — Package exports for provider-agnostic E3 interfaces and security controls.
- [llm/types.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/types.py) — Pydantic configs, strict structured schemas (`SemanticRelationshipAnalysis`, `QuestionnaireSemanticMatchAnalysis`), error hierarchy, `GEMINI_MODEL_DEPRECATION_REGISTRY`, `ProviderLifecycleWarning`, `UsageTelemetry`.
- [llm/security.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/security.py) — Prompt-injection sanitization, secret scrubbing, HTTPS endpoint validation, `self_hosted` vs `official_hosted` credential isolation, hard free-tier confidential block, citation grounding check, `APICallBudgetTracker`.
- [llm/providers.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/providers.py) — `EmbeddingProvider`, `ReasoningProvider`, `GoogleGeminiProvider`, `OpenAICompatibleProvider`, `DeterministicMockSemanticProvider`, `SemanticProviderBundle`, `build_provider_bundle()`, `check_gemini_model_lifecycle()`.
- [semantic_reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/semantic_reconciliation.py) — Stages A–D reconciliation pipeline (`generate_hybrid_reconciliation_candidates`, `validate_hybrid_candidate_relationship`) and hybrid questionnaire suggestion helper (`suggest_questionnaire_mappings_hybrid`).
- [models.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py) — Additive E3 metadata fields on `ReconciliationDecision`.
- [api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) — Per-request `matching_mode` support on `POST /v1/enterprise/baselines/{baseline_id}/reconcile` and `GET /v1/enterprise/llm-status`.
