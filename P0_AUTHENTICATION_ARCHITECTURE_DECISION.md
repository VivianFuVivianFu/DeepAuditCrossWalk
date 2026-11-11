# DeepAudit Crosswalk — P0 Authentication & Session Architecture Decision Record (ADR)

## Status
**Accepted & Implemented**

## Context & Problem Statement
In previous iterations, the document workspace gateway (`web/app/api/workspace/route.ts`) relied on server-side environment variables (`BANKING_CROSSWALK_TENANT_ID`, `BANKING_CROSSWALK_ACTOR`, `BANKING_CROSSWALK_ROLE`, and `CROSSWALK_API_KEY`) to interact with FastAPI. When `WORKSPACE_AUTH_TOKEN` was unconfigured, incoming browser requests were automatically granted `"authenticated_single_tenant"` access.

This created critical vulnerabilities:
1. **Unauthenticated Access**: Any client reaching the web server could upload documents and access private records.
2. **Reviewer Impersonation**: Review actions were attributed to the server-configured actor rather than an independently verified individual.
3. **No Community Self-Hosting Option**: Existing suggestions often proposed external enterprise cloud identity services (e.g., Auth0, Okta, Clerk) that would break self-hosted open-source operation.

## Decision Drivers
- **Zero Paid Dependencies**: Community Edition self-hosters must be able to run authenticated workspaces without cloud subscriptions or external SaaS dependencies.
- **Standards-Based Interoperability**: Support OIDC / OAuth2 Authorization Code Flow with PKCE (`S256`) for enterprise integrations (Keycloak, Microsoft Entra, Okta).
- **Enforceable End-to-End Boundary**: Browser requests must establish identity via signed `HttpOnly` session cookies or Bearer JWTs, and the web gateway must assert this identity to FastAPI via a signed context header (`X-Workspace-Context`).
- **Fail-Closed Security**: In production, missing credentials or unverified sessions must deny access with 401 or 503 rather than defaulting to open access.

---

## Architectural Decisions

### 1. Dual Identity Provider Strategy

```
               ┌────────────────────────────────────────────────────────┐
               │           DeepAudit Next.js Security Layer             │
               │                   (web/app/security.ts)                 │
               └──────────────────────────┬─────────────────────────────┘
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   ▼                                             ▼
     [ Self-Hosted Account Registry ]            [ Enterprise OIDC / OAuth2 ]
     - Configured via WORKSPACE_USERS_JSON       - Authorization Code + PKCE (S256)
     - Multi-tenant role mappings                - State & Nonce verification
     - Constant-time password verification       - Zero cloud subscription required
     - Default local dev accounts provided       - Self-hostable via Keycloak
```

1. **Built-in Self-Hosted Account Registry (`WORKSPACE_USERS_JSON`)**:
   - JSON-configured user directory mapping user credentials, display names, and tenant roles.
   - Evaluated using constant-time string and hash comparison.
   - Non-production environments provide default local test accounts (`analyst`, `reviewer`, `viewer`, `admin`).
2. **Standards-Based OIDC / OAuth2 with PKCE**:
   - Authorization Code flow with RFC 7636 PKCE (`S256` code challenge).
   - Cryptographically bound `state` and `nonce` parameters stored in signed `HttpOnly` cookies.
   - ID Token verification (issuer, audience, expiration, and nonce).

### 2. Session Management & CSRF Protection
- **Session Tokens**: Signed compact JWTs using HMAC-SHA256 (`alg: HS256`) keyed by `WORKSPACE_SESSION_SECRET`.
- **Cookie Attributes**: `HttpOnly; SameSite=Lax; Path=/; Max-Age=28800; Secure (in production)`.
- **Session Revocation**: Real-time revocation registry (`revokedSessions`) ensuring logout immediately invalidates the session token across subsequent requests.
- **Live User & Tenant Membership Check**: On each request, the security layer verifies that the user account is active and that the user's tenant membership and assigned roles remain valid in the registry. Role downgrades or membership removals take effect immediately.
- **CSRF Defense**: Double-submit cookie with session-bound `csrf_token` sent in `X-CSRF-Token` header, combined with Origin and Referer header validation.

### 3. Gateway-to-Backend Signed Context Assertion (`X-Workspace-Context`)
To prevent direct invocation of the FastAPI service with forged identity headers:
- The web gateway constructs a signed payload:
  ```json
  {
    "user_id": "usr-123",
    "tenant_id": "tenant-corp",
    "roles": ["reviewer"],
    "session_id": "sess-456",
    "exp": 1731300000
  }
  ```
- Signed using HMAC-SHA256 with `WORKSPACE_SESSION_SECRET` and transmitted via `X-Workspace-Context: <base64url_payload>.<signature>`.
- FastAPI verifies the signature, expiration, and header consistency (`X-Tenant-ID`, `X-Actor`, `X-Role`).

---

## Consequences

### Positive
- **Complete Access Control**: Unauthenticated access to private documents is eliminated.
- **True Multi-Tenancy**: Users can belong to multiple tenants with distinct roles per tenant.
- **Review Decision Integrity**: Approvals are immutably tied to verified user identities.
- **Open-Source Compatibility**: Anyone can self-host locally or on Docker without external accounts.

### Negative / Trade-offs
- In multi-instance deployments, server-side revocation requires shared Redis or database storage (the current in-memory revocation registry is per-process, with JWT expiration providing the ultimate bounded lifecycle).
