# Verification record

## PostgreSQL milestone — 29 October 2026

Local Python 3.13 checks passed: 52 backend tests (14 skips at the milestone
commit), 8 frontend tests, TypeScript, Ruff, package build, dependency audit,
secret scan and both Compose configurations. The skipped tests require real
PostgreSQL or the optional source workbook; two are PostgreSQL-only checks on
the SQLite adapter. They are not recorded as passing local database tests.

[Milestone CI run](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/40800366124)
at commit `13f09a5` completed successfully, including:

- Python 3.11 and 3.13 regression, package builds and dependency audits.
- Real PostgreSQL 17 and 18 storage contracts: restart/reconnect, tenant
  isolation, forced RLS without application predicates, stale-review conflicts,
  transaction rollback and append-only audit enforcement.
- Actual `pg_dump`/`pg_restore` to a separate database for both PostgreSQL
  versions; restored assessment, closure evidence, mapping and audit content
  hashes matched, and cross-tenant reads were denied.
- Both Docker image builds and live web/API smoke workflows; 2 Chromium browser
  tests; the optional PostgreSQL Compose deployment in production mode;
  evidence-gated gap closure through HTTP; and API container restart with
  unchanged report/audit hashes and enforced tenant binding.
- [CodeQL](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/runs/40800366146)
  completed successfully.

A follow-up adds an explicit migration-superuser rejection test (skipped locally
without its disposable PostgreSQL URL), and forwards external `DATABASE_URL`
configuration through the base Compose file. The same CI matrix verifies it.

Local Docker remains unavailable; container/database results above come from
Linux CI, not a claimed deployment on this workstation. SSO/RBAC, expert mapping
validation and an enterprise operational recovery service remain incomplete.

## Standalone baseline — 28 October 2026

This record describes the standalone repository, not tests from the original
DeepAudit application. No source workbook or private bank policy is a test dependency.

Local checks run in a new isolated Python 3.13 environment and Node.js 22.20:

Latest local results: **38 backend tests passed, 1 optional workbook test skipped;
8 frontend tests passed; 2 browser tests passed; both live smoke workflows passed.**
Type checking, production build and dependency/security scans also passed.

- Backend regression suite, including isolated tenant state, four-state
  applicability, approved mapping gates, gap closure, exact currency boundaries,
  XLSX archive/XML safeguards, PDF/DOCX parsing and the standalone app.
- Frontend contract/gateway tests, TypeScript checking and Next.js production build.
- Two Playwright browser checks using a real local web server and separate
  FastAPI process: coverage/policy analysis with JSON download, and a mobile
  layout retaining undetermined facts.
- Two live smoke requests traversing the web proxy to the API, verifying
  assessment IDs, source hashes, undetermined facts and absence of automatic approval.
- Python dependency audit, npm audit and publishable-tree secret scan.
- Python source distribution/wheel build, with embedded JSON asset checks.
- Docker Compose configuration validation.

The optional real AIAF workbook acceptance test skips when the operator's own
authorised workbook is absent. This is expected in a public clone; synthetic
XLSX import tests still run.

The local Docker daemon was unavailable. Linux image builds, non-root health
checks and live container/browser smoke tests are therefore configured as a
separate CI job; local Compose syntax validation is not recorded as an image
build or deployment success.

The first Linux container job built both images, passed their health checks,
and passed both live smoke workflows. Its browser-install step exposed an
`ubuntu-latest` change to Ubuntu 26.04, unsupported by the pinned Playwright.
Runners are now explicitly pinned to supported Ubuntu 24.04.

CI additionally checks Python 3.11/3.13 and Node.js 24. This repository has no
automatic cloud deployment. The project remains an experimental MVP while
durable storage, identity integration and expert mapping validation are pending.
