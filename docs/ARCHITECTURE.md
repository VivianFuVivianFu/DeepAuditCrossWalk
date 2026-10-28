# Architecture and trust boundaries

This repository is a standalone product. The UI in `web/` calls its own Next.js
server proxy, which forwards an allowlisted, non-persistent payload to the
FastAPI service in `backend/banking_crosswalk/app.py`. API credentials and tenant
configuration are server-only environment variables. Browser-supplied tenant,
actor, role, persistent IDs and review decisions are never forwarded by this proxy.

The two engines share models, applicability rules and a versioned regulatory
pack. Applicability is four-state. The coverage engine records required control
facets, candidate question IDs, approval status, source references and missing
facets. Only approved mappings for the selected questionnaire hash and pack
version count as confirmed coverage. Policy extraction retains mandatory clauses,
AUD thresholds and potential embedded instructions as inert source text.

The workbook importer reads formula and cached-value views without saving the
source. Archive, XML and worksheet limits precede openpyxl object creation.
Imported question IDs, provenance and routing remain separate from overlays.

All uploaded content is untrusted. Request bytes, archive expansion, PDF streams,
pages, extracted text and table dimensions are bounded. Strings are text, not
server paths. There are no document-triggered shell or model calls. Resource
caps reduce risk but do not replace process isolation and memory/CPU limits for
hostile enterprise uploads.

`TenantStore` is an in-memory repository, protected by a process lock. It is a
local-evaluation implementation, not a distributed database. Production disables
stateful operations by default; inline demo analyses remain stateless. The
`persisted` terminology in API descriptions refers to this local repository,
not durable storage. A PostgreSQL implementation, migrations, durable audit log,
backup/restore drills and authenticated identity integration are required before
bank production deployment.
