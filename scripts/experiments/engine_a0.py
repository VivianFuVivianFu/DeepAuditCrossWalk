"""Historical Production Baseline Engine (A0).

Executes the unchanged production deterministic extraction algorithm from
backend/banking_crosswalk/policy.py via the CanonicalMappingAdapter.
Strictly read-only with respect to production code.
"""

from __future__ import annotations

import time

from banking_crosswalk.policy import extract_enterprise_policy

from .canonical_adapter import CanonicalMappingAdapter
from .models import ExtractionResult


class EngineA0:
    """Historical Production Deterministic Baseline Engine (A0).

    Invokes production extract_enterprise_policy() and translates legacy identifiers
    through the CanonicalMappingAdapter.
    """

    def __init__(self, adapter: CanonicalMappingAdapter | None = None) -> None:
        self.adapter = adapter or CanonicalMappingAdapter()

    def extract_and_map(
        self,
        input_text: str,
        case_id: str = "",
    ) -> ExtractionResult:
        """Execute production baseline extraction and canonical adaptation."""
        t0 = time.perf_counter()

        policy_pack = extract_enterprise_policy(
            tenant_id="p1b-experiment-tenant",
            name="experiment-clause",
            text=input_text,
        )

        extraction_res = self.adapter.adapt_enterprise_clauses(
            clauses=policy_pack.clauses,
            case_id=case_id,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        extraction_res.execution_time_ms = elapsed_ms

        return extraction_res
