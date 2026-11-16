# P0 Playwright End-to-End Environment Matrix

## 1. Design Rationale

The obsolete `web/e2e/app.spec.ts` combined two mutually incompatible deployment assumptions in a single test: trying to sign in with local development fixture credentials (`analyst` / `analyst-local-pass`) against a container stack configured for **Production Public Demo** (`ENV=production`, `BANKING_CROSSWALK_TENANT_ID=public-demo`).

`web/e2e/app.spec.ts` has been removed and replaced by two dedicated Playwright specs mapped cleanly to explicit deployment modes in `.github/workflows/ci.yml`:

---

## 2. Environment & Test Matrix

| Attribute | Scenario A — Production Public Demo (`scenario_a_public_demo.spec.ts`) | Scenario B — Authenticated Private Workspace (`scenario_b_private_workspace.spec.ts`) |
| :--- | :--- | :--- |
| **`ENV` / `NODE_ENV`** | `production` | `production` |
| **`BANKING_CROSSWALK_TENANT_ID`** | `public-demo` | `ci-private-workspace` (non-demo tenant) |
| **`ALLOW_LOCAL_DEV_AUTH_BYPASS`** | unset (`false`) | `"false"` |
| **Database Backend (CI)** | Container default (`compose.yaml`) | PostgreSQL 17 (`compose.yaml` + `compose.postgres.yaml`, role `crosswalk_app`, RLS enforced) |
| **Credential Provisioning** | None (private login intentionally locked; fixture passwords rejected) | CI-generated ephemeral `WORKSPACE_SESSION_SECRET` (256-bit hex) and ephemeral `scrypt` hashed user `ci.reviewer` (`reviewer` role) in `WORKSPACE_USERS_JSON` |
| **Spec Filter Env** | `E2E_SCENARIO=public_demo` | `E2E_SCENARIO=private_workspace` |
| **Origin (`SMOKE_WEB_URL`)** | `http://localhost:3000` | `http://localhost:3000` |
| **Security Assertions** | • `session-badge` shows `Sign-In Required for Private Workspace`<br>• No `LOCAL DEVELOPMENT AUTH BYPASS ACTIVE` / fixture password leakage<br>• `/api/workspace` GET/POST fail closed (`403`/`503`)<br>• `analyst` / fixture login rejected (`401`/`403`/`503`, `authenticated !== true`) | • Unauthenticated `/api/workspace` GET/POST return `401`<br>• Wrong password login returns `401`<br>• `POST /api/workspace` without `X-CSRF-Token` returns `403`<br>• Session cookie is `HttpOnly` (`document.cookie` excludes `crosswalk_session`)<br>• Sign-out revokes session and replay of captured cookie returns `401` |
| **Functional Workflow Assertions** | • Switch to `Synthetic Demo Example (DEMO_BANKING_V1)`<br>• Load example -> Run assessment<br>• Verify `Traceable assessment results` and `Regulatory pack` render with 0 `pageerror`s | • UI login with ephemeral credentials -> `session-badge` reflects `ci-private-workspace` + `reviewer`<br>• Private upload controls visible<br>• Authenticated `import_policy_text` + `list_policies` persistence verified |

---

## 3. Execution Verification Notes

- **Local Verification (2026-11-16):**
  - Scenario A executed against production `next start` + `uvicorn banking_crosswalk.app:app` (`ENV=production`, `BANKING_CROSSWALK_TENANT_ID=public-demo`): **1 passed (`1.4s`)**.
  - Scenario B executed against production `next start` (`ENV=production`) + schema-migrated API (`BANKING_CROSSWALK_TENANT_ID=ci-private-workspace`, ephemeral `scrypt` `WORKSPACE_USERS_JSON`, `ALLOW_LOCAL_DEV_AUTH_BYPASS=false`) (note: FastAPI local API ran with `ENV=development` for SQLite compatibility since `ENV=production` rejects SQLite and local Docker Desktop Linux engine was stopped; full `ENV=production` PostgreSQL 17 Compose execution is exercised by CI `containers` job): **1 passed (`1.3s`)**.
