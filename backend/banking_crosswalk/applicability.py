"""Deterministic four-state applicability rules.

The rules select candidates for legal review; they do not make a final legal
determination.  Ambiguity is deliberately retained as conditional or
undetermined rather than silently excluded from a coverage denominator.
"""

from __future__ import annotations

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
        "ISO/IEC 42001 is adopted and the assessment is organisation-scoped.",
    )


RULES: Dict[str, Callable[[BankingUseCase, AtomicObligation], RuleResult]] = {
    "privacy_personal_information": _privacy,
    "privacy_automated_decision_future": _privacy_automated_future,
    "apra_entity": _apra,
    "apra_critical_operation": _apra_critical,
    "apra_third_party_service": _apra_third_party,
    "asic_idr": _asic_idr,
    "eu_ai_act_nexus": _eu,
    "nist_adopted": _nist,
    "iso42001_adopted": _iso,
}


def decide_applicability(
    obligation: AtomicObligation, use_case: BankingUseCase
) -> ApplicabilityDecision:
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
