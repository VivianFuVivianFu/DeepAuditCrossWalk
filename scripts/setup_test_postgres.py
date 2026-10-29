"""Initialise a disposable CI database. Never run against enterprise data.

Uses a dedicated migration connection; the application test role cannot own
tables or bypass RLS. Credentials here are public disposable CI fixtures.
"""

import os

import sqlalchemy as sa
from banking_crosswalk.database import create_database_engine, upgrade_database

if os.getenv("CI") != "true":
    raise SystemExit("This setup script is restricted to disposable CI environments")

engine = create_database_engine(os.environ["MIGRATION_DATABASE_URL"])
try:
    upgrade_database(engine)
    upgrade_database(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE ROLE crosswalk_ci LOGIN PASSWORD 'test-ci-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
            )
        )
        connection.execute(sa.text("GRANT USAGE ON SCHEMA public TO crosswalk_ci"))
        connection.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO crosswalk_ci"
            )
        )
        connection.execute(
            sa.text("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO crosswalk_ci")
        )
finally:
    engine.dispose()
print("Disposable database migrated; non-owner RLS test role granted.")
