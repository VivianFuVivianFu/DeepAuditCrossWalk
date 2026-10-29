-- Runs only when the optional local PostgreSQL volume is first initialised.
-- psql format(%L) quotes passwords as values, not executable SQL.
\getenv runtime_password CROSSWALK_DATABASE_PASSWORD
SELECT format(
  'CREATE ROLE crosswalk_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'runtime_password'
) \gexec
