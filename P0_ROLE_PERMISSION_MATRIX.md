# DeepAudit Crosswalk — P0 Role & Permission Matrix

## 1. Role Definitions

The platform defines four explicit, hierarchically ordered roles for tenant workspace operations:

| Role | Hierarchy Level | Primary Intent | Australian FS Persona Example |
|---|:---:|---|---|
| **`viewer`** | 1 | Read-only inspection of questionnaires, policies, baselines, and assessment reports. | External Auditor, Executive Oversight, Independent Model Risk Observer |
| **`analyst`** (`contributor`) | 2 | Import questionnaires and internal policies, configure context, and run coverage assessments. | AI Governance Analyst, Technical Compliance Contributor, Model Developer |
| **`reviewer`** | 3 | Review and approve/reject extracted clauses, review and approve/reject control mappings, compile versioned baselines. | Senior Compliance Officer, Legal Counsel, Risk Committee Delegate |
| **`admin`** | 4 | Complete tenant workspace administration, including deleting policies within the authorized tenant. | Tenant Workspace Administrator, Head of Model Risk & Compliance |

---

## 2. Granular Permission Mapping

| Permission String | Description | `viewer` | `analyst` | `reviewer` | `admin` |
|---|---|:---:|:---:|:---:|:---:|
| `questionnaire:read` | List and view imported tenant questionnaires | ✅ | ✅ | ✅ | ✅ |
| `questionnaire:upload` | Import new questionnaires (.xlsx) | ❌ | ✅ | ✅ | ✅ |
| `policy:read` | List and view imported internal enterprise policies | ✅ | ✅ | ✅ | ✅ |
| `policy:upload` | Import new policy documents (.pdf, .docx, .txt, .md) | ❌ | ✅ | ✅ | ✅ |
| `policy:delete` | Delete an imported enterprise policy | ❌ | ❌ | ❌ | ✅ |
| `clause:read` | List extracted candidate clauses from policies | ✅ | ✅ | ✅ | ✅ |
| `clause:review` | Approve or reject candidate enterprise clauses | ❌ | ❌ | ✅ | ✅ |
| `mapping:read` | Inspect suggested control mappings | ✅ | ✅ | ✅ | ✅ |
| `mapping:review` | Independently approve or reject clause control mappings | ❌ | ❌ | ✅ | ✅ |
| `baseline:read` | List and inspect compiled Enterprise Baselines | ✅ | ✅ | ✅ | ✅ |
| `baseline:create` | Compile approved clauses and controls into an Enterprise Baseline | ❌ | ❌ | ✅ | ✅ |
| `assessment:read` | View assessment results, metrics, gap reports, and JSON export | ✅ | ✅ | ✅ | ✅ |
| `assessment:run` | Run Regulatory-Only or Enterprise-Enhanced coverage assessments | ❌ | ✅ | ✅ | ✅ |

---

## 3. Gateway Action Enforcement Mapping

Every request to `/api/workspace` maps to a required permission checked by `hasPermission(ctx, requiredPermission)`:

| Action Name | Target Endpoint | HTTP Method | Required Permission | Denied Role Response |
|---|---|:---:|---|:---:|
| `list_questionnaires` | `/v1/questionnaires` | `GET` | `questionnaire:read` | `401 Unauthorized` |
| `get_questionnaire` | `/v1/questionnaires/{id}` | `GET` | `questionnaire:read` | `401 Unauthorized` |
| `import_questionnaire` | `/v1/questionnaires/import` | `POST` | `questionnaire:upload` | `403 Forbidden` (`viewer`) |
| `list_policies` | `/v1/enterprise/policies` | `GET` | `policy:read` | `401 Unauthorized` |
| `get_policy` | `/v1/enterprise/policies/{id}` | `GET` | `policy:read` | `401 Unauthorized` |
| `import_policy_file` | `/v1/enterprise/policies/import-file` | `POST` | `policy:upload` | `403 Forbidden` (`viewer`) |
| `import_policy_text` | `/v1/enterprise/policies/import` | `POST` | `policy:upload` | `403 Forbidden` (`viewer`) |
| `delete_policy` | `/v1/enterprise/policies/{id}` | `DELETE` | `policy:delete` | `403 Forbidden` (`viewer`, `analyst`, `reviewer`) |
| `list_clauses` / `get_policy_clauses` | `/v1/enterprise/policies/{id}/clauses` | `GET` | `clause:read` | `401 Unauthorized` |
| `review_clause` | `/v1/enterprise/clauses/{id}/review` | `PUT` | `clause:review` | `403 Forbidden` (`viewer`, `analyst`) |
| `review_clause_mapping` | `/v1/enterprise/clauses/{id}/mappings/{mid}/review` | `PUT` | `mapping:review` | `403 Forbidden` (`viewer`, `analyst`) |
| `create_baseline` | `/v1/enterprise/baselines` | `POST` | `baseline:create` | `403 Forbidden` (`viewer`, `analyst`) |
| `list_baselines` | `/v1/enterprise/baselines` | `GET` | `baseline:read` | `401 Unauthorized` |
| `get_baseline` | `/v1/enterprise/baselines/{id}` | `GET` | `baseline:read` | `401 Unauthorized` |
| `assess_coverage` / `run_coverage_assessment` | `/v1/assessments/coverage` | `POST` | `assessment:run` | `403 Forbidden` (`viewer`) |
| `get_report` | `/v1/assessments/{id}/report` | `GET` | `assessment:read` | `401 Unauthorized` |
| `get_gaps` | `/v1/assessments/{id}/gaps` | `GET` | `assessment:read` | `401 Unauthorized` |

---

## 4. Invariants
1. **Analyst Approval Denial**: Analysts can upload documents and run assessments, but cannot approve clauses or mappings.
2. **Independent Clause & Mapping Approval**: Clause approval does not grant mapping approval, and mapping approval does not grant clause approval.
3. **Admin Exclusivity on Policy Deletion**: Only tenant administrators have permission to delete enterprise policy records.
4. **Tenant Isolation**: A user possessing `admin` in Tenant A has zero access or permissions in Tenant B unless explicitly assigned membership in Tenant B.
