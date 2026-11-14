# DeepAudit Crosswalk — P0.5 Backend Trust Boundary Verification

**Date:** 2026-11-14  
**Classification:** Backend Security Audit & Technical Verification  
**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Test Suite:** `backend/tests/test_p0_security_remediation.py`

---

## 1. Architectural Trust Boundary

The DeepAudit Crosswalk architecture separates the client-facing presentation layer from the core regulatory assessment and persistence engine:

```
[ Browser / API Client ]
       │
       ▼ (HTTPS, Cookie / Bearer Token, CSRF Token)
[ Next.js Workspace Gateway ]
       │
       ▼ (Private Network, X-API-Key, Signed X-Workspace-Context)
[ FastAPI Assessment & Persistence Engine ]
       │
       ▼ (SQL Connection, RLS Context: SET LOCAL app.current_tenant)
[ PostgreSQL Database (crosswalk_runtime role, NOBYPASSRLS) ]
```

### Trust Boundary Rules
1. **No Direct Client Access to Backend:** Direct client requests must never be exposed without traversing the Next.js gateway or presenting a valid server-to-server `X-API-Key` and cryptographically signed `X-Workspace-Context`.
2. **Context Integrity:** Gateway asserts end-user identity and role claims via HMAC-SHA256 signed `X-Workspace-Context`.
3. **Secret Entropy:** Both gateway and backend enforce `WORKSPACE_SESSION_SECRET` length >= 32 characters in production. If weak or missing, requests fail closed (503).
4. **Header vs Body Alignment:** Reviewer actions require exact match between `X-Actor`, `X-Role`, the signed context claims, and the JSON payload fields.

---

## 2. Verification Test Results

All backend trust boundary tests were executed against FastAPI via `pytest` and passed 100%:

| Test Name | Verification Objective | HTTP Result | Status |
|---|---|:---:|:---:|
| `test_reproduce_vuln_c_analyst_and_viewer_cannot_approve...` | Analyst and Viewer cannot approve clauses or control mappings | `403 Forbidden` | **PASS** |
| `test_reproduce_vuln_d_reviewer_identity_enforced_against_spoofing` | Forged reviewer attribution in body vs headers rejected | `403 Forbidden` | **PASS** |
| `test_cross_tenant_isolation_questionnaires_and_policies` | Cross-tenant policy, clause, and questionnaire access blocked | `403 / 404` | **PASS** |
| `test_cross_tenant_isolation_baselines_and_assessments` | Cross-tenant baseline and assessment report access blocked | `403 / 404` | **PASS** |
| `test_sql_store_tenant_isolation_under_sqlite_and_postgres` | Store-level tenant isolation across storage engines | `NotFoundError` | **PASS** |
| `test_public_demo_tenant_cannot_access_private_endpoints` | Public-demo tenant blocked from private endpoints and persistence | `403 Forbidden` | **PASS** |
| `test_viewer_cannot_run_assessments_in_private_tenant` | Viewer role blocked from triggering new assessments | `403 Forbidden` | **PASS** |
| `test_backend_private_tenant_requires_signed_workspace_context` | Private tenant requests without `X-Workspace-Context` rejected | `401 Unauthorized` | **PASS** |
| `test_backend_production_rejects_short_secret_with_503` | Production with secret < 32 chars fails closed | `503 Unavailable` | **PASS** |
| `test_backend_rejects_expired_and_tampered_workspace_context` | Expired timestamp or invalid HMAC signature rejected | `401 Unauthorized` | **PASS** |
| `test_backend_rejects_tenant_and_actor_mismatch_with_context` | Tenant or Actor mismatch between headers and signed context rejected | `403 Forbidden` | **PASS** |

**Backend Security Suite Summary:**
```
collected 11 items
backend/tests/test_p0_security_remediation.py ........... [100%]
11 passed, 1 warning in 3.51s
```

---

## 3. Cryptographic Signature Verification Details

In `backend/banking_crosswalk/api.py`, `_verify_signed_workspace_context` performs:
1. Canonical JSON parsing of the URL-safe base64 payload.
2. Constant-time comparison (`secrets.compare_digest`) between expected HMAC-SHA256 and received signature.
3. Expiration validation: `exp > time.time()`.
4. Tenant binding: `ctx_tenant == expected_tenant` using constant-time comparison.
5. User and role binding: ensures caller cannot spoof `X-Actor` or `X-Role` outside of signed assertion claims.
