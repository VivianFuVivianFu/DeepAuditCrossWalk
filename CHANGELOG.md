# Changelog

## Unreleased — 2026-10-29

- Add optional PostgreSQL snapshots, explicit Alembic migrations, forced tenant
  row security, non-owner runtime-role checks and separate storage readiness.
- Commit assessment gaps and detailed review audit events transactionally;
  reject stale gap revisions and blank closure evidence references.
- Add an optional persistent Compose stack, restart/rollback regressions,
  PostgreSQL 17/18 integration checks and a synthetic backup/restore drill.

## 0.1.0 — 2026-10-28

- Extract the Crosswalk engine into an independent repository with a new Git history.
- Add standalone API, web demo, packaging, Docker Compose and CI.
- Bundle original synthetic questions instead of distributing the source AIAF catalogue.
- Preserve rules, reviewer gates, version traceability and tenant-scoped local workflows.
- Add bounded PDF/DOCX policy import and exact multi-threshold questionnaire checks.
- Document production persistence and identity integration boundaries.
- Enforce patched pip/setuptools tooling in CI, isolated builds and Docker images.
