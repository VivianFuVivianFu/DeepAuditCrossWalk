# DeepAudit Crosswalk — Enterprise Beta Readiness Assessment

**Date:** 2026-11-04  
**Classification:** Technical Security, Architecture & Operations Review  
**Evaluator:** Senior Enterprise GRC Architect & Cloud Security Specialist  
**Target:** Enterprise Self-Service Beta Deployment

---

## 1. Executive Readiness Verdict

| Dimension | Readiness Status | Confidence | Summary |
| :--- | :---: | :---: | :--- |
| **Data Isolation & Multi-Tenancy** | **READY** | High | PostgreSQL forced Row-Level Security (RLS) protects all 8 persistent tables; tested in CI against PostgreSQL 17 and 18. |
| **Crosswalk & Gap Engine** | **READY** | High | Deterministic, rule-driven, 4-state applicability; candidate mappings never self-approve. |
| **Database Persistence & Migrations** | **READY** | High | Alembic migrations 0001 and 0002 verified; automated pg_dump/pg_restore backup test passes. |
| **API Boundary & Input Sanitization** | **READY** | High | Prompt injection detection, 32 MiB streaming limit, XXE entity expansion prevention, strict Pydantic schemas. |
| **Enterprise Authentication & SSO** | **NOT READY** | Low | Currently relies on HTTP headers (`X-Tenant-ID`, `X-API-Key`); no native JWT/OIDC signature verification. |
| **Web UI Self-Service Experience** | **NOT READY** | Low | Web UI is an ephemeral single-policy demo; cannot upload files, manage baselines, or review mappings. |
| **Overall Enterprise Beta Readiness** | **CONDITIONAL GO** | — | **Go for Guided Enterprise Pilot / API-led Integration**.<br>**No-Go for General Self-Service Beta** until SSO and UI upload workflows are deployed. |

---

## 2. Technical Security & Authorization Audit

### 2.1 Multi-Tenant Data Isolation & PostgreSQL RLS
The backend implements multi-tenant segregation at both the application repository layer and the PostgreSQL database engine layer.

1. **Database-Level Row-Level Security (RLS)**:
   - Migration [`0002_enterprise_policy_layer.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/migrations/versions/0002_enterprise_policy_layer.py) enables and forces RLS on all enterprise tables:
     ```sql
     ALTER TABLE "enterprise_policies" ENABLE ROW LEVEL SECURITY;
     ALTER TABLE "enterprise_policies" FORCE ROW LEVEL SECURITY;
     CREATE POLICY tenant_isolation ON "enterprise_policies"
       USING (tenant_id = nullif(current_setting('crosswalk.tenant_id', true), ''))
       WITH CHECK (tenant_id = nullif(current_setting('crosswalk.tenant_id', true), ''));
     ```
   - Verified by test [`test_postgresql_rls_protects_queries_even_without_tenant_predicates`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_repository.py): A connection from a shared pool executing `SELECT * FROM enterprise_policies` without setting `crosswalk.tenant_id` returns 0 rows. Attempting an `INSERT` without a valid tenant context raises a database error.
2. **Application-Level Isolation**:
   - `SQLTenantStore` wraps each tenant operation in a transaction setting the PostgreSQL local configuration:
     ```python
     connection.execute(
         sa.text("SELECT set_config('crosswalk.tenant_id', :tenant, true)"),
         {"tenant": tenant_id},
     )
     ```
   - In-memory `TenantStore` partitions all registries by `tenant_id` dictionaries.

### 2.2 Untrusted Document Parsing & File Ingestion Hardening
All customer-uploaded files are treated as untrusted data and parsed deterministically:
* **Prompt Injection Defense**: In [`policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L39-L46), policy text is scanned against `INJECTION_PATTERNS` (e.g. `ignore previous instructions`, `system prompt`, `developer message`). Matching phrases are recorded as warnings rather than executed or parsed as instructions.
* **XXE & XML Entity Expansion**: The DOCX parser in [`policy_documents.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy_documents.py) uses `defusedxml` and verifies that entity expansion attacks fail closed (`test_docx_rejects_entity_expansion`).
* **Decompression Bomb Protection**: Excel workbook ingestion in [`questionnaires.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/questionnaires.py) enforces uncompressed size limits ($< 25$ MiB) and maximum cell graph counts ($< 500,000$ cells) before handing off to openpyxl (`test_workbook_import_rejects_excessive_cell_graph_before_openpyxl`).
* **Streaming Byte Limits**: The ASGI middleware [`RequestLimit`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/app.py#L23-L65) enforces a 32 MiB ceiling on chunked or streamed HTTP payloads, preventing Denial-of-Service memory exhaustion.

### 2.3 Authentication & Authorization Gap Analysis (Critical Finding)
* **Current State**: The backend uses shared API keys (`CROSSWALK_API_KEY`) and reads tenant and actor identity from HTTP headers:
  * `X-API-Key`: Required in production, verified with constant-time comparison `secrets.compare_digest`.
  * `X-Tenant-ID`: Identifies the tenant boundary.
  * `X-Actor`: Identifies user performing reviews (e.g. `alice@bank.com.au`).
  * `X-Role`: Enforces reviewer role (`risk`, `compliance`, `legal`).
* **Vulnerability in Self-Service Architecture**:
  * There is no cryptographic verification of `X-Tenant-ID` inside the backend itself. If the backend is directly exposed to public traffic without an upstream API Gateway (or if a compromised client forwards arbitrary headers), a tenant spoofing risk exists.
* **Remediation Required for Beta**:
  * Deploy an upstream API Gateway (e.g. Cloudflare Access, AWS API Gateway, Kong, or Next.js Auth Middleware) that terminates OAuth 2.0 / OIDC tokens, validates claims, and injects authenticated, signed tenant headers.

---

## 3. Persistence, Storage & Database Readiness

### 3.1 Production Fail-Closed Safety
To prevent accidental data loss in enterprise environments:
* When `ENV=production`, the application strictly requires `DATABASE_URL` pointing to PostgreSQL and a `CROSSWALK_API_KEY` of at least 32 bytes.
* Function `_require_crosswalk_state()` returns `HTTP 503 Service Unavailable` if stateful operations are attempted in ephemeral in-memory mode during production.
* SQLite is disallowed in production mode (`test_unmigrated_database_and_sqlite_production_fail_closed`).

### 3.2 Audit Trail Immutability
* Audit events are stored in the `audit_events` table.
* PostgreSQL triggers block `UPDATE`, `DELETE`, and `TRUNCATE` operations on `audit_events` (`test_postgresql_audit_cannot_be_modified_or_truncated`).
* All gap reviews, policy uploads, and mapping decisions generate immutable audit log entries with ISO 8601 UTC timestamps.

### 3.3 Backup & Disaster Recovery Verification
* CI pipeline executes real `pg_dump` and `pg_restore` verification:
  ```bash
  docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres -d crosswalk_test -Fc -f /tmp/crosswalk.backup
  docker exec "$POSTGRES_CONTAINER" createdb -U postgres crosswalk_restore
  docker exec "$POSTGRES_CONTAINER" pg_restore -U postgres -d crosswalk_restore /tmp/crosswalk.backup
  python scripts/verify_restored_database.py
  ```
* All seeded records, use-cases, and audit logs were confirmed intact post-restoration.

---

## 4. Deployment Readiness & Environments

### 4.1 Production Configuration Matrix

| Variable | Required in Prod | Validated Constraint | Description |
| :--- | :---: | :--- | :--- |
| `ENV` | Yes | Must be `"production"` | Activates strict production safeguards |
| `DATABASE_URL` | Yes | `postgresql+psycopg://...` | Connection to PostgreSQL 16+ with RLS |
| `CROSSWALK_API_KEY` | Yes | Length $\ge 32$ bytes | High-entropy gateway pre-shared secret |
| `BANKING_CROSSWALK_TENANT_ID` | Yes | Non-empty string | Default production tenant identifier |
| `ALLOWED_ORIGINS` | Yes | Explicit origins (no `*`) | CORS origins (e.g. `https://audit.bank.com.au`) |
| `CROSSWALK_API_URL` | Yes | URL | Internal backend URL for Next.js proxy |

### 4.2 Supported Deployment Topologies
1. **Containerized Stack (Recommended for Enterprise VPC / Kubernetes)**:
   - Built and tested via `compose.yaml` and `compose.postgres.yaml`.
   - Separate, non-root user execution (`USER 10001:10001`).
   - Playwright E2E and container smoke tests pass automatically in CI.
2. **Cloud Hybrid (Vercel Frontend + Railway/AWS Backend)**:
   - Next.js web application deployed to Vercel.
   - FastAPI container deployed to Railway / AWS ECS with PostgreSQL RDS.
   - Note: Requires Vercel Serverless Function to communicate with private backend via secure VPN or authenticated gateway.

---

## 5. Enterprise Beta Finding & Risk Matrix

| Finding ID | Domain | Severity | Title & Root Cause | Impact | Recommended Remediation |
| :---: | :--- | :---: | :--- | :--- | :--- |
| **SEC-01** | Security | **High** | Absence of native OIDC / JWT signature verification in backend | Reliance on perimeter gateway to assert `X-Tenant-ID` | Implement Supabase / Auth0 JWT middleware in FastAPI or validate tokens in Next.js middleware. |
| **UI-01** | Frontend | **High** | Lack of Multi-Document and File Upload UI in web portal | Enterprise users cannot upload PDF/Word policies without CLI/API | Build Enterprise Policy Manager in Next.js with drag-and-drop file upload. |
| **UI-02** | Frontend | **Medium** | Absence of Mapping Review & Sign-Off Screen in UI | Compliance officers cannot confirm or reject candidate mappings | Add interactive Unified Control Crosswalk Review table to web portal. |
| **REP-01** | Reporting | **Medium** | Absence of PDF / DOCX Executive Gap Report Export | Users only receive raw JSON; executive committees cannot read format | Implement ReportLab or headless Chromium PDF export for Crosswalk Reports. |
| **DOC-01** | Ingestion | **Low** | Scanned PDF OCR pipeline absent | Scanned image-only PDFs fail with 422 error | Integrate AWS Textract / Google Cloud Vision OCR for legacy scanned policies. |
| **CFG-01** | Catalog | **Low** | Enterprise baseline entity-type selection hidden in UI | UI defaults to ADI, omitting AFSL/ACL toggles | Add institution selector (ADI, AFSL, ACL) in frontend intake screen. |

---

## 6. Beta Recommendation

### Verdict: **CONDITIONAL GO**

#### Scenario A: **Guided Enterprise Pilot (Recommended)** — **GO**
* Deployed as a private instance in an enterprise environment (or VPC) where DeepAudit integration engineers configure the tenant, upload authorized AIAF workbooks via API, and connect corporate policies.
* Enterprise compliance teams use the web interface for use-case intake and JSON report review.
* **Safety**: Fully safe. Multi-tenant RLS guarantees data isolation, and all mathematical and regulatory rules are verified.

#### Scenario B: **Self-Service Public Enterprise Beta** — **NO-GO**
* Do not release as a self-service SaaS portal until:
  1. **SEC-01** (OIDC/SAML Authentication) is implemented.
  2. **UI-01** (Multi-Policy File Upload UI) is implemented.
  3. **REP-01** (Executive PDF Report Export) is implemented.

