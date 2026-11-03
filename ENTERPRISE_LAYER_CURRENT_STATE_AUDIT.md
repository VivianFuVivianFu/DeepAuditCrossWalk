# Enterprise Regulatory & Policy Layer — Current State Audit

**Repository**: `VivianFuVivianFu/DeepAuditCrossWalk`  
**Date**: November 2026  
**Auditor**: Senior AI Governance & Enterprise GRC Architect  
**Scope**: Backend (`backend/banking_crosswalk`), Frontend (`web/app`), Data & Schema Layer  

---

## 1. Executive Summary

This audit evaluates whether `DeepAuditCrossWalk` contains a production-ready, reusable **Enterprise Regulatory & Policy Layer**.

### Core Verdict
An **ephemeral, heuristic policy extraction and two-way gap analyzer** exists in the codebase (`backend/banking_crosswalk/policy.py`), but a **persistent, reusable Enterprise Regulatory & Policy Layer DOES NOT exist**. 

Currently:
1. **No Enterprise Catalogue**: Policies cannot be catalogued, organized by business domain, version-controlled across revisions, or aggregated into a single organizational control baseline.
2. **Disconnected from Unified Controls**: Policy clauses are matched strictly via raw keyword/token heuristics against `obligation.coverage_facets` and hardcoded string regexes. They have **zero connection** to the 33 Unified Controls (`UNIFIED_CONTROL_LIBRARY.json`).
3. **One-Way Workflow Separation**: The Questionnaire Coverage engine (`coverage.py`) completely ignores enterprise policies. Only the Policy Gap engine (`policy.py`) evaluates policies, and it can only accept a single `PolicyPack` at a time.
4. **No True Tenant Authentication or Access Control**: Tenant isolation relies entirely on an unauthenticated client-supplied `X-Tenant-ID` header.
5. **No Enterprise UI**: The web frontend only provides a demo text area for pasting a raw text snippet (max 250,000 chars) into a shared `public-demo` tenant. No document upload, management, or review UI exists.

---

## 2. Capability Audit Matrix

Every capability specified in Phase 1 is audited and classified below:

| # | Capability | Classification | Primary Code References | Implementation Summary & Technical Evidence |
|---|---|---|---|---|
| 1 | **Enterprise Policy Layer Existence** | **Partially Implemented** | `models.py` L480-536<br>`policy.py` L1-433 | Basic data models (`PolicyClause`, `PolicyPack`, `PolicyGapAssessment`) and evaluation functions exist, but there is no policy registry, document hierarchy, or multi-document baseline. |
| 2 | **Heuristic Extraction & Two-Way Gap Assessment** | **Fully Implemented** | `policy.py` L105-168, L222-386<br>`models.py` L480-499 | `extract_policy_pack()` parses text into clauses using regex patterns. `assess_policy_gaps()` detects missing policy coverage for regulatory obligations, missing questionnaire coverage for mandatory policy clauses, implementation evidence gaps, and AUD threshold conflicts. |
| 3 | **Document Ingestion (`/import` & `/import-file`)** | **API Only** | `api.py` L345-379<br>`policy_documents.py` L22-68 | Endpoints accept raw text (`/import`) or Base64-encoded PDF, DOCX, TXT, MD (`/import-file`). Parsed clauses are converted to `PolicyPack`. The raw files and document metadata are discarded immediately. |
| 4 | **Policy Storage, Versioning & Cross-Assessment Reuse** | **Partially Implemented** | `store.py` L75-88<br>`sql_store.py` L192-205<br>`api.py` L482-537 | `PolicyPack` is saved as a single JSON blob in table `policies`. However, versioning is a static string (`version="unversioned"`). There is no list endpoint (`GET /v1/policies` does not exist), and each assessment can only reference a single `policy_pack_id`. |
| 5 | **Mapping to Unified Controls** | **Not Implemented** | `policy.py` L171-210<br>`models.py` L236-283 | Policy clauses are mapped **only to 3 generic string facets** (`human_approval_required`, `approval_threshold_defined`, `pre_execution_block`) or token-matched against `obligation.coverage_facets`. There is no mapping to `CTRL-*` IDs. |
| 6 | **Independent Enterprise Requirement Ingestion** | **Not Implemented** | `catalog.py` L42-95<br>`models.py` L105-132 | The system cannot register custom `AtomicObligation` records or independent enterprise regulatory frameworks. All obligations are strictly loaded from static JSON files in the shared library. |
| 7 | **Multi-Document Enterprise Control Baseline** | **Not Implemented** | `policy.py` L222-240<br>`api.py` L490-515 | `assess_policy_gaps()` accepts exactly one `policy_pack: PolicyPack`. There is no capability to aggregate multiple uploaded policies (e.g., AI Policy + Privacy Standard + Procurement Guide) into a consolidated baseline. |
| 8 | **Tenant-Level Segregation & User Authorisation** | **Partially Implemented** | `api.py` L45-63<br>`sql_store.py` L65-85 | Tenant segregation exists in the database schema (`tenant_id` columns), but is authenticated only via an untrusted `X-Tenant-ID` header. No user authentication, session, or role validation exists. |
| 9 | **Dual-Engine Policy Utilization (Coverage & Gaps)** | **Not Implemented** | `coverage.py` L341-375<br>`api.py` L426-479 | `evaluate_questionnaire_coverage()` has no parameter for `PolicyPack` and only tests shared regulatory obligations. Enterprise policies cannot be validated during questionnaire coverage checks. |
| 10 | **No-Code Web UI for Policy Management** | **Not Implemented** | `web/app/page.tsx` L19-25, L210-230<br>`web/app/api/analysis/route.ts` | The frontend only has a raw text `<textarea>` for pasting excerpts up to 250k chars. There is no file upload button, no document catalogue table, and no review/approval interface. |

---

## 3. Deep-Dive Code Analysis

### 3.1 Policy Extraction Engine (`backend/banking_crosswalk/policy.py`)
- **Injection Sanitization**: Scans for 6 regex patterns (e.g., `ignore previous instructions`, `bypass security`). Matches do not abort parsing; they append warnings to `PolicyPack.warnings` (L32-47, L110-120).
- **Clause Splitting**: Splits on double newlines or bullet patterns. A SHA-256/MD5 stable ID is generated: `_stable_clause_id(name, raw_clause)` (L19-29).
- **Facet Extraction**:
  - `MANDATORY_PATTERN`: Checks for `must`, `shall`, `required to`, `may not`, `prohibited` (L39-42).
  - `GENERIC_FACET_PATTERNS`: Hardcoded to 3 strings: `human_approval_required`, `approval_threshold_defined`, and `pre_execution_block` (L50-78).
  - `AUD_PATTERN`: Extracts monetary thresholds using `(?:AUD\s*\$?\s*|\$\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)` (L43-47).
- **Critical Limitation**: Real-world enterprise AI governance policies address model inventorying, bias mitigation, data lineage, vendor zero-data retention, and cybersecurity escalation. The extractor ignores all of these because its facet dictionary is hardcoded to 3 transactional payment approval concepts.

### 3.2 Document Import Processing (`backend/banking_crosswalk/policy_documents.py`)
- **Limits**: Maximum 20 MiB file size, maximum 200 DOCX zip entries, maximum 5 MiB uncompressed text (L17-20).
- **Format Support**:
  - `.pdf`: Uses PyMuPDF (`fitz`) via `extract_document_from_pdf` (plain text extraction; scanned images without OCR fail).
  - `.docx`: Zip-slip and zip-bomb validation with `defusedxml.ElementTree`, followed by paragraph and table extraction via `docx.Document`.
  - `.txt` / `.md`: UTF-8 decoding with BOM support.
- **Architectural Void**: The original binary is discarded immediately. It is not archived in object storage, cannot be downloaded for audit evidence, and page-level bounding boxes are not saved.

### 3.3 Storage and Tenancy (`backend/banking_crosswalk/sql_store.py` & `store.py`)
- Table `policies`:
  ```sql
  CREATE TABLE policies (
      tenant_id VARCHAR(64) NOT NULL,
      policy_id VARCHAR(64) NOT NULL,
      payload JSONB NOT NULL,
      created_at TIMESTAMP WITH TIME ZONE NOT NULL,
      PRIMARY KEY (tenant_id, policy_id)
  );
  ```
- Storage is purely document-level JSON serialization. There are no relational tables for individual policy clauses, no indices on extracted facets, and no query capabilities across tenant policies.
- In `store.py`, in-memory dictionary `self._policies: Dict[str, Dict[str, PolicyPack]]` mirrors the SQL store.

### 3.4 Web Client & Proxy (`web/app/page.tsx` & `web/app/api/analysis/route.ts`)
- In `page.tsx`, switching to `kind === "policy-gaps"` displays a plain `<textarea>` for `Policy excerpt` (L212-225).
- In `route.ts`, requests are routed to `${CROSSWALK_API_URL}/v1/assessments/policy-gaps` with:
  ```typescript
  headers: {
    "X-Tenant-ID": process.env.BANKING_CROSSWALK_TENANT_ID || "public-demo",
  }
  ```
- Persist is forced to `false` in the web client, preventing any browser-based creation of persistent enterprise policy assets.

---

## 4. Conclusion & Audit Findings

The existing codebase contains a well-tested **proof-of-concept algorithm for detecting delegated-authority payment threshold conflicts** between credit cards and banking policies. 

However, to support Australian enterprise AI governance (APRA CPS 230, Privacy Act, National AI Ethics Principles, and internal board risk tolerances), the system requires an **Enterprise Requirements Catalogue** that bridges enterprise policy clauses directly to the 33 Unified Controls and integrates seamlessly into both Crosswalk engines.

