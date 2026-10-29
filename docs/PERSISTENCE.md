# PostgreSQL persistence and recovery

The default local workspace uses memory. Set `DATABASE_URL` to select the
PostgreSQL repository at API startup. Missing dependencies, failed connectivity,
unsafe production roles or missing migrations stop startup; there is no memory
fallback. SQLite is a test adapter and is rejected in production.

## Local persistent evaluation

1. Copy `.env.example` to `.env`.
2. Generate **two different** URL-safe passwords, for example by running
   `python -c "import secrets; print(secrets.token_urlsafe(32))"` twice. Set
   `POSTGRES_PASSWORD` and `CROSSWALK_DATABASE_PASSWORD` in the ignored `.env`.
   The supplied Compose overlay builds URLs from these values, so use URL-safe
   characters. A manually configured URL must percent-encode reserved characters.
3. Run:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml up --build -d --wait
```

The database has no host port. A one-shot migration service owns schema changes;
the API connects as `crosswalk_app`, which owns no tables and cannot bypass row
security. Data survives API restarts and `docker compose down` in the named
volume. Changing `.env` passwords does not rotate an existing database role:
the initialisation script runs only when the volume is first created. Use an
authorised database password-rotation procedure for an existing installation.

This stack remains a local evaluation deployment. Keep the API behind a trusted
identity-aware gateway before using internal data or reviewer routes.

## External PostgreSQL

Install `pip install -e './backend[postgres]'`. Provision an existing database
and separate migration and application roles. The runtime role must be LOGIN,
NOSUPERUSER, NOCREATEDB, NOCREATEROLE and NOBYPASSRLS, and must not own tables or
inherit privileged roles. Keep migration credentials out of the API container.
The current migration targets the default `public` schema.

In the **migration shell**, export `DATABASE_URL` using the schema-owner
credentials, then run:

```bash
python -m banking_crosswalk.database upgrade --runtime-role crosswalk_app
```

The command does not create a role or database. It applies Alembic revisions
under a PostgreSQL advisory lock and grants the existing runtime role only
data access, sequence usage and schema-version read access. Audit events receive
SELECT/INSERT only. A failed upgrade exits non-zero without printing connection
credentials. Back up the database and review migrations before an upgrade.

In the **API shell**, export `DATABASE_URL` with the runtime credentials and
start Uvicorn. Use a normal PostgreSQL connection or session pooling; this
repository has not qualified transaction-mode poolers. Require TLS with
certificate verification for remote deployments, using the appropriate libpq
URL parameters and trusted CA configuration. `/ready` returns 503 when storage
checks fail; `/health` remains a process-liveness endpoint.

## Data and concurrency guarantees

- Complete Pydantic snapshots retain questionnaire hashes, pack versions,
  selected questions, control facets, evidence references and review identities.
- Tenant IDs participate in primary keys and gap-to-assessment foreign keys.
  Every SQL operation uses a tenant predicate; PostgreSQL also applies forced
  RLS using `set_config(..., true)` scoped to the transaction. A connection
  returned to the pool carries no authorisation for the previous tenant.
- Assessment creation and all its gaps/event are one transaction. Gap and mapping
  reviews commit with their detailed audit events. A failed audit insert rolls
  the review back. Mapping audit events preserve superseded approval/rejection
  reasons even though the current mapping row holds the latest decision.
- Send `expected_revision` from the gap response when reviewing a gap. Stale
  revisions return 409. Concurrent server reads also use compare-and-update
  protection. Refresh and reassess the decision before retrying.
- Closure still requires validated remediation, scope recheck, approval,
  nonblank evidence references and a retest reference. These are reviewer
  attestations; the repository does not verify that an external artifact exists.

Audit events reject UPDATE, DELETE and TRUNCATE through both limited grants and
a PostgreSQL trigger. This is not cryptographic immutability: database owners can
change triggers or restore older backups. Restrict database administration and
export audit evidence to separately controlled retention storage where required.

## Backup and restore

Use your managed database's encrypted backups/PITR or PostgreSQL `pg_dump -Fc`
and `pg_restore` into a **separate, empty recovery database**. Provision the
expected owner/runtime roles before restoring an owner-preserving dump. Use
libpq service/password files or a secret manager; avoid putting passwords into
shell history. Backups contain policy text and reviewer data and must be
protected like the database itself.

After restore, run the migration `check` command, connect with the non-owner
runtime role, call `/ready`, retrieve known assessment reports and verify source
hashes, reviewed gaps, evidence references and audit history. Test that another
tenant cannot retrieve those assessment IDs. Do not overwrite the live database
as a recovery test. Define and exercise recovery objectives for the deployment.

CI runs this process against PostgreSQL 17 and 18 using disposable synthetic
data: it seeds an evidence-gated closure and an approved mapping, creates a
custom-format dump, restores to another database, compares content hashes and
checks tenant isolation using the runtime role. That drill demonstrates the
repository's round trip; it is not a bank's operational backup service.

Implementation references: [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html),
[SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/core/connections.html),
and [Alembic migration commands](https://alembic.sqlalchemy.org/en/latest/api/commands.html).
