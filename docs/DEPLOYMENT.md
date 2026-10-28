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

The current store is in memory. Production stateful routes fail with 503.
`ALLOW_EPHEMERAL_CROSSWALK=true` is an explicit demonstration override, not a
durability feature. Do not run multiple replicas/processes for a local stateful
evaluation. PostgreSQL persistence and migrations are future work.

Health endpoints indicate process health, not readiness of a database or external
assurance service. No cloud credentials, deployment account or automatic
production deployment is configured in this repository.
