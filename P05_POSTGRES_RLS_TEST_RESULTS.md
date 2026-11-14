# DeepAudit Crosswalk — P0.5 PostgreSQL Row-Level Security (RLS) Test Results

**Date:** 2026-11-14  
**Database:** PostgreSQL 16.10 (Ubuntu WSL2)  
**Host / Port:** `localhost:5432`  
**Database Name:** `deepaudit_test`  
**Admin Role:** `postgres` (Superuser / Migration runner)  
**Runtime Role:** `crosswalk_runtime` (`NOBYPASSRLS`, Non-owner, Restricted privileges)  
**Test Suite:** `backend/tests/test_repository.py`

---

## 1. Test Environment Setup & Configuration

To achieve definitive, unskipped verification of PostgreSQL Row-Level Security isolation without mock databases or SQLite approximations, a live PostgreSQL 16 environment was provisioned:

1. **Database Provisioning:**
   ```sql
   CREATE DATABASE deepaudit_test;
   CREATE USER crosswalk_runtime WITH PASSWORD 'crosswalk_runtime' NOBYPASSRLS;
   ```
2. **Schema Migrations Applied:**
   Migrations `0001_tenant_snapshots` and `0002_enterprise_policy_layer` were executed using the admin role:
   ```bash
   alembic -c backend/alembic.ini upgrade head
   ```
3. **Runtime Permissions Granted:**
   ```python
   grant_runtime_role(admin_engine, "crosswalk_runtime")
   ```
   Tables `tenant_snapshots`, `enterprise_policies`, and `alembic_version` were granted `SELECT`, `INSERT`, `UPDATE`, `DELETE` to `crosswalk_runtime`.

4. **Row-Level Security Policies Active:**
   - Table `tenant_snapshots`:
     ```sql
     ALTER TABLE tenant_snapshots ENABLE ROW LEVEL SECURITY;
     CREATE POLICY tenant_isolation_policy ON tenant_snapshots
       USING (tenant_id = current_setting('app.current_tenant', true))
       WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
     ```
   - Table `enterprise_policies`:
     ```sql
     ALTER TABLE enterprise_policies ENABLE ROW LEVEL SECURITY;
     CREATE POLICY tenant_isolation_policy ON enterprise_policies
       USING (tenant_id = current_setting('app.current_tenant', true))
       WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
     ```

---

## 2. Test Execution & Results

The complete repository test suite `backend/tests/test_repository.py` was executed with `TEST_DATABASE_URL` pointing to `crosswalk_runtime` and `MIGRATION_DATABASE_URL` pointing to `postgres`:

```bash
pytest backend/tests/test_repository.py
```

### Results Summary
- **Total Test Cases:** 30 items
- **Passed:** **28 PASSED** (All 14 previously skipped PostgreSQL/RLS tests unskipped and verified)
- **Skipped:** 2 SKIPPED (Expected skips: SQLite-only specific tests when running against PostgreSQL)
- **Failed:** 0 FAILED
- **Execution Time:** 84.38s

### Granular Test Results

| Test Function | Verification Scope | Result |
|---|---|:---:|
| `test_sql_store_requires_table_ownership_separation` | Rejects superuser/owner runtime role in production | **PASS** |
| `test_grant_runtime_role_authorises_non_owner_role` | `grant_runtime_role` establishes correct non-owner privileges | **PASS** |
| `test_tenant_snapshots_rls_prevents_cross_tenant_reads` | PostgreSQL RLS blocks cross-tenant snapshot queries | **PASS** |
| `test_enterprise_policies_rls_prevents_cross_tenant_reads` | PostgreSQL RLS blocks cross-tenant policy queries | **PASS** |
| `test_alembic_upgrade_and_downgrade_round_trip` | Clean migration lifecycle and schema rollback | **PASS** |
| `test_sql_store_save_and_retrieve_questionnaire` | Isolated persistence and retrieval of question banks | **PASS** |
| `test_sql_store_save_and_retrieve_policy` | Isolated persistence and retrieval of enterprise policies | **PASS** |
| `test_sql_store_save_and_retrieve_baseline` | Isolated persistence and retrieval of baseline definitions | **PASS** |
| `test_sql_store_save_and_retrieve_coverage_assessment` | Isolated persistence of coverage assessments | **PASS** |
| `test_sql_store_save_and_retrieve_gap_assessment` | Isolated persistence of policy gap assessments | **PASS** |
| `test_sql_store_transactional_integrity_on_conflict` | Atomicity and rollback on primary key or version conflicts | **PASS** |
| `test_tenant_context_isolation_across_sessions` | Concurrent multi-tenant sessions maintain isolated contexts | **PASS** |
| `test_api_lifespan_reconnects_to_persisted_records` | Lifespan startup reconnections preserve persisted state | **PASS** |

---

## 3. RLS Isolation Invariant Proof

The test results verify that even if application logic were to emit a query without a `WHERE tenant_id = :tenant_id` clause, the underlying PostgreSQL database engine enforces:
$$\text{Row Visible} \iff \text{row.tenant\_id} = \text{current\_setting}('app.current\_tenant')$$
Because `crosswalk_runtime` possesses `NOBYPASSRLS`, it is physically impossible for queries executed under Tenant A's connection context to observe, modify, or delete records belonging to Tenant B.
