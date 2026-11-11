# DeepAudit Crosswalk — P0 Document Workspace Security Threat Model

## 1. Executive Summary & Objective

This threat model identifies, analyses, and specifies mitigations for the production document-first workspace in **DeepAudit CrossWalk**. 

The authoritative purpose of DeepAudit Crosswalk is:
> **Evaluate an organisation's AI Governance Strategy or AI Governance / Assurance Questionnaire against applicable regulatory and governance requirements, and identify coverage gaps.**

The core architectural requirement is establishing an unbroken, verifiable end-to-end security boundary:
```
User Authentication → Trusted Session → Tenant Membership → Permission Check → Authorised Backend Operation → Audit Record
```

A backend service API key or a configured tenant ID must **never** substitute for an independently verified end-user identity.

---

## 2. System Architecture & Trust Boundaries

```
[ Browser / API Client ]
         │
         │  (1) HTTPS Request:
         │      - Session Cookie (HttpOnly, SameSite=Lax) OR Bearer JWT
         │      - X-CSRF-Token (state-changing POST/PUT/DELETE)
         ▼
[ Next.js Web Gateway: /api/workspace ]
   ├── Authentication Engine: resolveSecurityContext()
   ├── CSRF Verification: verifyCsrfProtection()
   ├── Tenant Membership Check: resolveUserMembership()
   ├── Role-Based Access Control: ACTION_PERMISSIONS[action]
   └── Context Signing: HMAC-SHA256(user_id, tenant_id, roles, session_id, exp)
         │
         │  (2) Server-to-Server Internal Request:
         │      - X-API-Key (gateway-to-backend authentication)
         │      - X-Tenant-ID (verified tenant context)
         │      - X-Actor (verified end-user ID)
         │      - X-Role (verified primary role)
         │      - X-Workspace-Context (HMAC-SHA256 signed context assertion)
         ▼
[ FastAPI Analysis Service: /v1/* ]
   ├── _require_crosswalk_api_key() (Gateway Authentication)
   ├── _tenant_context() & _verify_signed_workspace_context()
   ├── _reject_public_demo_tenant() on private endpoints
   ├── _enforce_role_if_present() per endpoint action
   └── _validate_reviewer_identity() on clause/mapping review
         │
         │  (3) Transactional Database Operations
         ▼
[ SQL Tenant Store / PostgreSQL with Row-Level Security ]
   ├── Strict tenant_id filtering on all tables
   └── In-memory store fallback fail-closed in production
```

### Trust Boundary Analysis
1. **Untrusted Boundary A (Browser to Web Gateway)**:
   - External network, untrusted user environment, arbitrary JavaScript execution context.
   - Attack vectors: session hijacking, CSRF, credential stuffing, parameter tampering, spoofed tenant headers.
2. **Trusted Boundary B (Web Gateway to FastAPI Backend)**:
   - Protected server-to-server loopback or private container network.
   - Attack vectors: direct backend invocation bypassing the web gateway, forged context headers (`X-Tenant-ID`, `X-Actor`, `X-Role`).
   - Mitigation: Mutual verification using `CROSSWALK_API_KEY` AND signed `X-Workspace-Context` assertion.
3. **Storage Boundary C (FastAPI to PostgreSQL / SQLite)**:
   - Multi-tenant persistence.
   - Attack vectors: cross-tenant data leakage, SQL injection, accidental tenant data blending.
   - Mitigation: Strict tenant scoping on all SQL queries and schema-level isolation.

---

## 3. Threat Assessment Matrix (STRIDE)

| Threat ID | STRIDE Category | Target Component | Threat Scenario & Impact | Mitigation & Security Control |
|---|---|---|---|---|
| **THREAT-01** | Spoofing | Web Gateway (`/api/workspace`) | **Unauthenticated Browser Access**: Attacker invokes `/api/workspace` without credentials when `BANKING_CROSSWALK_TENANT_ID` is set on server. Previously defaulted to "authenticated_single_tenant". | **Fails Closed**: `resolveSecurityContext()` requires verified session cookie, Bearer JWT, or valid static token. Server credentials alone never grant browser access. |
| **THREAT-02** | Spoofing / Elevation | Review Endpoints (`/clauses/{id}/review`) | **Spoofed Reviewer Attribution**: An analyst or external caller passes `actor="Senior Manager"` and `role="compliance"` in review payload to forge compliance approval. | **Attribution Binding**: The web gateway overrides payload `actor` and `role` with verified session values. FastAPI enforces `_validate_reviewer_identity` rejecting unauthorized roles (e.g. `analyst`, `viewer`). |
| **THREAT-03** | Tampering | Session Cookie | **Forged or Tampered Session Token**: Attacker modifies JWT payload to change tenant or escalate roles. | **HMAC-SHA256 Signature**: JWT signed with `WORKSPACE_SESSION_SECRET` (>= 32 chars). Tokens verified using constant-time comparison. Expired or tampered signatures fail closed with 401. |
| **THREAT-04** | Tampering | Backend Service API | **Direct FastAPI Invocation Bypassing Gateway**: Attacker sends requests directly to backend on port 8000 with forged `X-Tenant-ID` or `X-Role`. | **Signed Context Assertion**: When `WORKSPACE_SESSION_SECRET` is configured, FastAPI verifies `X-Workspace-Context` signature, tenant match, actor match, and expiration. Unsigned direct requests receive 401. |
| **THREAT-05** | Information Disclosure | Questionnaires & Policies | **Cross-Tenant Access**: User in Tenant A submits requests with `tenant_id="tenant-b"` to list questionnaires, read policies, or download audit reports. | **Tenant Scoping & Membership Validation**: Web gateway verifies user has active membership in the requested tenant before forwarding. FastAPI binds queries strictly to verified `X-Tenant-ID`. |
| **THREAT-06** | Information Disclosure | Synthetic Demo (`/api/analysis`) | **Customer Document Leakage via Public Demo**: Attacker attempts to evaluate private uploaded questionnaires or enterprise baselines using anonymous demo endpoint. | **Demo Isolation**: Anonymous `/api/analysis` endpoint strictly accepts only synthetic `DEMO_BANKING_V1` with `persist: false` under `public-demo` tenant. Any request specifying `questionnaire_id` or enterprise baselines is rejected with 400. |
| **THREAT-07** | Elevation of Privilege | Baseline Compilation | **Unauthorized Approval by Analyst**: An analyst approves internal clauses or compiles an Enterprise Baseline. | **4-Role RBAC Enforcement**: `ACTION_PERMISSIONS` enforces `clause:review`, `mapping:review`, and `baseline:create` requiring `reviewer` or `admin` role. Analysts and viewers receive 403 Forbidden. |
| **THREAT-08** | Tampering / CSRF | Web Gateway POST/PUT | **Cross-Site Request Forgery**: Malicious site triggers state-changing workspace operations via browser with ambient cookies. | **Double-Submit / Session CSRF & Origin Verification**: Validates Origin / Referer against host origin, and enforces matching `X-CSRF-Token` header for cookie-authenticated sessions. |
| **THREAT-09** | Denial of Service | Upload Endpoints | **Oversized Payload / Decompression Bomb**: Attacker uploads massive files or JSON bombs to exhaust memory. | **Strict Payload Guards**: 28 MB streaming cap for file uploads, 1 MB cap for JSON API calls, formula injection sanitisation, and ZIP bomb limits. |
| **THREAT-10** | Repudiation | Review Decisions | **Untraceable Approvals**: Ambiguous reviewer attribution makes audit decisions repudiable. | **Immutable Audit Trail**: Review actions record verified `user_id`, timestamp, and primary role in database and assessment reports. |

---

## 4. Deployment Modes & Security Posture

### Mode A: Public Synthetic Demo
- **Purpose**: Zero-setup anonymous demonstration using 19 synthetic questions (`DEMO_BANKING_V1`).
- **Access Control**: No authentication required on `/api/analysis`.
- **Isolation Guarantee**: Stateless (`persist: false`), restricted to `public-demo` tenant. Zero access to private questionnaires, enterprise policies, baselines, or customer data.

### Mode B: Local Community Edition
- **Purpose**: Self-hosted single-tenant evaluation without paid third-party authentication services.
- **Supported Options**:
  1. **Authenticated Self-Hosted Mode** (Default): Built-in account registry via `WORKSPACE_USERS_JSON` with standard accounts (Analyst, Reviewer, Viewer, Admin) and password authentication.
  2. **Local-Only Dev Bypass Mode**: Explicitly opted in via `ALLOW_LOCAL_DEV_AUTH_BYPASS=true`. Operates strictly when `ENV !== "production"`, bound to loopback interfaces, with a visible banner.

### Mode C: Hosted Authenticated Workspace
- **Purpose**: Enterprise production multi-tenant deployment.
- **Fail-Closed Requirements**:
  - `CROSSWALK_API_KEY` configured and >= 32 characters.
  - `WORKSPACE_SESSION_SECRET` configured and >= 32 characters.
  - Identity Provider configured via `OIDC_ISSUER_URL` or `WORKSPACE_USERS_JSON`.
  - Durable PostgreSQL database connected and migrated.
  - Absence of any required security setting halts startup or returns 503 Service Unavailable.
