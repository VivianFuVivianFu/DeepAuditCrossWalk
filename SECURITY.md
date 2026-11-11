# Security Policy

## Reporting Security Issues

We take the security of DeepAudit Crosswalk seriously. If you discover a security vulnerability, please report it privately:

- **GitHub Security Advisories**: Use GitHub's private vulnerability reporting feature on repository [`VivianFuVivianFu/DeepAuditCrossWalk`](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/security/advisories/new).
- **Direct Maintainer Contact**: If private reporting is unavailable, reach out privately through the maintainer's GitHub profile before publicly disclosing details.

Please do not open public issues containing exploit steps, private documents, or sensitive credentials.

---

## Security Architecture & Guarantees

DeepAudit Crosswalk enforces strict multi-tenant isolation, role-based access control, and identity verification:

1. **Authentication & Session Security**:
   - Private document workspace routes (`/api/workspace`) require an authenticated user session.
   - Sessions use `HttpOnly; SameSite=Lax` cookies or Bearer JWTs signed with HMAC-SHA256 (`WORKSPACE_SESSION_SECRET` >= 32 characters).
   - Real-time session revocation ensures immediate invalidation upon logout.
2. **Reviewer Attribution & Invariants**:
   - Clause review and control mapping review operations are strictly segregated and require `reviewer` or `admin` roles.
   - Decisions are immutably attributed to verified user identities (`user_id`), preventing client-side spoofing.
   - Evaluated candidate mappings never automatically confirm coverage without explicit human approval (P1-S0 invariant).
3. **Multi-Tenant Isolation**:
   - Uploaded customer questionnaires, internal policies, clauses, baselines, assessments, and reports are isolated by `tenant_id`.
   - Cross-tenant requests are denied with `403 Forbidden`.
   - Public demo operations are strictly confined to the stateless `public-demo` tenant and cannot access customer document records.
4. **Defense in Depth**:
   - Double-submit session-bound CSRF validation on all state-changing browser requests.
   - Web gateway asserts identity to the backend service using signed `X-Workspace-Context` headers and mutual `CROSSWALK_API_KEY` verification.
   - Strict payload streaming limits (28 MB for file uploads, 1 MB for JSON payloads), XML external entity (XXE) mitigation, and formula injection guards.
   - Database operations enforce tenant isolation and Row-Level Security in PostgreSQL.

For detailed architecture decisions and threat modeling, see:
- [`P0_WORKSPACE_SECURITY_THREAT_MODEL.md`](P0_WORKSPACE_SECURITY_THREAT_MODEL.md)
- [`P0_AUTHENTICATION_ARCHITECTURE_DECISION.md`](P0_AUTHENTICATION_ARCHITECTURE_DECISION.md)
- [`P0_ROLE_PERMISSION_MATRIX.md`](P0_ROLE_PERMISSION_MATRIX.md)
- [`P0_SECURITY_REGRESSION_RESULTS.md`](P0_SECURITY_REGRESSION_RESULTS.md)
