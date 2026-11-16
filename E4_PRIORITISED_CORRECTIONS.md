# E4 Prioritised Remediation & Corrections Plan

**Audit Date:** 2026-11-15  
**Scope:** Recommended fixes to `REGULATORY_SOURCE_REGISTER.csv`, `ATOMIC_OBLIGATION_CATALOGUE.json`, `OBLIGATION_CONTROL_MAPPINGS.json`, `regulatory_pack.v0.1.json`, and applicability rules (`applicability.py`) prior to any legal sign-off or `approved` promotion.  
**Safeguard Note:** Per E4 validation rules, all existing runtime library records remain preserved in `proposed` status until a qualified human reviewer verifies and applies each approved edit.

---

## Priority P0 — Release-Critical Legal Accuracy & Applicability Defects

### 1. Fix Misattributed ASIC RG 271 & IDR Data Reporting Instruments (`AU-ASIC-RG271-SYSTEMIC`, `MAP-PRIMARY-026`, `ASIC-RG271`)
- **Primary-Source Evidence:** Under *ASIC Instrument 2020/98*, systemic issue enforceable paragraphs are **RG 271.118–271.120** (+ note), while **RG 271.116** addresses hardship notices / enforcement postponement and **RG 271.165** requires timely implementation of complaint outcomes. Mandatory IDR data reporting to ASIC arises under separate legislative instrument ***ASIC Corporations (Internal Dispute Resolution Data Reporting) Instrument 2022/205*** (`F2022L00430`, amended by `2023/282` and `2026/48`).
- **Required Correction:**
  1. Remove incorrect claim `"RG 271.117–271.121 are enforceable requirements under ASIC Instrument 2020/98"` and `"271.165–271.182 (Systemic issues and IDR data reporting)"` from `AU-ASIC-RG271-SYSTEMIC`.
  2. Restrict `AU-ASIC-RG271-SYSTEMIC` to Instrument `2020/98` systemic issues (`RG 271.118–271.120`) and outcome execution (`RG 271.165`).
  3. Add a distinct `binding` source and obligation for **ASIC Instrument 2022/205 (`F2022L00430`)** IDR Data Reporting; update `AU-ASIC-RG271-COMPLAINT` to explicitly separate enforceable `2020/98` paragraphs from guidance expectations (like `271.51` acknowledgement).

### 2. Fix Misstated Enacted Privacy Act `APP 11.3` (`AU-PRIV-APP11-SECURITY`, `MAP-PRIMARY-007`, `CTRL-PRIV-SECURITY-RETENTION`)
- **Primary-Source Evidence:** The *Privacy and Other Legislation Amendment Act 2024* (`C2024A00128`, commenced **11 December 2024**) enacted **APP 11.3**, explicitly clarifying that "reasonable steps" under APP 11.1 and APP 11.2 include **technical and organisational measures** (TOMs).
- **Required Correction:**
  1. Update `AU-PRIV-APP11-SECURITY` `provision` from `"Schedule 1, APP 11.1–11.2 ( including APP 11.3 retention commentary )"` to `"Schedule 1, APP 11.1–11.3"` and update `legal_note` to reflect commencement on `11 December 2024`.
  2. Add/update facet & rationale coverage in `MAP-PRIMARY-007` and `CTRL-PRIV-SECURITY-RETENTION` to verify both **technical** and **organisational** security measures, eliminating the erroneous `"APP 11.3 retention commentary"` phrase.

### 3. Update EU AI Act Annex III Timeline per `Regulation (EU) 2026/1744` (`EU-AI-ACT`, `EU-AIA-ART2-HIGH-RISK`, `EU-AIA-ART26-27-DEPLOYER-CREDIT`)
- **Primary-Source Evidence:** **Regulation (EU) 2026/1744** ("Digital Omnibus on AI") amended **Article 113(c)(i)** of Regulation (EU) 2024/1689, extending stand-alone **Annex III high-risk AI obligations** (including `Annex III point 5(b)` creditworthiness) from `2 August 2026` to **2 December 2027** (with Annex I embedded product systems extended to `2 August 2028`), while Arts 4 & 5 remain effective from `2 February 2025`.
- **Required Correction:**
  1. Update `effective_from` on `EU-AIA-ART2-HIGH-RISK` and `EU-AIA-ART26-27-DEPLOYER-CREDIT` from `2026-08-02` to `2027-12-02` (and update `EU-AI-ACT` source notes).
  2. Update `applicability._eu()` so `obligation.effective_from` is evaluated consistently with `_eu_deployer_high_risk()`, preventing premature positive/active triggers prior to `2027-12-02`.
  3. Split `Article 50` interactive AI transparency out of `EU-AIA-ART26-27-DEPLOYER-CREDIT`, and split the composite facet `deployer_human_oversight_and_6month_log_retention` into separate facets (`deployer_human_oversight_assigned` and `automatic_logs_retained_6months`) to prevent `MAP-CROSS-005`/`006` over-claims.

### 4. Correct Invalid APRA CPS 220 FRL Identifier (`APRA-CPS220`, `AU-APRA-CPS220-REVIEW`)
- **Primary-Source Evidence:** Federal Register of Legislation instrument **`F2017L00695`** belongs to *Disability Services (Rehabilitation Services) Guidelines*, **not** APRA Prudential Standard CPS 220. Additionally, `CPS 220 para 37` addresses policy review tracking rather than the start of independent review obligations (~`paras 45-48`, 3-yearly review) and Attachment A annual declaration (`~paras 49-51`).
- **Required Correction:**
  1. Remove erroneous `F2017L00695` from `APRA-CPS220.version_id` and record the verified FRL determination/compilation ID for CPS 220.
  2. Verify exact paragraph numbering for Board RMF, Risk Management Function/CRO, 3-yearly Comprehensive Review, and Attachment A Annual Risk Management Declaration against the official CPS 220 text.

### 5. Close Three P0 Completeness Gaps for Australian ADIs / Licensees
- Add **Financial Accountability Regime Act 2023 (Cth)** (`C2023A00067`, commenced `15 Mar 2024` for ADIs) covering Accountable Persons & Accountability Statements for AI/model governance.
- Add direct **binding** source/obligations for **Corporations Act 2001 (Cth)** (`C2004A00818`): `s 912A(1)` general obligations (separating binding law from RG 104 guidance), `s 912D` Reportable Situations (`RG 78`), and **Part 7.8A Design & Distribution Obligations (`ss 994B-994D` / RG 274)**.
- Add **ASIC Instrument 2022/205 (`F2022L00430`)** as a standalone binding reporting obligation.

---

## Priority P1 — Mapping Defensibility, Shared-Control Over-Broadening & Temporal Nuances

1. **Deduplicate `ISO23894-AI-RISK-PROCESS -> CTRL-RISK-FRAMEWORK` (`MAP-PRIMARY-044` vs `MAP-CROSS-007`):**
   - Automated check flags exact duplicate `(obligation_id, control_id)` pair with conflicting `mapped_facets` (`3/3` in `MAP-PRIMARY-044` vs `2/3` in `MAP-CROSS-007`). Remove redundant `MAP-CROSS-007` (or clarify distinct facet sub-mapping after licensed ISO 23894 verification).
2. **Mitigate False Equivalence & Over-Broadening on Shared Controls (`CTRL-AI-GOV-ACCOUNTABILITY` x5, `CTRL-SEC-COMMENSURATE` x4):**
   - Downgrade `MAP-PRIMARY-030` (`AU-ASIC-REP798-AI-GAP` guidance) and `MAP-PRIMARY-031` (`AU-NCCP-S47-CONDUCT` broad general conduct statute) from `full` to `partial` or `related`; review `MAP-PRIMARY-023` (`CPG 235`), `027` (`RG 104`), and `028` (`RG 104`) `full` labels against non-binding guidance authority to avoid implying that one unified control discharges broad statutory/guidance regimes.
3. **Prevent `mapped_facets` Leakage on `non_equivalent` Mappings (`MAP-CROSS-003`, `004`, `006`):**
   - Although caution fields explicitly warn `CRITICAL NON-EQUIVALENCE`, all three `non_equivalent` mappings currently populate `mapped_facets`. Either clear `mapped_facets` (moving all to `unmapped_obligation_facets`) or assert an explicit runtime guard ensuring `non_equivalent` cross-mappings never credit obligation coverage.
4. **Fix APRA CPS 230 Phased Commencement Metadata (`AU-APRA-CPS230-OPS`, `BCP`) & CPG 235 EUC Scope (`AU-APRA-CPG235-LIFECYCLE`):**
   - Document `1 July 2025` initial CPS 230 commencement (`F2023L01025`) vs `1 July 2026` revised commencement/transitional completion so historical point-in-time (`2025-07-01..2026-06-30`) assessments evaluate core operational risk & SFI BCP accurately.
   - Decompose `CPG 235 para 45` End-User Computing (EUC / shadow AI tools) out of `paras 20-45`, and reconcile `CPS 234 paras 32-36` overlap with `paras 27-34`.
5. **Add P1 Consumer, Privacy & Financial-Crime Sources:**
   - *ASIC Act 2001* Pt 2 Div 2 / *ACL* (`misleading/deceptive` GenAI outputs), *Banking Code of Practice (2025)* (`28 Feb 2025`), *Privacy Act 1988 Part IIIA* (credit reporting AI) & *Statutory Tort* (`10 Jun 2025`), and *SOCI Act 2018* / *AML-CTF Act 2006*.

---

## Priority P2 — Commercial Overlay Governance, Hygiene & Structural Improvements

1. **Licensed ISO Verification (`ISO-42001`, `ISO-23894`, `ISO-27001`):**
   - Keep all 4 ISO obligations and 7 ISO-related mappings in `proposed` / `source_unavailable` until an enterprise customer or compliance team supplies licensed text via `PRIVATE_REGULATORY_OVERLAY_PATH`.
2. **Preserve Official Binary Snapshots / Hashes:**
   - Replace `NOT_DOWNLOADED_URL_REFERENCED` across the 14 open government/EU/NIST sources with verified local snapshot SHA-256 digests during periodic compliance release sign-off (consistent with E4's no-crawler, one-time QA policy).
3. **Add P2 Supporting Prudential & Data-Sharing Rules:**
   - *APRA CPS 511 Remuneration*, *APRA CPG 230*, *APRA CPG 234*, *Consumer Data Right (CCA Pt IVD)*, and *Spam Act 2003*.

---

## E4.1 Remediation Update (`2026.11-au-banking-v0.2.0`)

P0 findings C1–C11 from this E4 register have been remediated in **E4.1** (`regulatory_pack` `0.2.0`, `obligation_control_mappings` `1.1.0`); see [`E41_REGULATORY_CORRECTION_CHANGELOG.md`](E41_REGULATORY_CORRECTION_CHANGELOG.md), [`E41_CONTROL_MAPPING_REMEDIATION.md`](E41_CONTROL_MAPPING_REMEDIATION.md), and [`E41_CANDIDATE_REQUIREMENTS_REGISTER.csv`](E41_CANDIDATE_REQUIREMENTS_REGISTER.csv). Remaining open legal review and deferred items are tracked in [`E41_PENDING_LEGAL_REVIEW.md`](E41_PENDING_LEGAL_REVIEW.md).
