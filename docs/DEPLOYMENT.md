# Deployment

`docker compose up --build` starts the standalone API on `127.0.0.1:8000` and
the web app on `127.0.0.1:3000`. Images run under non-root users. No service from
the original DeepAudit project is required. The Docker contexts exclude source
workbooks, bank policies, environment files, virtual environments and Git history.

For local Python setup, install `backend[dev]` into an isolated virtual environment.
For the web app use `npm ci`; its lockfile is committed. Python's declared ranges
are resolved at installation; review and lock a tested environment before an
enterprise deployment. CI audits the resolved dependency set.

For Compose, copy `.env.example` to `.env` for service configuration. When
running the processes directly, export these values in the API shell and put
the web values in `web/.env.local` (or export them in the web shell). The web proxy uses
`CROSSWALK_API_URL` and optional `CROSSWALK_API_KEY`; these variables must never
use the `NEXT_PUBLIC_` prefix. Behind Docker, the backend host is `api`.

Production startup requires a >=32-byte API key and an explicit tenant ID.
Configure explicit CORS origins and terminate HTTPS at a trusted ingress.
The web app is a public, non-persistent demo; it is not an authenticated bank
workspace. Protect an enterprise instance with an identity-aware gateway before
exposing internal documents, reviewer headers or administrative routes.
For reviewer routes, explicitly configure `BANKING_CROSSWALK_ACTOR` and
`BANKING_CROSSWALK_ROLE` on the API service; missing configuration disables
review with 503. This single trusted-service identity is not federated RBAC.

The default store is in memory. Production stateful routes fail with 503 unless
a migrated PostgreSQL repository is connected. `ALLOW_EPHEMERAL_CROSSWALK=true`
is an explicit demonstration override, not a durability feature. Use one process
for memory-backed evaluation. See [PostgreSQL setup](PERSISTENCE.md) for the
optional Compose stack, separate migration/runtime roles and recovery steps.

`/health` indicates process liveness. `/ready` checks the configured database's
connectivity, schema version, tenant-security flags and (in production) runtime
role. API container health checks use `/ready`. Neither endpoint verifies an
external assurance service. No cloud credentials, deployment account or automatic
production deployment is configured in this repository.
