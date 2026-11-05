"""Canonical Mapping Adapter for Phase P1B Experiments.

Authoritatively translates legacy production control and facet identifiers into
the 33 Canonical Unified Controls and 155 Canonical Facets defined in
UNIFIED_CONTROL_LIBRARY.json.

Preserves the invariant that ambiguous legacy targets are flagged as unresolved
rather than silently forced.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from .models import CandidatePrediction, ExtractionResult, ThresholdAST


class CanonicalMappingAdapter:
    """Translates legacy heuristic engine identifiers into canonical UCL identifiers."""

    # Explicit 1:1 Verified Legacy-to-Canonical Control Mapping
    VERIFIED_CONTROL_ALIASES: ClassVar[dict[str, str]] = {
        "CTRL-FIN-APPROVAL-THRESHOLDS": "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "CTRL-GOV-OVERSIGHT": "CTRL-HUMAN-OVERSIGHT",
        "CTRL-FAIR-BIAS-DETECTION": "CTRL-AI-DRIFT-MONITORING",
        "CTRL-FAIR-BIAS-EVALUATION": "CTRL-AI-DRIFT-MONITORING",
        "CTRL-DATA-RETENTION-DISPOSAL": "CTRL-PRIV-SECURITY-RETENTION",
        "CTRL-COMPL-DISPUTE-RESOLUTION": "CTRL-IDR-HANDLING",
        "CTRL-GOV-AUDITABILITY": "CTRL-INDEPENDENT-AUDIT-ASSURANCE",
        "CTRL-DATA-PRIVACY-RIGHTS": "CTRL-PRIV-ACCESS-CORRECTION",
        "CTRL-TECH-INCIDENT-RESPONSE": "CTRL-SEC-INCIDENT",
        "CTRL-TECH-ACCESS-SECURITY": "CTRL-SEC-COMMENSURATE",
        "CTRL-TPS-VENDOR-ASSESSMENT": "CTRL-THIRD-PARTY-AI",
        "CTRL-OPS-OUTSOURCING": "CTRL-THIRD-PARTY-AI",
        # Exact Canonical Controls that may appear in legacy text
        "CTRL-PRIV-CROSS-BORDER": "CTRL-PRIV-CROSS-BORDER",
        "CTRL-PRIV-COLLECTION": "CTRL-PRIV-COLLECTION",
    }

    # Ambiguous Legacy Control Identifiers (Must NOT be silently resolved)
    AMBIGUOUS_CONTROL_ALIASES: ClassVar[dict[str, list[str]]] = {
        "CTRL-GOV-FRAMEWORK": [
            "CTRL-RISK-FRAMEWORK",
            "CTRL-AI-GOV-ACCOUNTABILITY",
            "CTRL-INDEPENDENT-AUDIT-ASSURANCE",
        ],
        "CTRL-TECH-OBSERVABILITY": [
            "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
            "CTRL-AI-DRIFT-MONITORING",
            "CTRL-SEC-INCIDENT",
        ],
    }

    # Facet Translations to Canonical UCL Facets
    # 3 Exact Canonical String Matches:
    #   human_approval_required, approval_threshold_defined, pre_execution_block
    # Verified Aliases to 155 Canonical Facets:
    FACET_TRANSLATIONS: ClassVar[dict[str, list[str]]] = {
        "human_approval_required": ["human_approval_required"],
        "approval_threshold_defined": ["approval_threshold_defined"],
        "pre_execution_block": ["pre_execution_block"],
        "zero_data_retention": [
            "retention_schedule_applied",
            "destruction_or_deidentification_verified",
        ],
        "prompt_logging": [
            "approval_logs_retained",
            "incident_detection_defined",
        ],
        "bias_testing": [
            "fairness_and_explainability_metrics_evaluated",
        ],
        "model_inventory": [
            "use_case_registered_in_enterprise_ai_inventory",
            "ai_assets_classified_by_criticality_and_sensitivity",
        ],
        "data_sovereignty": [
            "overseas_recipients_and_regions_mapped",
        ],
    }

    def __init__(self, ucl_path: Path | str | None = None) -> None:
        if ucl_path is None:
            # Default to repo root UNIFIED_CONTROL_LIBRARY.json
            repo_root = Path(__file__).resolve().parent.parent.parent
            ucl_path = repo_root / "UNIFIED_CONTROL_LIBRARY.json"

        with open(ucl_path, "r", encoding="utf-8") as f:
            ucl_data = json.load(f)

        self.controls_data: list[dict[str, Any]] = ucl_data.get("controls", [])
        self.canonical_controls: set[str] = {c["control_id"] for c in self.controls_data}
        self.canonical_facets: set[str] = set()
        self.control_to_facets: dict[str, list[str]] = {}
        self.facet_to_control: dict[str, str] = {}

        for c in self.controls_data:
            cid = c["control_id"]
            facets = c.get("control_facets", [])
            self.control_to_facets[cid] = list(facets)
            for f_name in facets:
                self.canonical_facets.add(f_name)
                # First control claiming facet or canonical binding
                if f_name not in self.facet_to_control:
                    self.facet_to_control[f_name] = cid

        self._validate_adapter_integrity()

    def _validate_adapter_integrity(self) -> None:
        """Verify that all target controls and facets in adapter exist in the UCL."""
        assert len(self.canonical_controls) == 33, (
            f"Expected 33 Canonical Controls in UCL, found {len(self.canonical_controls)}"
        )
        assert len(self.canonical_facets) == 155, (
            f"Expected 155 Canonical Facets in UCL, found {len(self.canonical_facets)}"
        )

        for legacy_id, canonical_id in self.VERIFIED_CONTROL_ALIASES.items():
            assert canonical_id in self.canonical_controls, (
                f"Adapter target control '{canonical_id}' (from '{legacy_id}') not found in UCL"
            )

        for legacy_f, canonical_list in self.FACET_TRANSLATIONS.items():
            for cf in canonical_list:
                assert cf in self.canonical_facets, (
                    f"Adapter target facet '{cf}' (from '{legacy_f}') not found in UCL"
                )

    def resolve_control_id(self, identifier: str) -> tuple[str | None, bool, str]:
        """Resolve a legacy or canonical control ID.

        Returns:
            Tuple of (canonical_id, is_ambiguous, explanation)
        """
        # 1. Already a valid Canonical Control ID
        if identifier in self.canonical_controls:
            return identifier, False, "Exact canonical control ID match."

        # 2. Known verified legacy alias
        if identifier in self.VERIFIED_CONTROL_ALIASES:
            canonical_id = self.VERIFIED_CONTROL_ALIASES[identifier]
            return canonical_id, False, f"Resolved via verified legacy alias to '{canonical_id}'."

        # 3. Known ambiguous legacy identifier
        if identifier in self.AMBIGUOUS_CONTROL_ALIASES:
            candidates = self.AMBIGUOUS_CONTROL_ALIASES[identifier]
            return (
                None,
                True,
                f"Ambiguous legacy identifier '{identifier}' maps to multiple canonical targets: {candidates}. Kept unresolved.",
            )

        # 4. Unknown identifier
        return None, False, f"Unknown control identifier '{identifier}' outside canonical UCL."

    def resolve_facets(self, facet_name: str) -> list[str]:
        """Translate a legacy or canonical facet into canonical UCL facet(s)."""
        # Exact match in UCL
        if facet_name in self.canonical_facets:
            return [facet_name]

        # In translation table
        if facet_name in self.FACET_TRANSLATIONS:
            return list(self.FACET_TRANSLATIONS[facet_name])

        return []

    def adapt_enterprise_clauses(
        self,
        clauses: Sequence[Any],
        case_id: str = "",
    ) -> ExtractionResult:
        """Adapt production EnterpriseClause objects into a standardised ExtractionResult.

        Translates legacy control mappings and facet strings into canonical representations.
        Preserves review_status='proposed'.
        """
        extracted_clauses: list[str] = []
        candidate_facets: list[str] = []
        candidate_controls: list[str] = []
        ranked_mappings: list[CandidatePrediction] = []
        detected_threshold: ThresholdAST | None = None
        is_suppressed = False

        seen_facets: set[str] = set()
        seen_controls: set[str] = set()

        for clause in clauses:
            extracted_clauses.append(clause.text)

            # Check threshold attributes from EnterpriseClause
            if getattr(clause, "thresholds_aud", None) and detected_threshold is None:
                op = getattr(clause, "threshold_operator", None) or ">="
                curr = getattr(clause, "threshold_currency", None) or "AUD"
                detected_threshold = ThresholdAST(
                    amount=float(clause.thresholds_aud[0]),
                    operator=op,
                    currency=curr,
                )

            # Check raw control_facets
            for raw_f in getattr(clause, "control_facets", []):
                canon_facets = self.resolve_facets(raw_f)
                for cf in canon_facets:
                    if cf not in seen_facets:
                        seen_facets.add(cf)
                        candidate_facets.append(cf)

            # Check control_mappings
            mappings = getattr(clause, "control_mappings", [])
            for m in mappings:
                legacy_cid = getattr(m, "control_id", "")
                canon_cid, is_ambiguous, reason = self.resolve_control_id(legacy_cid)

                pred = CandidatePrediction(
                    clause_id=clause.clause_id,
                    canonical_control_id=canon_cid,
                    canonical_facet_id=candidate_facets[0] if candidate_facets else None,
                    score=1.0 if not is_ambiguous else 0.5,
                    review_status="proposed",
                    is_ambiguous=is_ambiguous,
                    rationale=f"{m.rationale} | {reason}",
                    threshold_ast=detected_threshold,
                )
                ranked_mappings.append(pred)

                if canon_cid and not is_ambiguous and canon_cid not in seen_controls:
                    seen_controls.add(canon_cid)
                    candidate_controls.append(canon_cid)

        # If zero candidate controls and zero candidate facets were produced, or if all clauses were unmapped
        if not candidate_controls and not candidate_facets:
            is_suppressed = True

        return ExtractionResult(
            case_id=case_id,
            extracted_clauses=extracted_clauses,
            candidate_facets=candidate_facets,
            candidate_controls=candidate_controls,
            ranked_mappings=ranked_mappings,
            threshold_ast=detected_threshold,
            is_suppressed=is_suppressed,
        )
