# E4.1 Regulatory Correction Changelog

**Release:** `AU-BANKING-REG-PACK-0.1` version `0.2.0` (`library_release`: `2026.11-au-banking-v0.2.0`) | `AU-BANKING-OBLIGATION-CONTROL-MAPPINGS-1.1` version `1.1.0`  
**Branch:** `fix/e41-regulatory-accuracy-remediation`  
**Governance Rule:** All corrected and newly split library items remain in `review_status="proposed"` / `reviewer_status="proposed"` (`human_approved=0`). Human legal and compliance sign-off is required before promoting any item to `approved`.

## 1. Summary of Changes vs. E4 Baseline (`0.1.0` -> `0.2.0`)

| Dimension | E4 Baseline (`0.1.0`) | E4.1 Remediated (`0.2.0`) | Reason |
|---|---:|---:|---|
| Regulatory sources | 17 | 17 | Metadata, FRL instrument IDs, URLs, and notes corrected on `AU-PRIVACY-ACT`, `APRA-CPS220`, `ASIC-RG271`, `EU-AI-ACT`. |
| Active atomic obligations | 45 | 46 | Separated standalone `EU-AIA-ART50-TRANSPARENCY` (effective `2026-08-02`) from `EU-AIA-ART26-27-DEPLOYER-CREDIT` (deferred to `2027-12-02`). |
| Unified controls | 33 | 33 | Refined control definitions/objectives for `CTRL-PRIV-SECURITY-RETENTION` and `CTRL-EU-HIGH-RISK`. |
| Obligation-control mappings | 55 | 55 | Removed duplicate `MAP-CROSS-007` (`ISO23894-AI-RISK-PROCESS -> CTRL-RISK-FRAMEWORK`), preserved provenance in `MAP-PRIMARY-044` and `superseded_mapping_ids`, added `MAP-PRIMARY-046` (`EU-AIA-ART50-TRANSPARENCY`). |
| Duplicate `(obligation_id, control_id)` pairs | 1 | 0 | Deduplicated in data and enforced as a hard validation failure in `validation.py`. |
| `non_equivalent` mappings with `mapped_facets` | 3 | 0 | Cleared `mapped_facets` on `MAP-CROSS-003`, `004`, `006` and blocked non-equivalent leakage in runtime and validation. |
| Broad/guidance `full` mappings flagged | 9 | 4 | Reclassified `MAP-PRIMARY-023/027/028/030/031` cleanly to `related` or `partial`. |
| P0 completeness gap candidates | 0 registered | 5 candidate rows | Captured `GAP-FAR-2023`, `GAP-CORP-912A-DDO-BREACH` (3 obligations), and `GAP-ASIC-2022-205` in `E41_CANDIDATE_REQUIREMENTS_REGISTER.csv` (`imported_to_runtime=false`). |

## 2. P0 Source & Obligation Remediations

1. **`AU-PRIVACY-ACT` & `AU-PRIV-APP11-SECURITY` (Privacy Act 1988 Sch 1 APP 11.1–11.3):**
   - Removed inaccurate `"APP 11.3 retention commentary"` wording.
   - Updated provision, citation, and effective date (`2024-12-11`) to reflect *Privacy and Other Legislation Amendment Act 2024* (`C2024A00128`), which inserted APP 11.3 clarifying that "reasonable steps" under APP 11.1 and APP 11.2 explicitly include **technical and organisational measures**.
   - Separated security safeguards (`technical_security_measures_implemented`, `organisational_security_measures_implemented`) from APP 11.2 lifecycle disposal (`retention_schedule_applied`, `destruction_or_deidentification_verified`).
   - Updated `CTRL-PRIV-SECURITY-RETENTION` and `MAP-CROSS-001` accordingly.

2. **`ASIC-RG271`, `AU-ASIC-RG271-COMPLAINT`, & `AU-ASIC-RG271-SYSTEMIC` (ASIC RG 271 & Instruments 2020/98 vs 2022/205):**
   - Distinguished enforceable paragraphs designated by *ASIC Corporations, Credit and Superannuation (Internal Dispute Resolution) Instrument 2020/98* (e.g., `271.27`, `271.56`, `271.118–271.120`, `271.165`) from non-enforceable acknowledgement guidance (`271.51`).
   - Removed erroneous reference to `271.116` (credit hardship enforcement postponement) and `271.166–271.182` as the legal source of mandatory ASIC IDR data reporting.
   - Separated mandatory semi-annual IDR data reporting under *ASIC Corporations (Internal Dispute Resolution Data Reporting) Instrument 2022/205* (`F2022L00430`, as amended by `2023/282` and `2026/48`) into `E41_CANDIDATE_REQUIREMENTS_REGISTER.csv` (`CAND-ASIC-2022-205-01`).

3. **`APRA-CPS220`, `AU-APRA-CPS220-RMF`, & `AU-APRA-CPS220-REVIEW` (APRA CPS 220 Risk Management):**
   - Removed erroneous FRL identifiers `F2017L00695` (Disability Services Guidelines) and `F2014L01822` (National Health determination).
   - Replaced with verified current FRL instrument **`F2019L00669`** (*Banking, Insurance, Life Insurance and Health Insurance (prudential standard) determination No. 1 of 2019*, effective `2019-07-01`, URL `https://www.legislation.gov.au/F2019L00669/latest/details`), while preserving `APRA-CPS220-2015-01` (`2015-01-01` initial ADI commencement) in `historical_versions`.
   - Corrected `AU-APRA-CPS220-REVIEW` paragraph citation from `paras 37–47, 51` to **`paras 38–51 & Attachment A`** (note para `37` covers policy revision-date monitoring; paras `38–43` establish the designated Risk Management Function; `45` mandates annual audit review; `46–48` mandate 3-yearly comprehensive independent review; `49–51 & Attachment A` cover the annual Board Risk Management Declaration).

4. **`EU-AI-ACT`, `EU-AIA-ART2-HIGH-RISK`, `EU-AIA-ART26-27-DEPLOYER-CREDIT`, & `EU-AIA-ART50-TRANSPARENCY`:**
   - Updated source `EU-AI-ACT` to reflect **Regulation (EU) 2026/1744** (`CELEX:32026R1744`, OJ L `2026-07-24`) amending Article 113 of Regulation (EU) 2024/1689 (`CELEX:32024R1689`):
     - Chapters I & II (Articles 4 & 5): `2025-02-02` (unchanged)
     - Chapter V (GPAI): `2025-08-02` (unchanged)
     - Article 50 transparency (`EU-AIA-ART50-TRANSPARENCY`): `2026-08-02` (unchanged, split out cleanly with `applicability_key="eu_ai_act_transparency"` and `MAP-PRIMARY-046`)
     - Annex III stand-alone high-risk systems (`EU-AIA-ART2-HIGH-RISK`, `EU-AIA-ART26-27-DEPLOYER-CREDIT`): deferred to **`2027-12-02`**
     - Annex I embedded product high-risk systems: deferred to **`2028-08-02`**
   - Decomposed composite facet `deployer_human_oversight_and_6month_log_retention` into `deployer_human_oversight_assigned` and `automatic_logs_retained_6months` on `EU-AIA-ART26-27-DEPLOYER-CREDIT`, eliminating cross-mapping over-claims on `CTRL-HUMAN-OVERSIGHT` (`MAP-CROSS-005`).

## 3. Runtime & Validation Engine Hardening

- **`backend/banking_crosswalk/applicability.py`:** `_eu` now evaluates `obligation.effective_from` against `use_case.as_of_date` and respects `eu_operator_role == "none"`; added `_eu_transparency` (`"eu_ai_act_transparency"` in `RULES`) and updated `_eu_deployer_high_risk` for Regulation (EU) 2026/1744 timelines and role/credit context.
- **`backend/banking_crosswalk/reconciliation.py` & `semantic_reconciliation.py`:** Excluded `MappingRelationship.NON_EQUIVALENT` / `NOT_EQUIVALENT` when building control-to-obligation indexes and clause-level facet/control sets so non-equivalent links can never leak coverage or candidate retrieval.
- **`backend/banking_crosswalk/validation.py`:** Added `"EU-AIA-ART50-TRANSPARENCY"` to `ALLOWED_PHASED_CHILD_DATES` and upgraded duplicate `(obligation_id, control_id)` pairs and `non_equivalent` mappings with populated `mapped_facets` from warning diagnostics to hard structural validation failures.
- **`backend/banking_crosswalk/llm/providers.py`:** Updated `DeterministicMockSemanticProvider` facet semantic cues for split APP 11.3 security facets (`technical_security_measures_implemented`, `organisational_security_measures_implemented`) and EU AI Act Art 26/27/50 facets while retaining backward compatibility.

## 4. Packaging & Versioning Notes

- Bumped `regulatory_pack.v0.1.json` `version` from `"0.1.0"` to **`"0.2.0"`** (`library_release`: `"2026.11-au-banking-v0.2.0"`) while keeping `pack_id="AU-BANKING-REG-PACK-0.1"` so existing Reconciliation / Effective Baseline version-staleness guards trigger cleanly.
- Bumped `OBLIGATION_CONTROL_MAPPINGS.json` `version` to **`"1.1.0"`** and recorded `superseded_mapping_ids: ["MAP-CROSS-007"]`.
- Regenerated root and `backend/banking_crosswalk/data/` deliverables via `scripts/build_regulatory_library.py` with byte-for-byte parity verified.
