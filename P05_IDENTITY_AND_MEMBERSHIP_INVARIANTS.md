# DeepAudit Crosswalk — P0.5 Identity and Membership Invariants

**Date:** 2026-11-14  
**Classification:** Security Architecture Specification  
**Status:** Implemented & Verified in Test Matrix  
**Branch:** `fix/p05-identity-session-security-hardening`

---

## 1. Identity Trust Boundary Model

DeepAudit Crosswalk enforces an immutable five-stage security boundary for all operations on private tenant documentation:

```
[ Verified Identity ]
       │
       ▼
[ Current Tenant Membership ]
       │
       ▼
[ Enforced Permissions ]
       │
       ▼
[ Trusted Backend Assertion ]
       │
       ▼
[ Auditable Action ]
```

### Stage 1: Verified Identity
Every incoming request must authenticate using:
- A cryptographically verified HMAC-SHA256 session token (cookie or Bearer header).
- Valid, unexpired signature signed with `WORKSPACE_SESSION_SECRET` (>= 32 chars).
- Session ID (`sid`) that has not been revoked in the `DurableRevocationStore`.
- User ID (`sub`) that exists and is currently enabled (`disabled != true`) in the active user registry (`loadWorkspaceUsers()`).

### Stage 2: Current Tenant Membership
A valid user identity is not sufficient; the user must be an active member of the requested tenant:
- The user record must contain the requested `tenant_id` in its `tenants` mapping.
- If the tenant assignment was removed after the token was issued, the request fails closed immediately with `403 Forbidden`.
- In server-bound production, `tenant_id` must match `BANKING_CROSSWALK_TENANT_ID`.
- The reserved synthetic demo tenant `public-demo` is strictly forbidden from private workspace sessions.

### Stage 3: Enforced Permissions
Permissions are dynamically derived from the user's **current live tenant roles**, not static token claims:
- If a user was downgraded from `reviewer` to `analyst` mid-session, the user's effective permissions are immediately restricted to `analyst`.
- Any attempt to execute `clause:review` or `mapping:review` fails closed with `403 Forbidden` despite token claims.
- The static bearer token (`WORKSPACE_AUTH_TOKEN`) is restricted to `viewer` permissions.

### Stage 4: Trusted Backend Assertion
The frontend gateway mints a tamper-evident, short-lived (300-second TTL) assertion:
- Header: `X-Workspace-Context: <base64url(payload)>.<hmac_sha256_sig>`
- Claims: `user_id`, `tenant_id`, `roles`, `session_id`, `exp`.
- Upstream backend verifies the HMAC signature using the shared secret.
- Upstream backend verifies that `X-Tenant-ID`, `X-Actor`, and `X-Role` match the signed claims.

### Stage 5: Auditable Action
All database and review actions record the verified end-user identity:
- Reviewer attribution (`reviewer_actor`) records `ctx.user_id`, completely ignoring client-supplied body or header overrides.
- Database snapshots isolate tenant data via PostgreSQL Row-Level Security (`app.current_tenant`).

---

## 2. Invariant Specifications & Verification Proofs

| Invariant ID | Invariant Statement | Enforcement Mechanism | Verified Test Case |
|---|---|---|---|
| **INV-1** | **Deleted User Immediate Invalidation**<br>A deleted user must not retain access through an unexpired signed session. | `resolveSecurityContext` queries `loadWorkspaceUsers().get(claims.sub)`. Missing record returns 401. | Vitest: `J2: Deleted user is immediately rejected (401)` |
| **INV-2** | **Revoked Tenant Membership Immediate Denial**<br>Removing a tenant assignment immediately terminates access to that tenant. | `resolveSecurityContext` checks `registeredUser.tenants[effectiveTenant]`. Missing or empty roles returns 403. | Vitest: `J3: User removed from tenant membership is immediately rejected (403)` |
| **INV-3** | **Live Role Override (Downgrade Invariant)**<br>Token claims cannot be used to execute privileges revoked in the user store. | Effective roles are assigned from `liveTenantRoles`, overriding token claims. | Vitest: `J4: Role downgrade from reviewer to analyst immediately revokes clause approval rights (403)` |
| **INV-4** | **Multi-Process Revocation Persistence**<br>A logged-out or revoked session ID must remain revoked across process boundaries and restarts. | `DurableRevocationStore` persists revocation entries atomically to disk (`SESSION_REVOCATION_PATH`). | Vitest: `J1: DurableRevocationStore persists revocations across store instances via disk` |
| **INV-5** | **Password Hash Standard in Production**<br>In production, accounts without memory-hard salted hashes are discarded. | `loadWorkspaceUsers` drops accounts without `password_hash`; `verifyPassword` rejects non-scrypt/pbkdf2 formats. | Vitest: `H3: In production, plaintext passwords and unsalted sha256 are rejected` |
| **INV-6** | **CSRF Defense-in-Depth**<br>Cookie sessions require matching CSRF header and valid Origin/Referer. | `verifyCsrfProtection` validates Origin header against request URL and verifies `X-CSRF-Token` against session claim. | Vitest: `A12: Missing or invalid CSRF token returns 403` |
| **INV-7** | **Static Token Privilege Boundary**<br>Static automation tokens cannot approve requirements or delete policies. | Static bearer authentication strips approval and deletion permissions, forcing role `viewer`. | Vitest: `K1 & K2: Static WORKSPACE_AUTH_TOKEN is restricted to viewer permissions` |
| **INV-8** | **Backend Gateway Cryptographic Binding**<br>Direct backend requests to private tenants without valid gateway assertion fail closed. | `_verify_signed_workspace_context` enforces HMAC signature, unexpired TTL, and matching tenant/actor. | Pytest: `test_backend_private_tenant_requires_signed_workspace_context` |
| **INV-9** | **Public Demo Strict Isolation**<br>Synthetic demo tenant cannot access private questionnaires or persist data. | Gateway overrides `persist=False` and rejects `public-demo` on `/api/workspace`. Backend enforces `persist=False`. | Vitest: `F1–F6: Anonymous /api/analysis allows only stateless DEMO_BANKING_V1` |
| **INV-10** | **PostgreSQL RLS Non-Owner Constraint**<br>Production database operations must run under non-owner role with active RLS. | `SQLTenantStore.check_ready` rejects superuser and table owner roles in production. | Pytest: `test_repository.py` (28 live PostgreSQL RLS tests) |
