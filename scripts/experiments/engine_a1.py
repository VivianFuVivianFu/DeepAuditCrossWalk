"""Enhanced Deterministic Rules Engine (A1).

Phase P1B experimental rules engine implementing expanded canonical facet coverage (~40 facets),
robust clause boundary detection, domain phrase patterns, numeric AST validation,
and normative modality & candidate suppression handling.

Does not modify any production code. Outputs candidate predictions with review_status="proposed".
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from .models import CandidatePrediction, ExtractionResult, ThresholdAST


class EngineA1:
    """Enhanced Deterministic Rules Engine (A1)."""

    # Stage 1: Modality & Normative Regex Patterns
    # 1a. Prohibitions that forbid or disable a beneficial control (MUST suppress)
    CONTROL_PROHIBITION_PATTERN = re.compile(
        r"\b((?:shall|must) not (?:implement|perform|conduct|execute|enable|log|record) "
        r"(?:automated )?(?:bias testing|fairness|penetration testing|security testing|audit|validation)|"
        r"prohibited from (?:performing|conducting|implementing|logging) "
        r"(?:bias testing|fairness|audit|security testing|validation)|"
        r"forbidden from publicly disclosing security incidents or apra notifications)\b",
        re.IGNORECASE,
    )

    # 1b. Out-of-scope corporate/HR prohibitions with no UCL control target (MUST suppress)
    UNMAPPED_PROHIBITION_PATTERN = re.compile(
        r"\b(prohibited from taking adverse|retaliatory employment action)\b",
        re.IGNORECASE,
    )

    # 1c. Protective / preventive prohibitions that enforce a security, privacy, or governance control (DO NOT suppress in revised mode)
    PROTECTIVE_PROHIBITION_PATTERN = re.compile(
        r"\b(prohibited from transmitting unencrypted|must not transmit unencrypted|"
        r"must not collect or process .* without (?:formal )?(?:statutory )?consent|"
        r"prohibited from collecting or processing sensitive data|"
        r"under no circumstances shall .* retain .* local workstation|"
        r"shall not disable .* scanning|bypass static analysis security testing|"
        r"shall not deploy .* without an approved and tested business continuity plan|"
        r"shall not execute agreements .* that exclude liability|"
        r"shall not override .* without written concurrence|"
        r"shall not refuse to register .* dissatisfaction|"
        r"shall not approve .* without actual verification|"
        r"strictly prohibited under article 5)\b",
        re.IGNORECASE,
    )

    # 1d. Legacy P1B-1 syntactic prohibition pattern (used only when normative_mode == 'historical_p1b1')
    PROHIBITION_ABSOLUTE_PATTERN = re.compile(
        r"\b(strictly prohibited|strictly forbidden|prohibited under any circumstances|"
        r"under no circumstances shall|under no conditions|must not under any circumstances|"
        r"personnel are prohibited from|employees are prohibited from|staff are prohibited from|"
        r"staff must not collect|management is (?:strictly )?prohibited from|"
        r"prohibited from taking adverse|retaliatory employment action|forbidden from publicly disclosing)\b",
        re.IGNORECASE,
    )

    CONTROL_WAIVER_PATTERN = re.compile(
        r"\b(is waived|are waived|waived for|control waiver|waiver of .* requirement)\b",
        re.IGNORECASE,
    )

    MISSING_IMPLEMENTATION_PATTERN = re.compile(
        r"\b(does not currently (?:implement|encrypt|maintain|perform)|"
        r"has not implemented|no .* controls? are currently in place|"
        r"has zero .* compliance obligations|no .* compliance obligations apply)\b",
        re.IGNORECASE,
    )

    SCOPE_EXEMPTION_PATTERN = re.compile(
        r"\b(is exempt from|are exempt from|exemption for|exempt from|"
        r"does not apply to|do not apply to|excluded from the scope of|"
        r"are excluded from|out of scope|sandboxes are exempt|publicly available .* are exempt|"
        r"not classified as third-party service providers)\b",
        re.IGNORECASE,
    )

    PERMISSIVE_GUIDANCE_PATTERN = re.compile(
        r"\b(may optionally|may choose to|may seek informal|may at (?:its|their) discretion|"
        r"at their convenience|if commercially convenient|is encouraged to|are encouraged to)\b",
        re.IGNORECASE,
    )

    ASPIRATIONAL_PATTERN = re.compile(
        r"\b(strives? to|endeavours? to|aims? to|aspires? to|"
        r"overarching ambition is to|champions? proactive|cultural mindfulness|"
        r"future digital banking microservices|highest ethical standards)\b",
        re.IGNORECASE,
    )

    CONDITIONAL_BLOCK_PATTERN = re.compile(
        r"\b(must not execute without|shall not execute without|cannot proceed without|"
        r"prohibited prior to|must not disburse .* without|shall not proceed without|"
        r"before payment|before execution|prior to payment|prior to execution)\b",
        re.IGNORECASE,
    )

    MANDATORY_PATTERN = re.compile(
        r"\b(must|shall|required to|is required|are required|mandatory|will enforce)\b",
        re.IGNORECASE,
    )

    THRESHOLD_AMOUNT_PATTERN = re.compile(
        r"(?:(?:AUD|USD|EUR|GBP)\s*\$?\s*|\$\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d,])",
        re.IGNORECASE,
    )

    # Stage 2: Expanded Canonical Facet Patterns (~40 Facets across 33 UCL Controls)
    FACET_REGEX_PATTERNS: ClassVar[dict[str, Sequence[re.Pattern]]] = {
        # Governance & Delegated Authority
        "human_approval_required": [
            re.compile(r"\b(human approval|manual approval|approved by a human|authorised officer|dual sign-off|dual approval|two-up|manual override|human underwriter concurrence)\b", re.IGNORECASE),
        ],
        "approval_threshold_defined": [
            re.compile(r"\b(threshold|above aud|over aud|aud\s*\$|\$\s*\d|delegated authority|approval limit)\b", re.IGNORECASE),
        ],
        "pre_execution_block": [
            re.compile(r"\b(before payment|before execution|prior to payment|prior to execution|prior to transaction release|pre-execution|prevent execution|cannot proceed|shall not proceed without|must not execute without)\b", re.IGNORECASE),
        ],
        "approval_logs_retained": [
            re.compile(r"\b(approval log|audit log|record approval|retain approval|approval record|immutable audit|immutable log|audit trail|human review records|officer signature hashes)\b", re.IGNORECASE),
        ],
        "clear_escalation_and_override_authority": [
            re.compile(r"\b(clear escalation|escalation pathways?|manual override authority|override authority|override .* assessments? .* concurrence)\b", re.IGNORECASE),
        ],
        "meaningful_human_oversight_and_kill_switch": [
            re.compile(r"\b(kill-switch|kill switch|meaningful human oversight|immediate suspension of automated)\b", re.IGNORECASE),
        ],
        "board_or_senior_oversight": [
            re.compile(r"\b(board risk committee|board oversight|senior executive oversight|risk appetite metrics?)\b", re.IGNORECASE),
        ],
        "ai_risk_identified": [
            re.compile(r"\b(ai risk|risk identification|risk assessment framework|risk sources)\b", re.IGNORECASE),
        ],
        "independent_framework_review_covers_ai": [
            re.compile(r"\b(independent validation|independent audit|second line|line 2 challenge|model validation unit|independent framework review)\b", re.IGNORECASE),
        ],
        "use_case_registered_in_enterprise_ai_inventory": [
            re.compile(r"\b(model registry|ai inventory|registered in .* inventory|use case register|model catalog|model card)\b", re.IGNORECASE),
        ],
        "ai_assets_classified_by_criticality_and_sensitivity": [
            re.compile(r"\b(tier 1|criticality|sensitivity classification|high-risk ai|model classification|asset classification)\b", re.IGNORECASE),
        ],

        # Privacy & Personal Information (APPs)
        "pia_threshold_screen_completed": [
            re.compile(r"\b(privacy impact assessment|pia|privacy-by-design|threshold screen)\b", re.IGNORECASE),
        ],
        "privacy_accountability_assigned": [
            re.compile(r"\b(chief privacy officer|privacy officer|privacy lead|privacy accountability)\b", re.IGNORECASE),
        ],
        "privacy_practices_implemented": [
            re.compile(r"\b(privacy policy|privacy practices?|app 1|privacy governance)\b", re.IGNORECASE),
        ],
        "collection_purpose_defined": [
            re.compile(r"\b(collection purpose|solicited personal information|purpose of collection|app 3)\b", re.IGNORECASE),
        ],
        "sensitive_information_consent": [
            re.compile(r"\b(sensitive information|biometric.*consent|consent for collection|statutory consent)\b", re.IGNORECASE),
        ],
        "overseas_recipients_and_regions_mapped": [
            re.compile(r"\b(overseas recipient|cross-border|sovereignty|on-shore|data center location|transmission path|overseas storage|app 8)\b", re.IGNORECASE),
        ],
        "retention_schedule_applied": [
            re.compile(r"\b(retention schedule|retention period|statutory retention|retain .* years?|retention limit|7 years|retain customer identification documents on local workstation)\b", re.IGNORECASE),
        ],
        "destruction_or_deidentification_verified": [
            re.compile(r"\b(permanently purge|de-identify|deidentification|secure deletion|destruction|dispose|disposal)\b", re.IGNORECASE),
        ],
        "technical_security_measures_implemented": [
            re.compile(r"\b(technical security measures?|aes-256|encryption at rest|private tenant vpcs?|vpc isolation|cryptographic storage|de-identification and encryption of personal information)\b", re.IGNORECASE),
        ],
        "organisational_security_measures_implemented": [
            re.compile(r"\b(organisational security measures?|organizational security measures?|staff privacy training|information handling procedures?|access review procedures?|need-to-know access governance|personnel security vetting)\b", re.IGNORECASE),
        ],
        "access_and_correction_timeframes_tracked": [
            re.compile(r"\b(access and correction|app 12|app 13|personal information access|correction procedure|correction request)\b", re.IGNORECASE),
        ],

        # Security & Cyber (APRA CPS 234)
        "controls_commensurate": [
            re.compile(r"\b(commensurate|tls 1\.[23]|encryption in transit|mfa|multi-factor|access control|transmitting unencrypted customer information|transmit unencrypted customer information|disable automated runtime dependency scanning|bypass static analysis security testing)\b", re.IGNORECASE),
        ],
        "security_roles_and_asset_owners_assigned": [
            re.compile(r"\b(asset owner|ciso|chief information security officer|security role)\b", re.IGNORECASE),
        ],
        "testing_program_exists": [
            re.compile(r"\b(penetration testing|pen-test|vulnerability assessment|security testing program|testing program)\b", re.IGNORECASE),
        ],
        "testing_scope_defined": [
            re.compile(r"\b(testing scope|prior to major release|prior to deployment|testing frequency|annual testing)\b", re.IGNORECASE),
        ],
        "incident_detection_defined": [
            re.compile(r"\b(incident detection|security operations center|soc|detect .* incident|threat detection)\b", re.IGNORECASE),
        ],
        "response_and_escalation_defined": [
            re.compile(r"\b(incident response|escalation|notify .* ciso|apra notification|within 2 hours|breach response)\b", re.IGNORECASE),
        ],

        # Third-Party & Operational Resilience (APRA CPS 230)
        "provider_materiality_assessed": [
            re.compile(r"\b(provider materiality|material cloud|cps 230|service provider policy|material supplier)\b", re.IGNORECASE),
        ],
        "due_diligence_completed": [
            re.compile(r"\b(due diligence|vendor assessment|third-party assessment|supplier assessment|due diligence prior to)\b", re.IGNORECASE),
        ],
        "contract_controls_defined": [
            re.compile(r"\b(contractual controls?|right to audit|exit strategy|subcontractor|material contract)\b", re.IGNORECASE),
        ],
        "continuity_plan_tested": [
            re.compile(r"\b(failover testing|business continuity|bcp|disaster recovery|simulated failover)\b", re.IGNORECASE),
        ],
        "tolerance_and_fallback_defined": [
            re.compile(r"\b(tolerance limit|fallback procedure|alternative provider|disruption tolerance)\b", re.IGNORECASE),
        ],
        "incidents_and_weaknesses_managed": [
            re.compile(r"\b(control weakness|operational incident|investigate .* incident|operational risk|weakness tracking)\b", re.IGNORECASE),
        ],

        # Dispute Resolution (ASIC RG 271)
        "complaints_broadly_recognised": [
            re.compile(r"\b(complaints? broadly|expression of dissatisfaction|dissatisfaction|idr process)\b", re.IGNORECASE),
        ],
        "complaints_recorded": [
            re.compile(r"\b(complaint register|record .* complaint|central dispute register|within 24 hours)\b", re.IGNORECASE),
        ],
        "response_timeframes_enforced": [
            re.compile(r"\b(response timeframe|30 days|idr timeframe|maximum timeframe)\b", re.IGNORECASE),
        ],
        "systemic_issues_escalated": [
            re.compile(r"\b(systemic issue|systemic defect|root cause analysis|rg 271)\b", re.IGNORECASE),
        ],

        # AI Fairness & Trustworthiness
        "fairness_and_explainability_metrics_evaluated": [
            re.compile(r"\b(bias testing|algorithmic bias|statistical fairness|demographic parity|disparate impact|explainability|fairness metrics)\b", re.IGNORECASE),
        ],
        "residual_risk_acceptance_and_drift_response_logged": [
            re.compile(r"\b(model drift|concept drift|data drift|recalibration trigger|drift monitoring|drift response)\b", re.IGNORECASE),
        ],
        "article50_ai_interaction_transparency_provided": [
            re.compile(r"\b(transparency disclosure|inform users .* ai|conversational bot|customer-facing bot|communicating with an ai)\b", re.IGNORECASE),
        ],
        "deployer_human_oversight_assigned": [
            re.compile(r"\b(assign(?:ed|ing)? natural persons? .* oversee|deployer human oversight|competence, training and authority .* high-risk|article 26\(2\))\b", re.IGNORECASE),
        ],
        "automatic_logs_retained_6months": [
            re.compile(r"\b(retain(?:ed|ing)? .* logs? .* (?:at least )?6 months|logs generated by the ai system for at least 6 months|automatically generated logs? .* 6 months|article 26\(6\))\b", re.IGNORECASE),
        ],
        "synthetic_content_marking_and_disclosure_applied": [
            re.compile(r"\b(synthetic (?:audio|image|video|text|content)|machine-readable .* artificially generated|deepfake disclosure|article 50\([234]\))\b", re.IGNORECASE),
        ],
        "article5_prohibited_practices_screened_out": [
            re.compile(r"\b(subliminal techniques|exploit vulnerabilities of specific demographic groups|strictly prohibited under article 5|article 5 prohibited)\b", re.IGNORECASE),
        ],
    }

    # Direct Facet to Primary Canonical Control Binding ( strictly validated against UCL parent control )
    FACET_TO_CANONICAL_CONTROL: ClassVar[dict[str, str]] = {
        "human_approval_required": "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "approval_threshold_defined": "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "pre_execution_block": "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "approval_logs_retained": "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "clear_escalation_and_override_authority": "CTRL-HUMAN-OVERSIGHT",
        "meaningful_human_oversight_and_kill_switch": "CTRL-HUMAN-OVERSIGHT",
        "board_or_senior_oversight": "CTRL-RISK-FRAMEWORK",
        "ai_risk_identified": "CTRL-RISK-FRAMEWORK",
        "independent_framework_review_covers_ai": "CTRL-INDEPENDENT-AUDIT-ASSURANCE",
        "use_case_registered_in_enterprise_ai_inventory": "CTRL-AI-GOV-ACCOUNTABILITY",
        "ai_assets_classified_by_criticality_and_sensitivity": "CTRL-SEC-COMMENSURATE",
        "pia_threshold_screen_completed": "CTRL-PRIV-GOVERNANCE",
        "privacy_accountability_assigned": "CTRL-PRIV-GOVERNANCE",
        "privacy_practices_implemented": "CTRL-PRIV-GOVERNANCE",
        "collection_purpose_defined": "CTRL-PRIV-COLLECTION",
        "sensitive_information_consent": "CTRL-PRIV-COLLECTION",
        "overseas_recipients_and_regions_mapped": "CTRL-PRIV-CROSS-BORDER",
        "retention_schedule_applied": "CTRL-PRIV-SECURITY-RETENTION",
        "destruction_or_deidentification_verified": "CTRL-PRIV-SECURITY-RETENTION",
        "technical_security_measures_implemented": "CTRL-PRIV-SECURITY-RETENTION",
        "organisational_security_measures_implemented": "CTRL-PRIV-SECURITY-RETENTION",
        "access_and_correction_timeframes_tracked": "CTRL-PRIV-ACCESS-CORRECTION",
        "controls_commensurate": "CTRL-SEC-COMMENSURATE",
        "security_roles_and_asset_owners_assigned": "CTRL-SEC-COMMENSURATE",
        "testing_program_exists": "CTRL-SEC-TESTING",
        "testing_scope_defined": "CTRL-SEC-TESTING",
        "incident_detection_defined": "CTRL-SEC-INCIDENT",
        "response_and_escalation_defined": "CTRL-SEC-INCIDENT",
        "provider_materiality_assessed": "CTRL-THIRD-PARTY-AI",
        "due_diligence_completed": "CTRL-THIRD-PARTY-AI",
        "contract_controls_defined": "CTRL-THIRD-PARTY-AI",
        "continuity_plan_tested": "CTRL-BCP-AI",
        "tolerance_and_fallback_defined": "CTRL-BCP-AI",
        "incidents_and_weaknesses_managed": "CTRL-OPS-RISK",
        "complaints_broadly_recognised": "CTRL-IDR-HANDLING",
        "complaints_recorded": "CTRL-IDR-HANDLING",
        "response_timeframes_enforced": "CTRL-IDR-HANDLING",
        "systemic_issues_escalated": "CTRL-IDR-SYSTEMIC",
        "fairness_and_explainability_metrics_evaluated": "CTRL-AI-DRIFT-MONITORING",
        "residual_risk_acceptance_and_drift_response_logged": "CTRL-AI-DRIFT-MONITORING",
        "article50_ai_interaction_transparency_provided": "CTRL-EU-HIGH-RISK",
        "deployer_human_oversight_assigned": "CTRL-EU-HIGH-RISK",
        "automatic_logs_retained_6months": "CTRL-EU-HIGH-RISK",
        "synthetic_content_marking_and_disclosure_applied": "CTRL-EU-HIGH-RISK",
        "article5_prohibited_practices_screened_out": "CTRL-EU-HIGH-RISK",
    }

    def __init__(
        self,
        ucl_path: Path | str | None = None,
        normative_mode: str = "revised",
    ) -> None:
        if ucl_path is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            ucl_path = repo_root / "UNIFIED_CONTROL_LIBRARY.json"

        assert normative_mode in {"revised", "historical_p1b1"}, (
            f"Unsupported normative_mode: {normative_mode}"
        )
        self.normative_mode = normative_mode

        with open(ucl_path, "r", encoding="utf-8") as f:
            ucl_data = json.load(f)

        self.canonical_controls: set[str] = {c["control_id"] for c in ucl_data["controls"]}
        self.canonical_facets: set[str] = set()
        self.facet_to_ucl_control: dict[str, str] = {}
        for c in ucl_data["controls"]:
            cid = c["control_id"]
            for f_name in c.get("control_facets", []):
                self.canonical_facets.add(f_name)
                self.facet_to_ucl_control[f_name] = cid

        # Verify all regex keys and mapped targets exist in UCL and match their UCL parent control
        assert set(self.FACET_REGEX_PATTERNS.keys()) == set(
            self.FACET_TO_CANONICAL_CONTROL.keys()
        ), "FACET_REGEX_PATTERNS and FACET_TO_CANONICAL_CONTROL keys must match"
        for f, cid in self.FACET_TO_CANONICAL_CONTROL.items():
            assert f in self.canonical_facets, f"Facet {f} not in UCL"
            assert cid in self.canonical_controls, f"Control {cid} not in UCL"
            assert self.facet_to_ucl_control.get(f) == cid, (
                f"Facet {f} mapped to {cid}, but UCL parent control is {self.facet_to_ucl_control.get(f)}"
            )

    def _detect_threshold(self, text: str) -> ThresholdAST | None:
        m = self.THRESHOLD_AMOUNT_PATTERN.search(text)
        if not m:
            return None
        amt_str = m.group(1).replace(",", "")
        amount = float(amt_str)

        lower = text.lower()
        if re.search(r"\b(at or above|at least|greater than or equal to|>=)\b", lower):
            op = ">="
        elif re.search(r"\b(exceeding|above|greater than|over|>)\b", lower):
            op = ">"
        elif re.search(r"\b(up to and including|at most|less than or equal to|<=)\b", lower):
            op = "<="
        elif re.search(r"\b(below|less than|<)\b", lower):
            op = "<"
        else:
            op = ">="

        curr = "AUD"
        if "usd" in lower:
            curr = "USD"
        elif "eur" in lower:
            curr = "EUR"
        elif "gbp" in lower:
            curr = "GBP"

        return ThresholdAST(amount=amount, operator=op, currency=curr)

    def classify_normative_modality(self, text: str) -> tuple[str, bool]:
        """Classify clause text into normative modality and determine suppression status.

        In default 'revised' mode, distinguishes protective prohibitions (which express
        preventive security, privacy, or approval controls and must NOT be suppressed)
        from control prohibitions, waivers, exemptions, optional guidance, aspirational
        statements, and statements of missing implementation (which MUST be suppressed).

        Returns:
            Tuple of (detected_normative_type, should_suppress_candidates)
        """
        is_conditional_block = bool(self.CONDITIONAL_BLOCK_PATTERN.search(text))

        if self.normative_mode == "historical_p1b1":
            if self.PROHIBITION_ABSOLUTE_PATTERN.search(text) and not is_conditional_block:
                return "prohibition_absolute", True
            if (
                self.SCOPE_EXEMPTION_PATTERN.search(text)
                and not is_conditional_block
                and (
                    not self.MANDATORY_PATTERN.search(text)
                    or "exempt from" in text.lower()
                    or "excluded from" in text.lower()
                )
            ):
                return "scope_exemption", True
            if self.PERMISSIVE_GUIDANCE_PATTERN.search(text) and not self.MANDATORY_PATTERN.search(text):
                return "permissive_guidance", True
            if self.ASPIRATIONAL_PATTERN.search(text) and not self.MANDATORY_PATTERN.search(text):
                return "aspirational_statement", True
            if is_conditional_block:
                if "shall not proceed without" in text.lower() or "must not disburse" in text.lower():
                    return "prohibition_conditional", True
                return "affirmative_obligation", False
            return "affirmative_obligation", False

        # Revised v0.2.0 Evidence-Preserving Normative Modality Classification:
        # 1. Control Prohibitions (forbidding a beneficial governance/security control)
        if self.CONTROL_PROHIBITION_PATTERN.search(text):
            return "control_prohibition", True

        # 2. Unmapped Out-of-Scope Prohibitions
        if self.UNMAPPED_PROHIBITION_PATTERN.search(text):
            return "unmapped_prohibition", True

        # 3. Control Waivers
        if self.CONTROL_WAIVER_PATTERN.search(text):
            return "control_waiver", True

        # 4. Statements of Missing Implementation or Non-Applicability
        if self.MISSING_IMPLEMENTATION_PATTERN.search(text):
            return "missing_implementation", True

        # 5. Scope Exemptions
        if (
            self.SCOPE_EXEMPTION_PATTERN.search(text)
            and not is_conditional_block
            and (
                not self.MANDATORY_PATTERN.search(text)
                or "exempt from" in text.lower()
                or "excluded from" in text.lower()
                or "not classified as" in text.lower()
            )
        ):
            return "scope_exemption", True

        # 6. Permissive / Optional Guidance
        if self.PERMISSIVE_GUIDANCE_PATTERN.search(text) and not self.MANDATORY_PATTERN.search(text):
            return "permissive_guidance", True

        # 7. Aspirational Statements
        if self.ASPIRATIONAL_PATTERN.search(text) and not self.MANDATORY_PATTERN.search(text):
            return "aspirational_statement", True

        # 8. Protective Prohibitions & Conditional Pre-Execution Gates (DO NOT suppress!)
        if self.PROTECTIVE_PROHIBITION_PATTERN.search(text) or (
            is_conditional_block
            and re.search(r"\b(must not|shall not|cannot|prohibited)\b", text, re.IGNORECASE)
        ):
            return "protective_prohibition", False

        # 9. Remaining generic absolute prohibitions without a protective control target
        if self.PROHIBITION_ABSOLUTE_PATTERN.search(text) and not is_conditional_block:
            return "prohibition_absolute", True

        return "affirmative_obligation", False

    def extract_and_map(
        self,
        input_text: str,
        case_id: str = "",
    ) -> ExtractionResult:
        """Execute enhanced deterministic extraction, ranking, and candidate suppression."""
        t0 = time.perf_counter()

        # Step 1: Modality classification & suppression check
        norm_type, should_suppress = self.classify_normative_modality(input_text)

        threshold_ast = self._detect_threshold(input_text)

        if should_suppress:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return ExtractionResult(
                case_id=case_id,
                extracted_clauses=[input_text.strip()],
                candidate_facets=[],
                candidate_controls=[],
                ranked_mappings=[],
                threshold_ast=threshold_ast,
                is_suppressed=True,
                detected_normative_type=norm_type,
                execution_time_ms=elapsed_ms,
            )

        # Step 2: Facet Pattern Matching
        matched_facets: list[str] = []
        for facet_name, patterns in self.FACET_REGEX_PATTERNS.items():
            for pat in patterns:
                if pat.search(input_text):
                    matched_facets.append(facet_name)
                    break

        if threshold_ast and "approval_threshold_defined" not in matched_facets:
            matched_facets.append("approval_threshold_defined")

        # Step 3: Canonical Control Resolution & Ranking
        control_scores: dict[str, float] = {}
        facet_attribution: dict[str, list[str]] = {}

        for facet in matched_facets:
            cid = self.FACET_TO_CANONICAL_CONTROL.get(facet)
            if cid:
                control_scores[cid] = control_scores.get(cid, 0.0) + 1.0
                facet_attribution.setdefault(cid, []).append(facet)

        # Special domain combinations
        # 1. When financial threshold and human approval are present, prioritize CTRL-DELEGATED-AUTHORITY-THRESHOLD
        if "approval_threshold_defined" in matched_facets and "human_approval_required" in matched_facets:
            control_scores["CTRL-DELEGATED-AUTHORITY-THRESHOLD"] = (
                control_scores.get("CTRL-DELEGATED-AUTHORITY-THRESHOLD", 0.0) + 2.0
            )
            # Also surface CTRL-HUMAN-OVERSIGHT as secondary candidate when joint/dual human review is required
            if "CTRL-HUMAN-OVERSIGHT" not in control_scores:
                control_scores["CTRL-HUMAN-OVERSIGHT"] = 0.5
                facet_attribution["CTRL-HUMAN-OVERSIGHT"] = ["human_approval_required"]

        # 2. When manual override / escalation is matched without a financial threshold, prioritize CTRL-HUMAN-OVERSIGHT
        if (
            "clear_escalation_and_override_authority" in matched_facets
            and "approval_threshold_defined" not in matched_facets
        ):
            control_scores["CTRL-HUMAN-OVERSIGHT"] = (
                control_scores.get("CTRL-HUMAN-OVERSIGHT", 0.0) + 1.5
            )

        # 3. When explicit retention schedule is paired with audit logging (without officer approval gate), prioritize CTRL-PRIV-SECURITY-RETENTION
        if (
            "retention_schedule_applied" in matched_facets
            and "approval_logs_retained" in matched_facets
            and "human_approval_required" not in matched_facets
        ):
            control_scores["CTRL-PRIV-SECURITY-RETENTION"] = (
                control_scores.get("CTRL-PRIV-SECURITY-RETENTION", 0.0) + 1.5
            )

        # Sort candidate controls by score descending
        sorted_controls = sorted(control_scores.keys(), key=lambda c: control_scores[c], reverse=True)

        ranked_mappings: list[CandidatePrediction] = []
        for rank_idx, cid in enumerate(sorted_controls):
            facets_for_c = facet_attribution.get(cid, [])
            primary_facet = facets_for_c[0] if facets_for_c else None
            score = round(control_scores[cid] / (rank_idx + 1.0), 3)

            pred = CandidatePrediction(
                clause_id=f"POL-{case_id or '01'}",
                canonical_control_id=cid,
                canonical_facet_id=primary_facet,
                score=score,
                review_status="proposed",  # Strict governance invariant
                normative_type=norm_type,
                is_suppressed=False,
                is_ambiguous=False,
                rationale=f"Enhanced rule matched canonical facets: {facets_for_c}",
                threshold_ast=threshold_ast,
            )
            ranked_mappings.append(pred)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return ExtractionResult(
            case_id=case_id,
            extracted_clauses=[input_text.strip()],
            candidate_facets=matched_facets,
            candidate_controls=sorted_controls,
            ranked_mappings=ranked_mappings,
            threshold_ast=threshold_ast,
            is_suppressed=len(sorted_controls) == 0,
            detected_normative_type=norm_type,
            execution_time_ms=elapsed_ms,
        )
