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

The ASGI lifespan selects `TenantStore` for in-memory local evaluation or
`SQLTenantStore` when `DATABASE_URL` is configured. Configured storage errors
never fall back to memory. The SQL repository stores validated domain snapshots
in tenant-keyed relational envelopes; gap ownership has a composite foreign key.
Assessments, their gaps and their creation event commit together. Review changes
and their complete audit snapshots also commit together. Gap revisions use a
compare-and-update condition so stale concurrent reviews return 409.

PostgreSQL tables enforce row-level security with transaction-local tenant
context, in addition to explicit tenant predicates. Production rejects database
owners, superusers and BYPASSRLS roles. An audit trigger rejects UPDATE, DELETE
and TRUNCATE; database administrators can still alter the database and require
separate operational oversight. Schema changes run through explicit Alembic
migrations, never automatic startup DDL. See [persistence](PERSISTENCE.md).

Federated identity, tenant membership, independently controlled audit retention
and operational recovery procedures remain prerequisites for bank deployment.
Database tenant context is derived from the service gateway; it does not
authenticate end users or replace authorisation at that gateway.
