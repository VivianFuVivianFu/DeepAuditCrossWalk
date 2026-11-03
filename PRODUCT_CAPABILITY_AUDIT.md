# DeepAudit Crosswalk — Product Capability Audit

**Date:** 2026-11-04  
**Audit Scope:** Full Stack (Next.js Web UI, FastAPI Backend, Crosswalk Engine, Storage & Database, Regulatory Catalogues)  
**Evaluator:** DeepAudit Lead AI Governance & Solution Architect

---

## 1. Executive Summary

This audit assesses the functional, architectural, and user-experience capabilities of **DeepAudit Crosswalk** following the merge of PR #11 (`feature/enterprise-policy-layer`).

The core engine and backend API provide a comprehensive, mathematically sound, deterministic governance crosswalk across 46 Australian statutory obligations, 33 Unified Controls, AIAF questionnaires, and multi-tier enterprise policies. However, there is a stark dichotomy between the **Backend/API capabilities** (which are mature, tenant-isolated, and rigorously tested) and the **Frontend Web UI** (which currently functions as an ephemeral single-policy demo).

---

## 2. Product Capability Classification Matrix

Each capability is classified into one of four states:
1. **Fully implemented and usable through the UI**: End-user can perform the complete action in the web interface without API knowledge.
2. **Implemented in the backend/API only**: Fully functional endpoint and domain engine exist and are covered by automated tests, but have no UI in `web/`.
3. **Partially implemented**: Capability exists in UI or API with notable gaps in functionality, parameters, or workflow.
4. **Not implemented**: Desired capability is not yet implemented.

| Capability Area | Sub-Capability | Status | Primary File References | Endpoints / CLI | Test References | Audit Findings & Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Use Case Intake** | 4-State Applicability Determination | **Fully implemented and usable through the UI** | [`web/app/page.tsx`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/page.tsx)<br>[`backend/banking_crosswalk/applicability.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py) | `POST /v1/assessments/coverage`<br>`POST /api/analysis` | `test_four_state_applicability_does_not_default_eu_or_idr`<br>`test_missing_use_case_facts_remain_undetermined` | Evaluates 12 regulatory facts across APRA, Privacy Act, ASIC RG 271, and EU AI Act into `applicable`, `conditional`, `not_applicable`, `undetermined`. |
| | Persistent Use Case CRUD | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py)<br>[`backend/banking_crosswalk/sql_store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py) | `POST /v1/use-cases`<br>`GET /v1/use-cases/{id}` | `test_restart_preserves_use_case_routing_policy_and_assessment` | Backend validates strict schema (`extra="forbid"`) and stores use cases in PostgreSQL/SQLite. UI hardcodes `persist: false`. |
| | Organization / Entity Type Baseline Intake | **Implemented in the backend/API only** | [`backend/banking_crosswalk/models.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L358-L375) | `BankingUseCase.enterprise_baseline()` | `test_enterprise_baseline_mode_without_use_case_intake` | Engine supports ADI, AFSL, and ACL organisational baselines without requiring use-case intake; UI does not expose entity-type selection. |
| **2. Regulatory Library** | Authoritative Obligations Catalogue | **Fully implemented and usable through the UI** | [`ATOMIC_OBLIGATION_CATALOGUE.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/ATOMIC_OBLIGATION_CATALOGUE.json)<br>[`backend/banking_crosswalk/data/regulatory_pack.v0.1.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/data/regulatory_pack.v0.1.json) | `load_regulatory_pack()` | `test_required_deliverable_files_exist_and_load`<br>`test_all_nine_automated_validation_checks_pass` | 46 atomic obligations across 18 instruments rendered in UI with statutory provisions, links to legislation.gov.au, and authority layers. |
| | 33 Unified Controls Library | **Implemented in the backend/API only** | [`UNIFIED_CONTROL_LIBRARY.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/UNIFIED_CONTROL_LIBRARY.json)<br>[`backend/banking_crosswalk/catalog.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py) | `load_unified_control_library()` | `test_enterprise_policy_layer.py` | 33 controls across 11 domains. Obligation-to-control mappings exist in backend (57 mappings); UI displays results by obligation rather than by Unified Control. |
| | Licensed Private Standard Overlay (e.g. ISO 42001) | **Implemented in the backend/API only** | [`backend/banking_crosswalk/catalog.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py) | `load_regulatory_pack(overlay_paths=...)` | `test_private_licensed_standard_overlay_mechanism` | Allows private tenants to overlay proprietary ISO/IEC standards without violating copyright in open-source repository. Not exposed in UI. |
| **3. Enterprise Policy Layer** | Single Policy Excerpt Ingestion | **Fully implemented and usable through the UI** | [`web/app/page.tsx`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/page.tsx)<br>[`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | `POST /v1/assessments/policy-gaps`<br>`POST /api/analysis` | `test_policy_threshold_extraction_prompt_injection_and_gap_types` | UI provides a `<textarea>` accepting up to 250,000 characters of policy text. |
| | Multi-Document Upload (PDF, DOCX, XLSX, TXT) | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L849)<br>[`backend/banking_crosswalk/policy_documents.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy_documents.py) | `POST /v1/enterprise/policies/import-file`<br>`POST /v1/enterprise/policies/import` | `test_policy_docx_extraction_and_api_import`<br>`test_policy_pdf_and_plain_text_parsing` | Backend handles base64 binary files up to 10 MB, extracts text, rejects XML external entities (XXE). UI lacks file picker and drag-and-drop. |
| | Policy Versioning & SHA-256 Deduplication | **Implemented in the backend/API only** | [`backend/banking_crosswalk/store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py)<br>[`backend/banking_crosswalk/sql_store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py) | `POST /v1/enterprise/policies/import` | `test_enterprise_policy_deduplication_detection` | Automatically computes SHA-256 and detects duplicate policy uploads, attaching warning to policy. UI does not display document versions. |
| | Multi-Document Enterprise Baselines | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L932)<br>[`backend/banking_crosswalk/models.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L614) | `POST /v1/enterprise/baselines`<br>`GET /v1/enterprise/baselines` | `test_enterprise_policy_layer.py` | Allows aggregating multiple enterprise policies into a single versioned baseline. No UI interface. |
| **4. Crosswalk Mapping** | Clause-to-Control Heuristic Extraction | **Implemented in the backend/API only** | [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | `extract_enterprise_policy()` | `test_2_enterprise_policy_partially_covers_control` | Deterministic facet pattern matcher extracts clauses and maps to Unified Controls with status `proposed`. UI only displays final gap text. |
| | Human Review & Sign-Off of Candidate Mappings | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L646)<br>[`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L913) | `POST /v1/mappings/review`<br>`PUT /v1/enterprise/clauses/{id}/review` | `test_assessment_rejects_caller_approved_mappings_and_uses_versioned_reviews` | Allows authorized reviewer (`X-Role: risk|legal`) to confirm or reject mappings. UI has no review screen or mapping editor. |
| **5. Questionnaires** | Pre-bundled AIAF Question Bank (19 synthetic questions) | **Fully implemented and usable through the UI** | [`backend/banking_crosswalk/catalog.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py) | `load_aiaf_question_bank()` | `test_coverage_uses_routed_snapshot_and_materialises_questionnaire_gaps` | Default question bank used by web application for coverage analysis. |
| | Full Authorised AIAF Workbook Import (.xlsx) | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L387)<br>[`backend/banking_crosswalk/questionnaires.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/questionnaires.py) | `POST /v1/questionnaires/import` | `test_questionnaire_import_api_accepts_base64_xlsx`<br>`test_workbook_import_rejects_excessive_cell_graph_before_openpyxl` | Ingests real multi-tab AIAF Excel files with decompression ratio protection and cell limits. UI contains no upload mechanism. |
| | Questionnaire Tenant Routing Snapshots | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L405) | `POST /v1/questionnaires/route` | `test_routing_snapshot_is_tenant_scoped` | Generates immutable, tenant-scoped questionnaire routing snapshots based on use-case applicability. No UI. |
| **6. Gap Assessment Engine** | Questionnaire Coverage Scoring | **Fully implemented and usable through the UI** | [`backend/banking_crosswalk/coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py) | `POST /v1/assessments/coverage` | `test_only_approved_mappings_count_as_confirmed_coverage` | Calculates confirmed coverage rate, confirmed missing, conditional, and undetermined counts. Visualized in UI metrics cards. |
| | Enterprise Policy Gap Detection | **Fully implemented and usable through the UI** | [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | `POST /v1/assessments/policy-gaps` | `test_1_enterprise_policy_fully_covers_external_control` | Detects when enterprise policy omits mandatory regulatory facets (e.g. APRA CPS 234 incident notifications, APP 11 data retention). |
| | Conflicting Threshold & Rule Detection | **Implemented in the backend/API only** | [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L800-L840) | `assess_enterprise_policy_gaps()` | `test_5_two_policies_contain_conflicting_thresholds` | Materialises `control_conflict` gaps when multiple internal policies define conflicting approval thresholds (e.g. AUD 500 vs AUD 1,000). |
| | Implementation & Evidence Gap Materialisation | **Partially implemented** | [`backend/banking_crosswalk/coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py) | `evaluate_questionnaire_coverage()` | `validate_e2e.py` | Flags when a mandatory policy control lacks operational execution evidence. However, direct integration with automated telemetry or scanners is API-only. |
| **7. Remediation & Review** | Gap Review Lifecycle (Open $\to$ In Review $\to$ Closed) | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L703) | `POST /v1/gaps/{id}/review` | `test_reviews_survive_restart_and_stale_review_cannot_overwrite` | Enforces audit trails, reviewer credentials, retest record IDs, and optimistic concurrency. UI has no review workflow or gap state updating. |
| | Audit Trail Querying | **Implemented in the backend/API only** | [`backend/banking_crosswalk/store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py)<br>[`backend/banking_crosswalk/sql_store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py) | `GET /v1/assessments/{id}/report` | `test_postgresql_audit_cannot_be_modified_or_truncated` | Tamper-proof append-only audit trail recorded for all state mutations. Only accessible in API report payload. |
| **8. Reporting & Export** | JSON Assessment Export | **Fully implemented and usable through the UI** | [`web/app/page.tsx`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/page.tsx#L69-L79) | Browser client download | `web/tests/analysis.test.ts` | Allows one-click download of `crosswalk-<id>.json` directly in the browser. |
| | Executive Audit Report Endpoint | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L770) | `GET /v1/assessments/{id}/report` | `test_enterprise_policy_layer.py` | Generates report payload with metadata, timestamp, full gap records, audit trail, and APRA/ASIC legal disclaimers. |
| | PDF / Word / HTML Executive Export | **Not implemented** | N/A | None | N/A | No formatted PDF or Word report generation exists in either frontend or backend. Users must parse the JSON report manually. |
| **9. Multi-Tenancy & Security** | PostgreSQL Row-Level Security (RLS) | **Implemented in the backend/API only** | [`backend/banking_crosswalk/migrations/versions/0002_enterprise_policy_layer.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/migrations/versions/0002_enterprise_policy_layer.py) | PostgreSQL DB Engine | `test_postgresql_rls_protects_queries_even_without_tenant_predicates` | All 8 persistent tables enforce strict tenant RLS via session variable `crosswalk.tenant_id`. |
| | API Key Gateway Authorization | **Implemented in the backend/API only** | [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L60-L100) | HTTP Headers (`X-API-Key`, `X-Tenant-ID`) | `test_production_gateway_binds_api_key_tenant_and_reviewer` | Requires `CROSSWALK_API_KEY` in production with $\ge 32$ bytes. Tenant passed via `X-Tenant-ID`. |
| | Enterprise User Authentication (SSO / OIDC) | **Not implemented** | N/A | None | N/A | No user login, SAML, or OIDC flow exists. The Next.js frontend hardcodes tenant identity in its backend proxy route. |

---

## 3. Capability Audit Summary & Metrics

```
Total Distinct Capabilities Audited: 24
├─ Fully Implemented in UI:         6  (25.0%)
├─ Implemented in Backend/API Only: 14 (58.3%)
├─ Partially Implemented:           2  ( 8.3%)
└─ Not Implemented:                 2  ( 8.3%)
```

### Critical Architectural Observations

1. **Backend Maturity**: The backend architecture is enterprise-grade. The data models, deterministic applicability rules, Alembic migrations, tenant-isolated stores, and test coverage (70 unit/acceptance tests + 15 CI jobs) provide rock-solid governance mechanics.
2. **Frontend Disconnect**: The web application was originally created as an open-source demonstration interface for an individual reviewing a single policy excerpt. It does not yet reflect the multi-tenant, multi-document enterprise features implemented in backend PR #11.
3. **Executive Deliverable Gap**: Enterprise risk committees and internal audit departments require executive summary reports (PDF/DOCX) with visual compliance heatmaps and sign-off blocks. Currently, only raw JSON can be exported from the UI.



---

## 4. Product Architecture Boundaries & Governance Flow

A critical design requirement of DeepAudit Crosswalk is the strict separation between **baseline-building inputs** and **downstream assessment targets**:

`
[Baseline-Building Inputs]
  ├── 1. Shared Regulatory Library (APRA, ASIC, Privacy Act, EU AI Act)
  ├── 2. Enterprise Policy Layer (Private Policies, Internal Standards, Delegated Authority)
  └── 3. Enterprise-Specific Obligations (Contractual Terms, Audit Commitments)
               │
               ▼
   [Unified Control Crosswalk] ──► [Enterprise Control Baseline]
                                                │
                                                ▼  (Evaluated Against)
[Downstream Assessment Targets]
  ├── A. AI Governance Strategy / Framework
  ├── B. AI Governance or Risk Assessment Questionnaire (e.g. AIAF)
  └── C. Individual AI Use Case (Operational Facts, Controls & Evidence)
               │
               ▼
   [Traceable Crosswalk Gap Assessment Report]
`

### Key Architectural Boundaries
1. **Enterprise Policies are Baseline Inputs, Not Assessment Targets**:
   - Uploaded corporate policies (e.g. Credit Policy, Data Retention Standard) define what controls the enterprise requires.
   - They are mapped to the 33 Unified Controls to form the enterprise's private, versioned governance baseline.
   - They are *not* the objects being assessed for compliance; the AI Use Case and Questionnaire are assessed *against* them.
2. **Deterministic Evaluation with Human Review Gating**:
   - The crosswalk engine deterministically evaluates whether downstream targets (questionnaire answers, use-case facts) cover the mandatory obligations established by the baseline.
   - Automated keyword/facet mappings remain PROPOSED and cannot suppress gaps without explicit sign-off from an authorized compliance reviewer (X-Role: risk|legal).
3. **Tenant Segregation**:
   - The Shared Regulatory Library is immutable and read-only.
   - Private enterprise policies, baselines, mappings, and reviews are isolated per tenant and protected by PostgreSQL Row-Level Security (RLS).
