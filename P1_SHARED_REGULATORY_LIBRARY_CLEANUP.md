# P1 Shared Regulatory Library Cleanup Report

## Overview

This report details the inventory reconciliation and active regulatory catalog cleanup executed under **Prompt P1 Safety Fix A**.

The Shared Regulatory Library represents the platform-maintained legal and regulatory foundations governing Australian Financial Services AI deployments. To preserve regulatory integrity, all synthetic, enterprise-specific requirements have been removed from the active shared library.

---

## Before & After Regulatory Asset Inventory

| Asset Category | Pre-Cleanup Count (PR #22) | Post-Cleanup Count (P1 Safety Fix A) | Net Delta | Notes |
|:---|:---|:---|:---|:---|
| **Sources** (`REGULATORY_SOURCE_REGISTER.csv`) | 18 | **17** | -1 | Removed `ENTERPRISE-AI-STD` |
| **Atomic Obligations** (`ATOMIC_OBLIGATION_CATALOGUE.json`) | 46 | **45** | -1 | Removed `ENT-AI-DELEGATED-APPROVAL` |
| **Unified Controls** (`UNIFIED_CONTROL_LIBRARY.json`) | 33 | **33** | 0 | Preserved all canonical controls |
| **Obligation Mappings** (`OBLIGATION_CONTROL_MAPPINGS.json`) | 56 | **55** | -1 | Removed mapping `MAP-CROSS-011` |
| **Regulatory Pack Version** | `0.1.0` | `0.1.0` | 0 | Checksum recalculated |

---

## Detailed Modifications

### 1. Source Register (`REGULATORY_SOURCE_REGISTER.csv`)
* **Removed Entry:**
  ```csv
  ENTERPRISE-AI-STD,Enterprise AI Standard (Internal Policy Example),Enterprise Architecture,enterprise,internal_standard,draft,2024-06-01,Internal risk management guideline,enterprise,low,https://internal.example.bank/ai-standard,1.0
  ```
* **Justification:** An internal bank policy standard is tenant-specific; it does not belong in the universal shared regulatory library distributed to all tenants.

### 2. Atomic Obligation Catalogue (`ATOMIC_OBLIGATION_CATALOGUE.json` & `regulatory_pack.v0.1.json`)
* **Removed Obligation:** `ENT-AI-DELEGATED-APPROVAL`
  - Authority: `enterprise`
  - Classification: `enterprise_defined_control`
  - Summary: Internal delegated authority threshold requiring human approval.
* **Justification:** Enterprise policies vary widely by institution and product line (e.g. credit approvals, transaction monitoring, customer redress). Embedding a synthetic AUD threshold in the shared library contaminated statutory applicability checks.

### 3. Obligation-Control Crosswalk Mappings (`OBLIGATION_CONTROL_MAPPINGS.json`)
* **Removed Mapping:** `MAP-CROSS-011`
  - Source Obligation: `ENT-AI-DELEGATED-APPROVAL`
  - Target Control: `CTRL-DELEGATED-AUTHORITY-THRESHOLD`
* **Justification:** The mapping linked the removed synthetic obligation to the canonical control. With the obligation removed, this mapping is deprecated and purged.

### 4. Retention and Self-Containment of Canonical Controls (`UNIFIED_CONTROL_LIBRARY.json`)
Two controls associated with human oversight and financial thresholds were evaluated for retention:
* **`CTRL-HUMAN-OVERSIGHT`**: Retained. Provides generic architectural requirements for human-in-the-loop, override, and governance oversight.
* **`CTRL-DELEGATED-AUTHORITY-THRESHOLD`**: Retained. Serves as a canonical control target against which tenant-specific approved policies (e.g. delegated credit thresholds) can be evaluated during Enterprise-Enhanced assessments.

To ensure `CTRL-DELEGATED-AUTHORITY-THRESHOLD` is fully self-contained without depending on any synthetic obligation:
- Added explicit `default_facets`:
  - `delegated_authority_threshold_defined`
  - `human_approval_required`
  - `pre_execution_block`
- Added explicit `default_evidence`:
  - `Delegated authority schedule signed by Board Risk Committee`
  - `System configuration enforcing financial authority limits prior to transaction release`
- Updated `scripts/build_regulatory_library.py` to fall back to `default_facets` and `default_evidence` when primary obligations are empty.

---

## Active Regulatory Catalog Integrity

The regulatory pack generation script (`scripts/build_regulatory_library.py`) was re-executed. Both root catalog files and backend pack files were synchronized:

```
Root Catalog Files:
- ATOMIC_OBLIGATION_CATALOGUE.json
- OBLIGATION_CONTROL_MAPPINGS.json
- REGULATORY_SOURCE_REGISTER.csv
- UNIFIED_CONTROL_LIBRARY.json

Backend Pack Files:
- backend/banking_crosswalk/data/atomic_obligation_catalogue.json
- backend/banking_crosswalk/data/obligation_control_mappings.json
- backend/banking_crosswalk/data/regulatory_pack.v0.1.json
- backend/banking_crosswalk/data/regulatory_source_register.csv
- backend/banking_crosswalk/data/unified_control_library.json
```

All 9 automated integrity checks in `backend/banking_crosswalk/validation.py` pass with zero defects detected.
