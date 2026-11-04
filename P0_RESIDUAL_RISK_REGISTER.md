# P0 Residual Risk Register: DeepAudit Crosswalk

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Evaluation Branch:** `audit/p0-final-validation`  
**Base Commit (main):** `e41469845f9223344e9630c7a71597928062e1bf`  
**Evaluation Standard:** Enterprise AI Governance Risk Management Framework (APRA CPS 230 / CPS 234 Aligned)  
**Date:** November 2026  

---

## 1. Risk Scoring Framework & Methodology

DeepAudit Crosswalk utilizes a 5×5 Risk Assessment Matrix aligned with Australian Prudential Regulation Authority (APRA) prudential practice guides:

| Likelihood (L) | Impact (I) | Overall Risk Score (L × I) | Risk Severity Level | Action Required |
|---|---|---|---|---|
| 1: Rare | 1: Insignificant | 1 – 4 | **Low** | Acceptable; monitor via normal operational cadence. |
| 2: Unlikely | 2: Minor | 5 – 9 | **Moderate** | Manageable; requires defined mitigation in next sprint. |
| 3: Possible | 3: Moderate | 10 – 14 | **High** | Significant exposure; requires formal mitigation plan and senior sign-off. |
| 4: Likely | 4: Major | 15 – 19 | **Critical** | Unacceptable for production; requires immediate remediation or gate block. |
| 5: Almost Certain | 5: Severe / Catastrophic | 20 – 25 | **Severe** | Executive escalation; immediate operational halt. |

---

## 2. Summary Risk Register

| Risk ID | Risk Domain & Description | Inherent Risk (L × I) | Inherent Level | Residual Risk (L × I) | Residual Level | Direction | Target Phase | Designated Owner |
|---|---|---|---|---|---|---|---|---|
| **RISK-01** | **Semantic Mapping Recall Deficit** (38.89% baseline extraction recall) | 5 × 4 = 20 | **Severe** | 3 × 3 = 9 | **Moderate** | Decreased | P1 | Head of AI Engineering |
| **RISK-02** | **Synthetic-Only Ground Truth** (0 external legal reviews for 61 cases, 2 ambiguous) | 4 × 4 = 16 | **Critical** | 3 × 3 = 9 | **Moderate** | Decreased | P1 | Chief Risk Officer / Legal Counsel |
| **RISK-03** | **Scope Bounding & Unimplemented Downstream Targets** (Strategy & Telemetry 501s) | 4 × 3 = 12 | **High** | 1 × 3 = 3 | **Low** | Decreased | P1 / P2 | Principal Product Architect |
| **RISK-04** | **Gateway Header-Based Auth Reliance** (`X-Tenant-ID` header without JWT verification) | 4 × 5 = 20 | **Severe** | 2 × 4 = 8 | **Moderate** | Decreased | P1 | Application Security Lead |
| **RISK-05** | **Multi-Currency & Unstructured Legal Exception Parsing** (FX conversion & complex waivers) | 3 × 4 = 12 | **High** | 2 × 3 = 6 | **Moderate** | Decreased | P1 / P2 | GRC Lead Analyst |
| **RISK-06** | **Lack of Self-Service Review UI** (Frontend review screen disconnected from review gate) | 4 × 3 = 12 | **High** | 2 × 3 = 6 | **Moderate** | Decreased | P1 | Frontend Tech Lead |
| **RISK-07** | **Ephemeral In-Memory Store vs Enterprise PostgreSQL RLS** (Storage persistence & RLS isolation) | 4 × 5 = 20 | **Severe** | 2 × 4 = 8 | **Moderate** | Decreased | P1 | Infrastructure & Data Architect |

---

## 3. Detailed Risk Item Assessments

### RISK-01: Semantic Mapping Recall Deficit (38.89% Baseline Extraction Recall)
* **Risk Description**: In baseline construction, regex pattern matching misses 11 of 18 expected control facets across synthetic evaluation clauses (recall = 38.89%). An organization uploading complex enterprise policies will see many valid controls unextracted as candidates, creating initial manual classification burden.
* **Inherent Risk**: **5 × 4 = 20 (Severe)**. High probability of missing internal policy controls without human oversight.
* **Current P0 Mitigation**: 
  1. Compulsory Human Review Gate: All extracted candidate mappings carry `review_status="proposed"`. No candidate clause enters a compiled baseline without explicit human approval (`"approved"` status).
  2. Strict Baseline Compilation Gating: The API rejects compiling any baseline that contains unreviewed or rejected candidate clauses.
  3. False-Control Trigger Suppression: False candidate triggers on exclusions eliminated to 0.0%.
* **Residual Risk**: **3 × 3 = 9 (Moderate)**. The review gate prevents unverified controls from entering baselines, but the low recall imposes manual work on users to manually input missing controls.
* **Recommended P1 Remediation**: Implement **Option C (Hybrid Architecture)** combining deterministic validation with an LLM-assisted candidate suggestion engine (P1 controlled experiment).
* **Designated Owner**: Head of AI Engineering.

---

### RISK-02: Synthetic-Only Ground Truth (0 External Human Panel Reviews)
* **Risk Description**: The evaluation dataset [`MAPPING_EVALUATION_DATASET.json`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/MAPPING_EVALUATION_DATASET.json) consists of 63 cases, of which 61 are synthetic reference cases created by internal engineering and 2 are unresolved legal edge cases. Zero cases have undergone formal independent review by external GRC experts or Australian financial regulatory counsel.
* **Inherent Risk**: **4 × 4 = 16 (Critical)**. Discrepancies between synthetic interpretations and actual regulatory enforcement precedents could misalign control classifications.
* **Current P0 Mitigation**:
  1. Explicit Dataset Provenance Logging: `evaluate_semantic_mapping.py` prints explicit provenance warnings during every execution run.
  2. Formal Legal Ambiguity Flagging: The two ambiguous cases (`BASE-24` and `BASE-25` regarding offshore cloud hosting and APRA CPS 234 multi-tenancy) are explicitly segregated and excluded from binary pass/fail assertions.
* **Residual Risk**: **3 × 3 = 9 (Moderate)**. Internal benchmarks are reproducible and transparently documented, but external legal validation is required prior to external market launch.
* **Recommended P1 Remediation**: Convene an Independent Banking GRC Review Panel (comprising former APRA supervisors and banking technology risk partners) to review and formally sign off on all 63 benchmark cases.
* **Designated Owner**: Chief Risk Officer / Legal Counsel.

---

### RISK-03: Scope Bounding & Unimplemented Downstream Targets (Strategy & Telemetry 501s)
* **Risk Description**: Downstream assessment targets for AI Governance Strategies and Standalone AI Use Case Operational Telemetry are not yet built. If client documentation or marketing materials imply full automation of these targets, users could face expectation mismatches.
* **Inherent Risk**: **4 × 3 = 12 (High)**. Product misrepresentation risk and regulatory audit scrutiny.
* **Current P0 Mitigation**:
  1. Truthful Scope Bounding: Production endpoints `/assessments/strategy` and `/assessments/use-case` explicitly return `HTTP 501 Not Implemented`.
  2. Clear Error Payloads: Error JSON documents precisely what capabilities are supported (Mode A / Mode B Questionnaire Assessment) and what roadmap phase implements Strategy / Telemetry.
  3. Deprecation of Proxy Benchmarks: Strategy proxy measurements are explicitly labeled as non-representative of product accuracy.
* **Residual Risk**: **1 × 3 = 3 (Low)**. The system fails safely and transparently without misleading users or executing partial logic.
* **Recommended P1/P2 Remediation**: Build the Strategy Assessment Engine in P1 (Roadmap P1-3) and Use Case Telemetry Ingestion in P2 (Roadmap P2-1).
* **Designated Owner**: Principal Product Architect.

---

### RISK-04: Gateway Header-Based Authentication Reliance (`X-Tenant-ID`)
* **Risk Description**: The FastAPI backend currently resolves tenant tenancy via the `X-Tenant-ID` HTTP header without cryptographic JWT verification, mutual TLS (mTLS), or OAuth 2.0 bearer tokens. In an untrusted network environment, an attacker could spoof the tenant ID header to access another organization's baselines or assessments.
* **Inherent Risk**: **4 × 5 = 20 (Severe)**. Threat of cross-tenant data exfiltration in multi-tenant SaaS deployments.
* **Current P0 Mitigation**:
  1. Fail-Closed Tenant Resolution: Missing `X-Tenant-ID` immediately raises `HTTP 401 Unauthorized`.
  2. Strict Storage-Level Tenant Isolation: All database and in-memory store queries mandate `tenant_id` scoping; attempting to access a baseline belonging to another tenant returns `HTTP 404 Not Found`.
  3. Network Boundary Assumption: Documented requirement that the API must run behind an authenticated API Gateway (e.g. AWS API Gateway, Kong, or Azure APIM) that validates mTLS / JWT and strips/injects verified headers.
* **Residual Risk**: **2 × 4 = 8 (Moderate)**. Safe when deployed behind enterprise API gateways, but unacceptable for direct public internet exposure.
* **Recommended P1 Remediation**: Implement OAuth 2.0 / OpenID Connect (OIDC) JWT validation directly within `backend/banking_crosswalk/api.py` with signed claims validation and tenant ID extraction from cryptographically signed tokens.
* **Designated Owner**: Application Security Lead.

---

### RISK-05: Multi-Currency & Unstructured Legal Exception Parsing
* **Risk Description**: PR #16 successfully implemented numeric threshold parsing across 12 banking governance scenarios, including multi-currency extraction (AUD, USD, EUR, GBP). However, cross-currency comparisons currently rely on static or missing exchange rate conversion, and highly convoluted legal clauses (nested conditionals, committee exception waivers) may escape deterministic AST bounds.
* **Inherent Risk**: **3 × 4 = 12 (High)**. Cross-border credit scoring or multi-currency procurement could trigger false threshold conflicts or overlook executive waivers.
* **Current P0 Mitigation**:
  1. Deterministic AST/Interval Modeling: Monetary thresholds are parsed into formal intervals `(min, max]` with currency symbols attached.
  2. Currency Discrepancy Flagging: Mismatched currencies without explicit conversion rates are surfaced as unverified compliance exceptions rather than silent approvals.
* **Residual Risk**: **2 × 3 = 6 (Moderate)**. Handled safely for single-currency and standard multi-currency scenarios; edge cases fall back to human review.
* **Recommended P1/P2 Remediation**: Add daily FX rate ingestion service and an unstructured legal waiver classification engine.
* **Designated Owner**: GRC Lead Analyst.

---

### RISK-06: Lack of Self-Service Review UI
* **Risk Description**: While backend review gate endpoints (`POST /baselines/{id}/clauses/{clause_id}/review`, `POST /baselines/{id}/compile`) are fully operational and verified, the React frontend (`web/src/App.tsx`) does not yet provide interactive UI buttons for compliance officers to approve, reject, or reclassify candidate clauses.
* **Inherent Risk**: **4 × 3 = 12 (High)**. Enterprise users cannot complete the baseline review workflow without using curl, Postman, or custom API scripts.
* **Current P0 Mitigation**:
  1. Fully Documented REST API: OpenAPI documentation and comprehensive curl/python scripts provide clear instructions for API-driven baseline management.
  2. Backend Security Enforcement: Incomplete reviews are blocked at the server level regardless of client interface.
* **Residual Risk**: **2 × 3 = 6 (Moderate)**. Functional for technical integrations and pilots, but blocks non-technical risk officers from standalone self-service evaluation.
* **Recommended P1 Remediation**: Wire the Enterprise Policy Baseline Review workspace in the React frontend to the PR #14 / PR #15 review gate endpoints.
* **Designated Owner**: Frontend Tech Lead.

---

### RISK-07: Ephemeral In-Memory Store vs Enterprise PostgreSQL RLS
* **Risk Description**: DeepAudit Crosswalk includes an in-memory dictionary store (`store._enterprise_baselines`) and a PostgreSQL repository (`PostgresStore`). In development and ephemeral testing modes, data is stored in memory and lost on restart. In PostgreSQL mode, tenant segregation relies on application query clauses rather than database-enforced Row Level Security (RLS).
* **Inherent Risk**: **4 × 5 = 20 (Severe)**. Risk of data loss in ephemeral deployments and potential multi-tenant data bleed if application queries are misconfigured.
* **Current P0 Mitigation**:
  1. Strict Application Scoping: All repository methods enforce `WHERE tenant_id = :tenant_id` parameter binding.
  2. SHA-256 Baseline Fingerprinting: Out-of-band database modifications or cross-tenant data injections are caught by cryptographic fingerprint verification (HTTP 422).
* **Residual Risk**: **2 × 4 = 8 (Moderate)**. Data integrity is cryptographically protected, but enterprise production environments demand formal database-level RLS.
* **Recommended P1 Remediation**: Enable native PostgreSQL Row Level Security (`ALTER TABLE enterprise_baselines ENABLE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation_policy...`) and configure connection pooling with tenant session variables.
* **Designated Owner**: Infrastructure & Data Architect.

---

## 4. Overall P0 Readiness Conclusion

The P0 development cycle has successfully reduced all critical safety risks (false-control triggers, silent fallback, threshold miscalculation) to acceptable levels (**no residual risk exceeds Moderate / Score 9**).

The remaining moderate risks are strictly bounded by fail-closed architectural gates:
- The **Recall Deficit (Risk 01)** cannot cause false compliance because unreviewed candidate clauses are never included in baselines.
- The **Auth Reliance (Risk 04)** is mitigated by API gateway encapsulation.
- The **UI Gap (Risk 06)** affects user experience, not regulatory safety.

DeepAudit Crosswalk is therefore formally certified as **SAFE for Internal Testing and Supervised Enterprise Pilots**, subject to the P1 roadmap commitments detailed in [`NEXT_PHASE_ARCHITECTURE_DECISION.md`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/NEXT_PHASE_ARCHITECTURE_DECISION.md).
