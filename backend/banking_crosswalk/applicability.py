"""Deterministic four-state applicability rules.

The rules select candidates for legal review; they do not make a final legal
determination.  Ambiguity is deliberately retained as conditional or
undetermined rather than silently excluded from a coverage denominator.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Dict, Iterable, Tuple

from .models import (
    ApplicabilityDecision,
    ApplicabilityStatus,
    AtomicObligation,
    BankingUseCase,
)


RuleResult = Tuple[ApplicabilityStatus, str]


def _privacy(use_case: BankingUseCase, _: AtomicObligation) -> RuleResult:
    value = use_case.handles_personal_information
    if value is True:
        return ApplicabilityStatus.APPLICABLE, "Use case handles personal information."
    if value is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Use case is confirmed not to handle personal information.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "Personal-information handling has not been confirmed.",
    )


def _privacy_automated_future(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    if (
        use_case.handles_personal_information is False
        or use_case.makes_or_assists_significant_decisions is False
    ):
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Required personal-information/significant-decision conditions are not present.",
        )
    if (
        use_case.handles_personal_information is None
        or use_case.makes_or_assists_significant_decisions is None
    ):
        return (
            ApplicabilityStatus.UNDETERMINED,
            "Personal-information and significant-decision conditions need confirmation.",
        )
    if obligation.effective_from and use_case.as_of_date < obligation.effective_from:
        return (
            ApplicabilityStatus.CONDITIONAL,
            f"Conditions are indicated but the provision is future-dated to {obligation.effective_from.isoformat()}.",
        )
    return (
        ApplicabilityStatus.APPLICABLE,
        "Personal information is used in a potentially significant automated decision after commencement.",
    )


def _apra(use_case: BankingUseCase, _: AtomicObligation) -> RuleResult:
    if use_case.apra_regulated is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Entity is confirmed to be APRA regulated.",
        )
    if use_case.apra_regulated is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Entity is confirmed not to be APRA regulated.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "APRA-regulated entity status has not been confirmed.",
    )


def _apra_critical(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    base, reason = _apra(use_case, obligation)
    if base is not ApplicabilityStatus.APPLICABLE:
        return base, reason
    if use_case.supports_critical_operation is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "APRA entity and AI dependency on a critical operation are confirmed.",
        )
    if use_case.supports_critical_operation is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "AI use case is confirmed not to support a critical operation.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "Critical-operation dependency has not been assessed.",
    )


def _apra_third_party(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    base, reason = _apra(use_case, obligation)
    if base is not ApplicabilityStatus.APPLICABLE:
        return base, reason
    if use_case.third_party_ai_service is False:
        return ApplicabilityStatus.NOT_APPLICABLE, "No third-party AI service is used."
    if use_case.third_party_ai_service is None:
        return (
            ApplicabilityStatus.UNDETERMINED,
            "Third-party AI dependency has not been confirmed.",
        )
    if use_case.material_service_provider is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Third-party AI provider is confirmed material under the CPS 230 framework.",
        )
    if use_case.material_service_provider is False:
        return (
            ApplicabilityStatus.CONDITIONAL,
            "Third-party service exists; materiality and any retained CPS 230 duties require review.",
        )
    return (
        ApplicabilityStatus.CONDITIONAL,
        "Third-party AI service exists but CPS 230 materiality has not been determined.",
    )


def _asic_idr(use_case: BankingUseCase, _: AtomicObligation) -> RuleResult:
    if use_case.idr_obligations is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Entity/use case is confirmed within an applicable IDR obligation.",
        )
    if use_case.idr_obligations is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "The relevant IDR obligation is confirmed not to apply.",
        )
    if use_case.handles_regulated_complaints is True:
        return (
            ApplicabilityStatus.CONDITIONAL,
            "The use case handles complaints, but the entity/licence-specific IDR duty needs confirmation.",
        )
    if use_case.handles_regulated_complaints is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Use case is confirmed not to handle regulated complaints.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "Complaint function and entity/licence-specific IDR duties are unknown.",
    )


def _eu(use_case: BankingUseCase, _: AtomicObligation) -> RuleResult:
    nexus_values = [use_case.eu_establishment_or_market, use_case.eu_output_used]
    if all(value is False for value in nexus_values):
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "No Article 2 EU establishment, market or output-use nexus is indicated.",
        )
    if any(value is True for value in nexus_values):
        if use_case.eu_deployer_or_provider_role is True:
            return (
                ApplicabilityStatus.CONDITIONAL,
                "EU nexus and a regulated role are indicated; classification and phased commencement require Legal confirmation.",
            )
        if use_case.eu_deployer_or_provider_role is False:
            return (
                ApplicabilityStatus.NOT_APPLICABLE,
                "An EU nexus exists but no relevant provider/deployer role is confirmed.",
            )
        return (
            ApplicabilityStatus.CONDITIONAL,
            "EU nexus is indicated; role, classification and commencement must be determined.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "EU territorial nexus has not been fully assessed.",
    )


def _nist(use_case: BankingUseCase, _: AtomicObligation) -> RuleResult:
    if use_case.nist_ai_rmf_adopted is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Organisation has adopted NIST AI RMF as an internal benchmark.",
        )
    if use_case.nist_ai_rmf_adopted is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "NIST AI RMF is voluntary and has not been selected as an internal requirement.",
        )
    return ApplicabilityStatus.UNDETERMINED, "NIST AI RMF adoption status is unknown."


def _iso(use_case: BankingUseCase, obligation: AtomicObligation) -> RuleResult:
    if use_case.iso_42001_adopted is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "ISO/IEC 42001 is voluntary and has not been adopted.",
        )
    if use_case.iso_42001_adopted is None:
        return (
            ApplicabilityStatus.UNDETERMINED,
            "ISO/IEC 42001 adoption status is unknown.",
        )
    if (
        obligation.assessment_scope == "organisation"
        and use_case.assessment_scope != "organisation"
    ):
        return (
            ApplicabilityStatus.CONDITIONAL,
            "The standard is adopted, but this obligation requires organisation-scope evidence outside a use-case questionnaire.",
        )
    return (
        ApplicabilityStatus.APPLICABLE,
        "ISO/IEC 42001 is adopted and the assessment scope is compatible.",
    )


def _privacy_cross_border(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    base, reason = _privacy(use_case, obligation)
    if base is not ApplicabilityStatus.APPLICABLE:
        return base, reason
    if use_case.cross_border_disclosure is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Personal information is disclosed to or processed by an overseas recipient.",
        )
    if use_case.cross_border_disclosure is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Personal information is confirmed not to be disclosed to overseas recipients.",
        )
    if use_case.third_party_ai_service is True:
        return (
            ApplicabilityStatus.CONDITIONAL,
            "Personal information and a third-party AI service are used; overseas hosting, inference or subprocessor access under APP 8 must be confirmed.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "Cross-border personal-information disclosure status has not been confirmed.",
    )


def _asic_afs_licensee(
    use_case: BankingUseCase, _: AtomicObligation
) -> RuleResult:
    if use_case.afs_licensee is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Entity holds an Australian Financial Services Licence (AFSL) and the activity falls within financial services conduct obligations.",
        )
    if use_case.afs_licensee is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Entity or use case is confirmed outside AFSL financial services obligations.",
        )
    if use_case.apra_regulated is True or use_case.entity_type.upper() == "ADI":
        return (
            ApplicabilityStatus.CONDITIONAL,
            "Entity is an APRA-regulated institution/ADI; confirm AFSL scope and s 912A(1) applicability for this workflow.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "AFSL holder status and financial-service scope have not been confirmed.",
    )


def _nccp_credit_activity(
    use_case: BankingUseCase, _: AtomicObligation
) -> RuleResult:
    if use_case.credit_licensee_or_credit_activity is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Entity holds an Australian Credit Licence (ACL) or engages in regulated credit activities under the NCCP Act.",
        )
    if use_case.credit_licensee_or_credit_activity is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Use case does not involve regulated consumer credit activities under the NCCP Act.",
        )
    if use_case.entity_type.upper() == "ADI" or use_case.apra_regulated is True:
        return (
            ApplicabilityStatus.CONDITIONAL,
            "Entity is an ADI/APRA-regulated institution; confirm whether the AI workflow engages in regulated credit activities under s 47 of the NCCP Act.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "Australian Credit Licence (ACL) status and regulated credit-activity scope are unknown.",
    )


def _nccp_responsible_lending(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    if (
        use_case.credit_licensee_or_credit_activity is False
        or use_case.assists_consumer_credit_decision is False
    ):
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Use case does not enter into, increase or assess consumer credit contracts under Chapter 3 of the NCCP Act.",
        )
    if (
        use_case.credit_licensee_or_credit_activity is True
        and use_case.assists_consumer_credit_decision is True
    ):
        return (
            ApplicabilityStatus.APPLICABLE,
            "Use case assists or executes consumer credit assessments subject to NCCP Act ss 128-131 responsible lending obligations.",
        )
    if (
        use_case.credit_licensee_or_credit_activity is True
        and use_case.makes_or_assists_significant_decisions is True
    ):
        return (
            ApplicabilityStatus.CONDITIONAL,
            "Entity is a credit licensee and the AI assists significant decisions; confirm whether consumer credit contract entry or limit increases are in scope.",
        )
    return _nccp_credit_activity(use_case, obligation)


def _au_ai_guidance(
    use_case: BankingUseCase, _: AtomicObligation
) -> RuleResult:
    if use_case.au_ai_guidance_adopted is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Organisation has adopted the Australian Government Guidance for AI Adoption (Oct 2025) as a governance benchmark.",
        )
    if use_case.au_ai_guidance_adopted is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Australian Government Guidance for AI Adoption is non-binding and has not been selected for this assessment.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "Adoption of the Australian Government Guidance for AI Adoption (Oct 2025) has not been specified.",
    )


def _eu_prohibited_or_literacy(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    base, reason = _eu(use_case, obligation)
    if base is ApplicabilityStatus.NOT_APPLICABLE:
        return base, reason
    if base is ApplicabilityStatus.CONDITIONAL:
        return (
            ApplicabilityStatus.CONDITIONAL,
            "EU Article 2 nexus is indicated; Chapter I/II AI literacy (Art 4) and prohibited practice screening (Art 5, applicable from 2 Feb 2025) require Legal confirmation.",
        )
    return base, reason


def _eu_deployer_high_risk(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    base, reason = _eu(use_case, obligation)
    if base is ApplicabilityStatus.NOT_APPLICABLE:
        return base, reason
    if use_case.eu_operator_role == "none":
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Entity has confirmed no operator role under the EU AI Act.",
        )
    if base is ApplicabilityStatus.CONDITIONAL:
        if obligation.effective_from and use_case.as_of_date < obligation.effective_from:
            return (
                ApplicabilityStatus.CONDITIONAL,
                f"EU nexus is indicated; deployer/high-risk provisions are phased to {obligation.effective_from.isoformat()}.",
            )
        return (
            ApplicabilityStatus.CONDITIONAL,
            "EU nexus is indicated; Annex III point 5(b) creditworthiness/credit-scoring classification and Articles 26-27 deployer duties require Legal confirmation.",
        )
    return base, reason


def _iso23894(use_case: BankingUseCase, _: AtomicObligation) -> RuleResult:
    if use_case.iso_23894_adopted is True:
        return (
            ApplicabilityStatus.APPLICABLE,
            "Organisation has adopted ISO/IEC 23894:2023 as an AI risk management benchmark.",
        )
    if use_case.iso_23894_adopted is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "ISO/IEC 23894:2023 is voluntary and has not been adopted.",
        )
    if use_case.iso_42001_adopted is True:
        return (
            ApplicabilityStatus.CONDITIONAL,
            "ISO/IEC 42001 is adopted; confirm whether ISO/IEC 23894 risk management guidance is also used as a supporting reference.",
        )
    return (
        ApplicabilityStatus.UNDETERMINED,
        "ISO/IEC 23894:2023 adoption status is unknown.",
    )


def _iso27001(
    use_case: BankingUseCase, obligation: AtomicObligation
) -> RuleResult:
    if use_case.iso_27001_adopted is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "ISO/IEC 27001:2022 is voluntary and has not been adopted.",
        )
    if use_case.iso_27001_adopted is None:
        return (
            ApplicabilityStatus.UNDETERMINED,
            "ISO/IEC 27001:2022 adoption status is unknown.",
        )
    if (
        obligation.assessment_scope == "organisation"
        and use_case.assessment_scope != "organisation"
    ):
        return (
            ApplicabilityStatus.CONDITIONAL,
            "ISO/IEC 27001:2022 is adopted, but this obligation requires organisation-scope ISMS evidence outside a use-case questionnaire.",
        )
    return (
        ApplicabilityStatus.APPLICABLE,
        "ISO/IEC 27001:2022 is adopted and the assessment scope is compatible.",
    )


def _enterprise_delegated_authority(
    use_case: BankingUseCase, _: AtomicObligation
) -> RuleResult:
    if use_case.enterprise_controls_enabled is False:
        return (
            ApplicabilityStatus.NOT_APPLICABLE,
            "Enterprise delegated-authority payment/refund control is confirmed not applicable to this workflow.",
        )
    if (
        use_case.enterprise_controls_enabled is True
        or use_case.approval_threshold_aud is not None
    ):
        return (
            ApplicabilityStatus.APPLICABLE,
            "Enterprise delegated-authority control applies based on configured approval threshold or enterprise control baseline.",
        )
    return (
        ApplicabilityStatus.CONDITIONAL,
        "Confirm whether the AI system can initiate, recommend or execute financial transactions subject to enterprise delegated authority.",
    )


RULES: Dict[str, Callable[[BankingUseCase, AtomicObligation], RuleResult]] = {
    "privacy_personal_information": _privacy,
    "privacy_automated_decision_future": _privacy_automated_future,
    "privacy_cross_border": _privacy_cross_border,
    "apra_entity": _apra,
    "apra_critical_operation": _apra_critical,
    "apra_third_party_service": _apra_third_party,
    "asic_idr": _asic_idr,
    "asic_afs_licensee": _asic_afs_licensee,
    "nccp_credit_activity": _nccp_credit_activity,
    "nccp_responsible_lending": _nccp_responsible_lending,
    "au_ai_guidance_adopted": _au_ai_guidance,
    "eu_ai_act_nexus": _eu,
    "eu_ai_act_prohibited_or_literacy": _eu_prohibited_or_literacy,
    "eu_ai_act_deployer_high_risk": _eu_deployer_high_risk,
    "nist_adopted": _nist,
    "iso42001_adopted": _iso,
    "iso23894_adopted": _iso23894,
    "iso27001_adopted": _iso27001,
    "enterprise_delegated_authority": _enterprise_delegated_authority,
}


def decide_applicability(
    obligation: AtomicObligation, use_case: BankingUseCase
) -> ApplicabilityDecision:
    if (
        obligation.effective_to
        and obligation.effective_to not in {"NONE_CURRENT", "UNKNOWN", "N/A"}
    ):
        try:
            eff_to = date.fromisoformat(str(obligation.effective_to))
            if use_case.as_of_date > eff_to:
                replacement = (
                    f" (replaced by {obligation.superseded_by})"
                    if obligation.superseded_by
                    else ""
                )
                return ApplicabilityDecision(
                    obligation_id=obligation.obligation_id,
                    status=ApplicabilityStatus.NOT_APPLICABLE,
                    reason=f"Obligation version was superseded after {eff_to.isoformat()}{replacement}.",
                    authority=obligation.authority,
                    assessment_scope=obligation.assessment_scope,
                    rule_key=obligation.applicability_key,
                )
        except ValueError:
            pass
    rule = RULES.get(obligation.applicability_key)
    if rule is None:
        status, reason = (
            ApplicabilityStatus.UNDETERMINED,
            "No deterministic rule is configured; expert review is required.",
        )
    else:
        status, reason = rule(use_case, obligation)
    return ApplicabilityDecision(
        obligation_id=obligation.obligation_id,
        status=status,
        reason=reason,
        authority=obligation.authority,
        assessment_scope=obligation.assessment_scope,
        rule_key=obligation.applicability_key,
    )


def select_applicable_obligations(
    obligations: Iterable[AtomicObligation], use_case: BankingUseCase
) -> list[ApplicabilityDecision]:
    return [decide_applicability(obligation, use_case) for obligation in obligations]
