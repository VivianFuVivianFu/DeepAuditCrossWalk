# E3.2 Matching Failure Analysis

This analysis focuses primarily on genuine, uncontaminated failures observed on the **E3.2 Independent Holdout (`N=18`, Regulatory Pack `0.2.0`)**, alongside key residual patterns from `e11`, `e3`, and `e31`. Because live Gemini inference was **not run** (`NOT RUN — CREDENTIALS UNAVAILABLE`), attribution covers Config A (`deterministic`), Config B (`embedding_only` mock), and Config C (`hybrid` mock).

---

## 1. E3.2 Independent Holdout Error Inventory (`7/18` Failures in Config C Mock-Hybrid; `10/18` in Config A)

### Case `E32-HO-04` — Statutory `"Annex III"` Colliding with Vague-Annex Ambiguity Filter
- **Phenomenon:** `eu_art26_27_decomposed_facets`
- **Source Excerpt:** *"Where EU territorial scope applies to consumer creditworthiness scoring under **Annex III** point 5(b), deployers must assign competent human oversight, retain automatic execution logs for at least six months, and document a Fundamental Rights Impact Assessment before launch."*
- **Expected:** `EU-AIA-ART26-27-DEPLOYER-CREDIT` -> `partially_overlapping`
- **Returned:** Config A & C emitted `pred_rel = "undetermined"` (`pred_ob = None` in hybrid).
- **Root Cause & Module:** **Deterministic Stage A/C Pre-Guard (`reconciliation.py` `_is_ambiguous_clause` / `AMBIGUOUS_CLAUSE_PATTERNS`)**. Regex `"annex [a-z0-9]+"` matched the literal statutory reference `"Annex III"` in the EU AI Act, short-circuiting the entire hybrid pipeline to `UNDETERMINED` before EU AI Act retrieval or Stage B LLM analysis ran!
- **Justified Non-Overfitting Remediation (Deferred to Next Fix PR):** Refine `AMBIGUOUS_CLAUSE_PATTERNS` so explicit EU AI Act legislative citations (`Annex I`, `Annex III`, `Annex IV` accompanied by `point|ai act|regulation|eu|high-risk|creditworthiness`) are not misclassified as undefined internal policy annexes.

### Case `E32-HO-05` — Permissive Omission (`"may close ... informally without logging"`) Not Escalated to `potential_conflict`
- **Phenomenon:** `contradiction_idr_complaint`
- **Source Excerpt:** *"Frontline chatbots may close retail customer dissatisfaction threads informally without logging a complaint or issuing written reasons or AFCA escalation options within 30 calendar days."*
- **Expected:** `AU-ASIC-RG271-COMPLAINT` -> `potential_conflict`
- **Returned:** `AU-ASIC-RG271-COMPLAINT` -> `weaker_or_potentially_insufficient` (both Config A & C).
- **Root Cause & Module:** **Deterministic Stage B Polarity + Mock Stage B (`policy.py` `ABSENCE_OF_CONTROL_PATTERN` & `providers.py`)**. Retrieval succeeded (`AU-ASIC-RG271-COMPLAINT` #1), and Stage C safely refused false coverage, but `ABSENCE_OF_CONTROL_PATTERN` matched explicit phrases like `"does not require"` rather than `"may close ... informally without logging"`, producing `weaker_or_potentially_insufficient` instead of `potential_conflict`. A genuine LLM reading statutory IDR logging duties should elevate explicit `"without logging"` of complaints to `potential_conflict`.

### Case `E32-HO-08` — Non-Equivalent Cross-Framework Confusion (APRA CPS 234 72h Masking Privacy Act NDB)
- **Phenomenon:** `non_equivalent_ndb_vs_cps234_conflict`
- **Source Excerpt:** *"Once a suspected personal-information data breach is notified to APRA under CPS 234 within 72 hours, teams do not need to conduct a 30-day OAIC serious-harm assessment or notify affected individuals."*
- **Expected:** `AU-PRIV-NDB-S26WE` -> `potential_conflict`
- **Returned:** Config C emitted top obligation **`AU-APRA-CPS234-INCIDENT`** with `weaker_or_potentially_insufficient` (`AU-PRIV-NDB-S26WE` was crowded out of top candidates!).
- **Root Cause & Module:** **Stage A Retrieval Ranking (`reconciliation.py` + mock embedding concept overlap)**. `"APRA"`, `"CPS 234"`, `"72 hours"` matched `AU-APRA-CPS234-INCIDENT` cleanly, while the negative waiver targeting OAIC (`"do not need to conduct a 30-day OAIC serious-harm assessment"`) should simultaneously retrieve `AU-PRIV-NDB-S26WE` and flag the illegal substitution as `potential_conflict`. Note: the candidate limit (`max_cands=3`) filled slots with `AU-APRA-CPS234-INCIDENT/CONTROLS/TEST`, dropping `AU-PRIV-NDB-S26WE`.

### Case `E32-HO-07` — Un-Tuned Equivalent Under Pack v0.2.0 (`AU-APRA-CPS220-REVIEW`)
- **Phenomenon:** `cps220_f2019l00669_review`
- **Source Excerpt:** *"Second-line risk officers must independently challenge AI risk assessments, include AI controls within annual audit and three-yearly independent comprehensive RMF reviews, and escalate unresolved material gaps for the Board's annual CPS 220 Risk Management Declaration."*
- **Expected:** `AU-APRA-CPS220-REVIEW` -> `equivalent`
- **Returned:** `AU-APRA-CPS220-REVIEW` -> `partially_overlapping` (conservative downgrade, `0` false equivalence).
- **Root Cause & Module:** **Deterministic Stage C + Mock Stage B `facet_semantic_cues`**. Exact phrase wording (`"Line 2"` vs `"Second-line"`, `"framework review covers AI"`) missed mock/lexical substring triggers (`providers.py` line 1108 un-tuned fallback). Real Gemini Stage B structured reasoning is specifically needed to determine whether semantic paraphrases satisfy all facets without hardcoding substring lists.

### Case `E32-HO-15` — False-Positive Conflict on Clean Multi-Obligation Clause (`AU-ASIC-RG271-COMPLAINT` + `AU-PRIV-NDB-S26WE`)
- **Phenomenon:** `multi_obligation_complaint_and_ndb`
- **Source Excerpt:** *"Retail banking complaint handlers must document expressions of dissatisfaction and answer within maximum response timeframes with AFCA details, while cyber responders detecting personal-data leakage must initiate an eligible data breach assessment within 30 days."*
- **Expected:** `AU-ASIC-RG271-COMPLAINT` (`partially_overlapping`) + `AU-PRIV-NDB-S26WE` (`partially_overlapping`)
- **Returned:** Both `AU-ASIC-RG271-COMPLAINT` and `AU-PRIV-NDB-S26WE` WERE retrieved & emitted (`Multi-Ob Ret=1/1, Dec=1/1` in Config C vs `0/1` in Config A), **but Config A & C classified `AU-ASIC-RG271-COMPLAINT` as `potential_conflict`**!
- **Root Cause & Module:** **Deterministic Stage B Numeric Timing Extractor (`reconciliation.py`)**. Notice the clause mentions `"within 30 days"` in its *second* (NDB) half, plus `"maximum response timeframes"` (`30 calendar days` in `RG271`, `21 days` hardship!). Wait: `reconciliation.py`'s clause-level timing detector sees `"30 days"` (or NDB vs shorter credit hardship deadline / timing mismatch) and falsely triggers `timeframe_conflict=True`, turning `AU-ASIC-RG271-COMPLAINT` into a **false conflict (`1/18`)**. Multi-clause timing attribution cannot be bound safely per sentence without an LLM or clause splitter.

### Case `E32-HO-16` — Unpatched Australian `"Annexure G"` + Discretionary Waiver
- **Phenomenon:** `ambiguous_annexure_and_discretion`
- **Source Excerpt:** *"AI override tolerances follow **Annexure G** escalation procedures unless the regional committee decides to apply discretionary interim arrangements."*
- **Expected:** `UNDETERMINED` (`pred_ob = None`)
- **Returned:** `weaker_or_potentially_insufficient` against `AU-ASIC-RG271-COMPLAINT` / `AU-ASIC-RG104-REPRESENTATIVES`.
- **Root Cause & Module:** Confirms the exact unpatched E3.1 holdout finding (`E31-HO-10`): `AMBIGUOUS_CLAUSE_PATTERNS` omits `"annexure"`, so `"unless ..."` dominates Stage B into `weaker_or_potentially_insufficient` instead of `undetermined`.

### Case `E32-HO-18` — Unseen Out-of-Domain Marketing Brand Rule -> **False Positive Coverage Proposal (`1/18`)**
- **Phenomenon:** `unmapped_corporate_brand_standard`
- **Source Excerpt:** *"All internal marketing slide decks describing AI pilots must adhere to the bank's FY27 corporate typography palette, brand logo spacing and executive template standards."*
- **Expected:** `unmapped_no_reliable_relationship` (`pred_ob = None`)
- **Returned (Config C Hybrid Mock):** `EU-AIA-ART4-5-PROHIBITED-LITERACY` -> **`partially_overlapping`** (**1 false positive coverage proposal**!). Config A (`disabled`) correctly returned `unmapped_no_reliable_relationship`.
- **Root Cause & Module:** **Mock Embedding + Mock `emb >= 0.40` Fallback (`providers.py` lines 1286–1291)**. Because we intentionally withheld marketing/typography phrases from `out_of_domain_cues`, character-trigram cosine hash similarity (`"ai"`, `"pilots"`, `"adhere"`) exceeded retrieval threshold `0.36` and mock fallback `0.40`, proposing coverage against EU AI Act literacy/prohibited practices! **Critical Lesson:** Even embedding similarity alone (`Config B = 2/18` false positive proposals vs `Config A = 0/18` on `e32`) can hallucinate topical overlap on irrelevant corporate rules if Stage B LLM + Stage C do not verify domain relevance.

---

## 2. Historical Benchmark Residual Patterns (`e11`, `e3`, `e31`)

- **`e11` `HO-TIB-08` (now failing in v0.2.0):** Expected `equivalent` to `AU-PRIV-APP11-SECURITY`; system returned `partially_overlapping` because v0.2.0 enforces *POLA Act 2024* APP 11.3's dual requirement (technical + organisational measures), which `0.1.0`-era policy text omitted.
- **Improved Retrieval in B & C across unseen paraphrases:** On `e32`, deterministic-only Stage A failed completely on zero-keyword paraphrases (`E32-HO-13` PIA workshop, `E32-HO-14` cross-border cloud vendors) and dropped the second obligation on `E32-HO-15` (`0/1`), whereas mock embeddings recovered `E32-HO-06`, `E32-HO-13`, `E32-HO-14`, and `E32-HO-15` (`1/1`).
- **Safety Vetoes Held Across All Runs:** `False Equivalence = 0` across all `138` total benchmark clauses (`36 + 60 + 24 + 18`) and all 3 configurations; `False Confirmed Coverage = 0` across all clauses and all `22` questionnaire queries.
