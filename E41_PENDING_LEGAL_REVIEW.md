# E4.1 Items Pending Human Legal & Compliance Sign-Off

E4.1 repaired P0 technical citations, dates, duplicate pairs, non-equivalence leakage guards, and over-broad `full` labels while preserving the non-negotiable invariant: **zero regulatory sources, obligations, controls, mappings, or candidates have been human-approved (`human_approved = 0`)**.

## 1. Active Runtime Library Review Queue (`review_status="proposed"`)

Full item-by-item queue is tracked in `E4_LEGAL_REVIEW_REGISTER.csv` (126 rows: `17` sources, `46` obligations, `55` active mappings, `8` completeness gap entries).

| Category | Remaining Items Requiring Human Sign-Off | Key Legal Judgment / Action Needed |
|---|---|---|
| **APRA CPS 230 / CPS 234 Citation Boundary Notes (E4 carryover)** | `AU-APRA-CPS230-OPS`, `AU-APRA-CPS230-BCP`, `AU-APRA-CPS234-INCIDENT` | Clarify initial 1 Jul 2025 CPS 230 SFI commencement vs 1 Jul 2026 revised standard, and confirm exact CPS 234 para 32–34 vs 35–36 boundary with APRA Prudential Specialist. (Retained as open `needs_correction` in `E4_LEGAL_REVIEW_REGISTER.csv` so lifecycle governance tests continue gating premature approval.) |
| **EU AI Act Extraterritorial Nexus & Classification** | `EU-AI-ACT`, `EU-AIA-ART2-HIGH-RISK`, `EU-AIA-ART4-5-PROHIBITED-LITERACY`, `EU-AIA-ART26-27-DEPLOYER-CREDIT`, `EU-AIA-ART50-TRANSPARENCY` | Confirm Article 2(1)(c) `"output used in the Union"` triggers, operator role classifications, and Article 50 legacy GenAI transitional rules before any production sign-off. |
| **Privacy Act Interpretive Boundaries** | `AU-PRIV-APP1.7-AUTOMATED`, `AU-PRIV-APP3-COLLECT`, `AU-PRIV-APP6-USE`, `AU-PRIV-APP8-CROSSBORDER` | Legal sign-off on automated decision-making readiness (10 Dec 2026), inferred PI solicitation boundary, LLM training secondary-use basis, and OAIC Ch 8 offshore use-vs-disclosure criteria. |
| **Remaining Shared-Control `full` Mappings (`4` items)** | `MAP-PRIMARY-006`, `MAP-PRIMARY-019`, `MAP-PRIMARY-020`, `MAP-PRIMARY-024` | Legal confirmation of whether binding `MAP-PRIMARY-006/019/020` and CPG 235 lifecycle guidance `MAP-PRIMARY-024` remain `full` or narrow to `partial`/`related`. |
| **Non-Equivalence Guardrail Sign-Off (`3` items)** | `MAP-CROSS-003`, `MAP-CROSS-004`, `MAP-CROSS-006` | Technical empty-facet guardrail applied in E4.1; Privacy and AFS Counsel confirm regulatory non-equivalence wording before approval. |
| **Unlicensed Commercial ISO Standards (`3` sources / `4` obs / `6` mappings)** | `ISO-42001`, `ISO-23894`, `ISO-27001` | Status remains `source_unavailable` because full commercial ISO text cannot be stored without a valid license; legal approval blocked until licensed text review occurs in a private overlay. |

## 2. Candidate Requirements Staged Outside Runtime (`E41_CANDIDATE_REQUIREMENTS_REGISTER.csv`)

The 3 P0 completeness gaps identified in E4 are authored as `proposed`, `imported_to_runtime=false` candidates awaiting Compliance/Product scoping approval before runtime library import:
1. **`CAND-FAR-2023-01` (`GAP-FAR-2023`)** — *Financial Accountability Regime Act 2023* (`C2023A00067`, ss 21–23, ADI effective `2024-03-15`).
2. **`CAND-CORP-912A-01`, `CAND-CORP-912D-02`, `CAND-CORP-PT78A-03` (`GAP-CORP-912A-DDO-BREACH`)** — *Corporations Act 2001* (`C2004A00818`, `s 912A(1)`, `s 912D` / RG 78 30-day breach reporting, `Part 7.8A` DDO / TMD / RG 274).
3. **`CAND-ASIC-2022-205-01` (`GAP-ASIC-2022-205`)** — *ASIC Corporations (Internal Dispute Resolution Data Reporting) Instrument 2022/205* (`F2022L00430`).
