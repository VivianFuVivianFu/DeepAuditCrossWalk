# Deployment & Operations Guide

## Overview
DeepAudit Crosswalk provides three distinct operational deployment modes:

1. **Mode A — Public Synthetic Demo**:
   - Zero-setup evaluation of 19 synthetic banking questions (`DEMO_BANKING_V1`).
   - Accessible anonymously via `/api/analysis`.
   - Strictly stateless (`persist: false`) within the isolated `public-demo` tenant. Zero access to private customer documents, enterprise policies, or baselines.
2. **Mode B — Local Community Edition (Self-Hosted)**:
   - Self-hosted single-tenant operation without paid third-party authentication services.
   - **Authenticated Self-Hosted Mode (Default)**: Employs the built-in account registry via `WORKSPACE_USERS_JSON` with standard accounts (`analyst`, `reviewer`, `viewer`, `admin`) and password verification.
   - **Local-Only Dev Bypass Mode**: Explicitly opted in via `ALLOW_LOCAL_DEV_AUTH_BYPASS=true` strictly when `ENV !== "production"` and requests originate from loopback interfaces (`127.0.0.1` / `localhost`). Displays a clear warning banner.
3. **Mode C — Hosted Authenticated Workspace (Enterprise Production)**:
   - Fails closed if security configuration is missing.
   - Enforces signed `HttpOnly; SameSite=Lax` session cookies or Bearer JWTs, session-bound CSRF protection, tenant membership checks, and 4-role RBAC (`viewer`, `analyst`, `reviewer`, `admin`).
   - Forwarding to FastAPI uses internal `CROSSWALK_API_KEY` and HMAC-SHA256 signed `X-Workspace-Context` assertions.
   - Requires durable PostgreSQL with Row-Level Security (RLS).

---

## Quick Start (Docker Compose)

### 1. Local Evaluation
```bash
docker compose up --build
```
Starts the standalone FastAPI service on `127.0.0.1:8000` and the Next.js web application on `127.0.0.1:3000`.

Default local accounts available in non-production:
- **Analyst**: `analyst` / `analyst-local-pass`
- **Reviewer**: `reviewer` / `reviewer-local-pass`
- **Viewer**: `viewer` / `viewer-local-pass`
- **Admin**: `admin` / `admin-local-pass`

### 2. Persistent Evaluation (PostgreSQL)
```bash
docker compose -f compose.yaml -f compose.postgres.yaml up --build -d --wait
```
Applies schema migrations automatically and runs against PostgreSQL with isolated tenant roles.

---

## Configuration Reference

| Variable | Scope | Required In Production | Purpose |
|---|:---:|:---:|---|
| `ENV` | Both | Yes | Set to `production` or `development`. |
| `CROSSWALK_API_URL` | Web | Yes | Upstream URL of the FastAPI service (e.g. `http://api:8000` or `http://127.0.0.1:8000`). |
| `CROSSWALK_API_KEY` | Both | Yes (>= 32 chars) | Shared secret key authenticating web gateway requests to the backend service. |
| `WORKSPACE_SESSION_SECRET` | Both | Yes (>= 32 chars) | Secret used to sign session cookies, CSRF tokens, and `X-Workspace-Context` assertions. |
| `BANKING_CROSSWALK_TENANT_ID` | Both | Yes | Server-bound tenant identifier. Must not be `public-demo` in private workspaces. |
| `WORKSPACE_USERS_JSON` | Web | Optional | JSON array of user credentials, display names, and tenant-role mappings for self-hosted auth. |
| `ALLOW_LOCAL_DEV_AUTH_BYPASS` | Web | No (Dev only) | Set to `true` to allow loopback dev bypass without login in non-production environments. |
| `OIDC_ISSUER_URL` | Web | Optional | OpenID Connect discovery URL for enterprise single sign-on (e.g. Keycloak). |
| `OIDC_CLIENT_ID` | Web | Optional | OIDC application client ID. |
| `OIDC_CLIENT_SECRET` | Web | Optional | OIDC client secret. |
| `DATABASE_URL` | Backend | Yes (in Prod) | PostgreSQL connection string for non-owner application user. |
| `ALLOWED_ORIGINS` | Backend | Yes | Comma-separated list of permitted CORS origins (e.g. `http://localhost:3000`). |
| `ALLOW_EPHEMERAL_CROSSWALK` | Backend | No | Explicit override to permit in-memory store in production (demo purposes only). |

---

## Health & Readiness Probes
- `/health`: Liveness probe indicating the HTTP server is responsive.
- `/ready`: Readiness probe verifying database connectivity, schema migration status, and tenant isolation flags.

Containers run under non-root users with `no-new-privileges:true` and `cap_drop: ["ALL"]`.
