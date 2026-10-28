"""DeepAudit Banking Regulatory Crosswalk MVP.

The package is intentionally independent from the NSW AIAF readiness engine.
It reuses the question catalogue as an immutable source, then overlays banking
obligations, applicability decisions, mappings and human review records.
"""

from .applicability import select_applicable_obligations
from .catalog import load_aiaf_question_bank, load_regulatory_pack
from .coverage import evaluate_questionnaire_coverage

__all__ = [
    "evaluate_questionnaire_coverage",
    "load_aiaf_question_bank",
    "load_regulatory_pack",
    "select_applicable_obligations",
]
