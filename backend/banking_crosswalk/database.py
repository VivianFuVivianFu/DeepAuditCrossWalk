"""Explicit migration CLI: python -m banking_crosswalk.database upgrade|check."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import make_url

SCHEMA_REVISION = "0001_tenant_snapshots"


def create_database_engine(url: str):
    parsed = make_url(url)
    if parsed.drivername in {"postgres", "postgresql"}:
        parsed = parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername not in {"postgresql+psycopg", "sqlite"}:
        raise ValueError("Use a PostgreSQL psycopg URL (SQLite is for tests only)")
    options = {"pool_pre_ping": True, "hide_parameters": True}
    if parsed.get_backend_name() == "postgresql":
        options["connect_args"] = {
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=5000",
        }
        options["pool_size"] = 5
        options["max_overflow"] = 5
        options["pool_timeout"] = 5
    else:
        options["connect_args"] = {"check_same_thread": False}
    engine = sa.create_engine(parsed, **options)
    if parsed.get_backend_name() == "sqlite":

        @sa.event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def migration_config(connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["connection"] = connection
    return config


def upgrade_database(engine) -> None:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            # Serialise migration runners, without exposing URL/credentials.
            connection.execute(sa.text("SELECT pg_advisory_xact_lock(742006291)"))
        command.upgrade(migration_config(connection), "head")


def check_schema(connection) -> None:
    revisions = MigrationContext.configure(connection).get_current_heads()
    if revisions != (SCHEMA_REVISION,):
        raise RuntimeError(
            "Database schema is not current; run the migration upgrade command"
        )


def grant_runtime_role(engine, role: str) -> None:
    """Grant data permissions only, quoting the operator-supplied identifier."""
    from .schema import TENANT_TABLES

    if engine.dialect.name != "postgresql" or not role.strip():
        raise ValueError("A PostgreSQL runtime role is required")
    quoted = engine.dialect.identifier_preparer.quote_identifier(role)
    with engine.begin() as connection:
        connection.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {quoted}"))
        for name in TENANT_TABLES:
            permissions = (
                "SELECT, INSERT" if name == "audit_events" else "SELECT, INSERT, UPDATE"
            )
            connection.execute(
                sa.text(f'GRANT {permissions} ON TABLE public."{name}" TO {quoted}')
            )
        connection.execute(
            sa.text(f"GRANT SELECT ON TABLE public.alembic_version TO {quoted}")
        )
        connection.execute(
            sa.text(
                f"GRANT USAGE ON SEQUENCE public.audit_events_event_id_seq TO {quoted}"
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["upgrade", "check"])
    parser.add_argument(
        "--runtime-role",
        help="After upgrade, grant only data permissions to an existing PostgreSQL role",
    )
    args = parser.parse_args()
    engine = None
    try:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL is required")
        engine = create_database_engine(url)
        if args.action == "upgrade":
            upgrade_database(engine)
            if args.runtime_role:
                grant_runtime_role(engine, args.runtime_role)
        with engine.connect() as connection:
            check_schema(connection)
    except Exception:
        # Driver errors may contain hostnames or credentials. Operator checks
        # are deliberately concise; no raw URL or SQL parameters are printed.
        parser.exit(
            1,
            "Database operation failed. Check connectivity, migration role and schema version.\n",
        )
    finally:
        if engine is not None:
            engine.dispose()
    print("Database schema is current.")


if __name__ == "__main__":
    main()
