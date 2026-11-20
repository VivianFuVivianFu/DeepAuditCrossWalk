"""Canonical Mapping Adapter for Phase P1B Experiments.

Authoritatively translates legacy production control and facet identifiers into
the Canonical Unified Controls and Canonical Facets defined dynamically in
UNIFIED_CONTROL_LIBRARY.json.

Preserves the invariant that ambiguous legacy targets are flagged as unresolved
rather than silently forced.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar

from .models import CandidatePrediction, ExtractionResult, ThresholdAST


@dataclass(frozen=True)
class FacetMigrationRecord:
    """Audit record for version-aware facet migration to Regulatory Pack v0.2.0."""

    original_facet: str
    source_taxonomy_version: str
    target_taxonomy_version: str
    migration_kind: str
    emitted_facets: list[str]
    unresolved_candidate_facets: list[str]
    canonical_control_id: str | None
    source_text: str
    mapping_reason: str
    requires_human_review: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    # Verified Aliases to Canonical UCL Facets:
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

    # Exact 1:1 legacy-to-canonical facet renames
    EXACT_FACET_RENAMES: ClassVar[dict[str, str]] = {
        "bias_testing": "fairness_and_explainability_metrics_evaluated",
    }

    # Ambiguous legacy facet shorthands spanning multiple controls/domains
    AMBIGUOUS_FACET_SHORTHANDS: ClassVar[dict[str, list[str]]] = {
        "data_sovereignty": [
            "overseas_recipients_and_regions_mapped",
            "prior_apra_consultation_for_material_offshoring",
        ],
    }

    # Pre-E4.1 v1.0.0 retired facets decomposed in E4.1 / Regulatory Pack v0.2.0
    RETIRED_FACET_DECOMPOSITIONS: ClassVar[dict[str, dict[str, Any]]] = {
        "security_controls_defined": {
            "retired_in_version": "0.2.0",
            "canonical_control_id": "CTRL-PRIV-SECURITY-RETENTION",
            "candidates": {
                "technical_security_measures_implemented": re.compile(
                    r"\b(aes-256|aes|tls|encrypt(?:ed|ion|ing)?|cryptograph(?:y|ic)|"
                    r"private tenant vpcs?|vpc isolation|network isolation|key management|"
                    r"hashing|pseudonymis(?:ation|ed)|technical security measures?|"
                    r"firewall|mfa|multi-factor|access control mechanism)\b",
                    re.IGNORECASE,
                ),
                "organisational_security_measures_implemented": re.compile(
                    r"\b(organisational security measures?|organizational security measures?|"
                    r"staff training|privacy training|security awareness|handling procedures?|"
                    r"access review procedure|background checks?|personnel vetting|"
                    r"information handling policy|clean desk|need-to-know governance)\b",
                    re.IGNORECASE,
                ),
            },
            "ambiguous_cue": re.compile(
                r"\b(security controls?|information security|reasonable steps to protect|"
                r"safeguard personal information)\b",
                re.IGNORECASE,
            ),
        },
        "deployer_human_oversight_and_6month_log_retention": {
            "retired_in_version": "0.2.0",
            "canonical_control_id": "CTRL-EU-HIGH-RISK",
            "candidates": {
                "deployer_human_oversight_assigned": re.compile(
                    r"\b(human oversight|assign(?:ed|ing)? natural persons?|"
                    r"competence, training and authority|oversee .* high-risk|"
                    r"article 26\(2\)|human-in-the-loop oversight)\b",
                    re.IGNORECASE,
                ),
                "automatic_logs_retained_6months": re.compile(
                    r"\b(6 months|six months|retain(?:ed|ing)? .* logs?|"
                    r"system logs? generated by the ai|automatically generated logs?|"
                    r"article 26\(6\)|log retention)\b",
                    re.IGNORECASE,
                ),
            },
            "ambiguous_cue": re.compile(
                r"\b(article 26|deployer obligations?|high-risk deployer)\b",
                re.IGNORECASE,
            ),
        },
    }

    def __init__(self, ucl_path: Path | str | None = None) -> None:
        if ucl_path is None:
            # Default to repo root UNIFIED_CONTROL_LIBRARY.json
            repo_root = Path(__file__).resolve().parent.parent.parent
            ucl_path = repo_root / "UNIFIED_CONTROL_LIBRARY.json"

        with open(ucl_path, "r", encoding="utf-8") as f:
            ucl_data = json.load(f)

        self.ucl_metadata: dict[str, Any] = {
            k: v for k, v in ucl_data.items() if k != "controls"
        }
        self.controls_data: list[dict[str, Any]] = ucl_data.get("controls", [])
        self.canonical_controls: set[str] = {c["control_id"] for c in self.controls_data}
        self.canonical_facets: set[str] = set()
        self.control_to_facets: dict[str, list[str]] = {}
        self.facet_to_control: dict[str, str] = {}

        for c in self.controls_data:
            cid = c["control_id"]
            facets = c.get("control_facets", [])
            assert len(facets) == len(set(facets)), (
                f"Duplicate facets detected in control '{cid}'"
            )
            self.control_to_facets[cid] = list(facets)
            for f_name in facets:
                assert isinstance(f_name, str) and f_name.strip(), (
                    f"Invalid empty facet in control '{cid}'"
                )
                self.canonical_facets.add(f_name)
                # First control claiming facet or canonical binding
                if f_name not in self.facet_to_control:
                    self.facet_to_control[f_name] = cid

        self._validate_adapter_integrity()

    @property
    def canonical_control_count(self) -> int:
        """Number of canonical controls loaded dynamically from the UCL."""
        return len(self.canonical_controls)

    @property
    def canonical_facet_count(self) -> int:
        """Number of unique canonical facets loaded dynamically from the UCL."""
        return len(self.canonical_facets)

    def _validate_adapter_integrity(self) -> None:
        """Verify dynamic UCL integrity and confirm all alias targets exist in the UCL."""
        assert len(self.controls_data) > 0, "No controls loaded from UCL"
        assert len(self.canonical_controls) == len(self.controls_data), (
            f"Duplicate control_id entries detected in UCL: "
            f"{len(self.controls_data)} records vs {len(self.canonical_controls)} unique IDs"
        )
        expected_total_controls = self.ucl_metadata.get("total_controls")
        if expected_total_controls is not None:
            assert len(self.canonical_controls) == expected_total_controls, (
                f"UCL total_controls metadata ({expected_total_controls}) does not match "
                f"loaded unique controls ({len(self.canonical_controls)})"
            )
        assert len(self.canonical_facets) > 0, "No canonical facets loaded from UCL"

        for legacy_id, canonical_id in self.VERIFIED_CONTROL_ALIASES.items():
            assert canonical_id in self.canonical_controls, (
                f"Adapter target control '{canonical_id}' (from '{legacy_id}') not found in UCL"
            )

        for legacy_id, candidate_ids in self.AMBIGUOUS_CONTROL_ALIASES.items():
            assert len(candidate_ids) >= 2, (
                f"Ambiguous alias '{legacy_id}' must map to at least two canonical candidates"
            )
            for candidate_id in candidate_ids:
                assert candidate_id in self.canonical_controls, (
                    f"Ambiguous adapter target '{candidate_id}' (from '{legacy_id}') not found in UCL"
                )

        for legacy_f, canonical_list in self.FACET_TRANSLATIONS.items():
            for cf in canonical_list:
                assert cf in self.canonical_facets, (
                    f"Adapter target facet '{cf}' (from '{legacy_f}') not found in UCL"
                )

        for legacy_f, target_f in self.EXACT_FACET_RENAMES.items():
            assert target_f in self.canonical_facets, (
                f"Exact facet rename target '{target_f}' (from '{legacy_f}') not found in UCL"
            )

        for retired_f, spec in self.RETIRED_FACET_DECOMPOSITIONS.items():
            assert retired_f not in self.canonical_facets, (
                f"Retired facet '{retired_f}' should not be in active canonical UCL"
            )
            ctrl_id = spec["canonical_control_id"]
            assert ctrl_id in self.canonical_controls, (
                f"Retired facet '{retired_f}' control '{ctrl_id}' not found in UCL"
            )
            for replacement_f in spec["candidates"]:
                assert replacement_f in self.canonical_facets, (
                    f"Replacement facet '{replacement_f}' for '{retired_f}' not found in UCL"
                )
                assert self.facet_to_control.get(replacement_f) == ctrl_id, (
                    f"Replacement facet '{replacement_f}' parent control mismatch"
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

    def resolve_facets(self, facet_name: str, source_text: str | None = None) -> list[str]:
        """Translate a legacy or canonical facet into canonical UCL facet(s).

        When source_text is provided for a retired or decomposed facet, emits only
        the replacement facets supported by the evidence in source_text.
        """
        if source_text is not None and (
            facet_name in self.RETIRED_FACET_DECOMPOSITIONS
            or facet_name not in self.canonical_facets
        ):
            record = self.migrate_legacy_facet(facet_name, source_text=source_text)
            if record.emitted_facets:
                return list(record.emitted_facets)

        # Exact match in UCL
        if facet_name in self.canonical_facets:
            return [facet_name]

        # In translation table
        if facet_name in self.FACET_TRANSLATIONS:
            return list(self.FACET_TRANSLATIONS[facet_name])

        return []

    def migrate_legacy_facet(
        self,
        facet_name: str,
        source_text: str = "",
        source_taxonomy_version: str = "1.0.0-pre-e4.1",
        target_taxonomy_version: str = "0.2.0",
    ) -> FacetMigrationRecord:
        """Version-aware migration of a facet identifier with evidence verification.

        Distinguishes:
        1. exact_rename (1:1 canonical match or verified 1:1 rename)
        2. one_to_many_decomposition (retired composite facet split into distinct facets)
        3. ambiguous_legacy_mapping (multiple candidate targets without disambiguating evidence)
        4. unsupported_legacy_facet (unknown/unsupported facet identifier)
        5. missing_evidence (known decomposed facet where source_text lacks specific evidence)
        """
        clean_text = (source_text or "").strip()

        # 1a. Already an active canonical facet in target UCL
        if facet_name in self.canonical_facets:
            return FacetMigrationRecord(
                original_facet=facet_name,
                source_taxonomy_version=source_taxonomy_version,
                target_taxonomy_version=target_taxonomy_version,
                migration_kind="exact_rename",
                emitted_facets=[facet_name],
                unresolved_candidate_facets=[],
                canonical_control_id=self.facet_to_control.get(facet_name),
                source_text=clean_text,
                mapping_reason=f"Facet '{facet_name}' is an active canonical UCL facet.",
                requires_human_review=False,
            )

        # 1b. Verified 1:1 rename
        if facet_name in self.EXACT_FACET_RENAMES:
            target_f = self.EXACT_FACET_RENAMES[facet_name]
            return FacetMigrationRecord(
                original_facet=facet_name,
                source_taxonomy_version=source_taxonomy_version,
                target_taxonomy_version=target_taxonomy_version,
                migration_kind="exact_rename",
                emitted_facets=[target_f],
                unresolved_candidate_facets=[],
                canonical_control_id=self.facet_to_control.get(target_f),
                source_text=clean_text,
                mapping_reason=(
                    f"Legacy facet '{facet_name}' maps 1:1 via exact semantic rename to '{target_f}'."
                ),
                requires_human_review=False,
            )

        # 2. Retired pre-E4.1 facet decomposed in E4.1 / Pack v0.2.0
        if facet_name in self.RETIRED_FACET_DECOMPOSITIONS:
            spec = self.RETIRED_FACET_DECOMPOSITIONS[facet_name]
            ctrl_id = spec["canonical_control_id"]
            candidates: dict[str, re.Pattern[str]] = spec["candidates"]
            all_candidate_names = list(candidates.keys())

            if not clean_text:
                return FacetMigrationRecord(
                    original_facet=facet_name,
                    source_taxonomy_version=source_taxonomy_version,
                    target_taxonomy_version=target_taxonomy_version,
                    migration_kind="missing_evidence",
                    emitted_facets=[],
                    unresolved_candidate_facets=all_candidate_names,
                    canonical_control_id=ctrl_id,
                    source_text=clean_text,
                    mapping_reason=(
                        f"Retired facet '{facet_name}' was decomposed into {all_candidate_names} "
                        f"in v{target_taxonomy_version}, but no source_text was provided to verify "
                        f"which replacement facet(s) are evidenced."
                    ),
                    requires_human_review=True,
                )

            supported: list[str] = []
            unresolved: list[str] = []
            for cand_name, pattern in candidates.items():
                if pattern.search(clean_text):
                    supported.append(cand_name)
                else:
                    unresolved.append(cand_name)

            if supported:
                return FacetMigrationRecord(
                    original_facet=facet_name,
                    source_taxonomy_version=source_taxonomy_version,
                    target_taxonomy_version=target_taxonomy_version,
                    migration_kind="one_to_many_decomposition",
                    emitted_facets=supported,
                    unresolved_candidate_facets=unresolved,
                    canonical_control_id=ctrl_id,
                    source_text=clean_text,
                    mapping_reason=(
                        f"Retired facet '{facet_name}' decomposed under '{ctrl_id}': "
                        f"source text evidences {supported}; un-evidenced sibling facet(s) "
                        f"{unresolved} kept unresolved."
                    ),
                    requires_human_review=bool(unresolved),
                )

            # Check if text has only generic/ambiguous domain cues without specific sub-facet evidence
            if spec["ambiguous_cue"].search(clean_text):
                return FacetMigrationRecord(
                    original_facet=facet_name,
                    source_taxonomy_version=source_taxonomy_version,
                    target_taxonomy_version=target_taxonomy_version,
                    migration_kind="ambiguous_legacy_mapping",
                    emitted_facets=[],
                    unresolved_candidate_facets=all_candidate_names,
                    canonical_control_id=ctrl_id,
                    source_text=clean_text,
                    mapping_reason=(
                        f"Source text mentions broad domain concepts for retired facet '{facet_name}' "
                        f"without distinguishing between {all_candidate_names}. Kept unresolved."
                    ),
                    requires_human_review=True,
                )

            return FacetMigrationRecord(
                original_facet=facet_name,
                source_taxonomy_version=source_taxonomy_version,
                target_taxonomy_version=target_taxonomy_version,
                migration_kind="missing_evidence",
                emitted_facets=[],
                unresolved_candidate_facets=all_candidate_names,
                canonical_control_id=ctrl_id,
                source_text=clean_text,
                mapping_reason=(
                    f"Source text does not contain supporting evidence for any v{target_taxonomy_version} "
                    f"replacement of retired facet '{facet_name}' ({all_candidate_names})."
                ),
                requires_human_review=True,
            )

        # 3. Ambiguous / multi-target legacy shorthand facets
        if facet_name in self.AMBIGUOUS_FACET_SHORTHANDS or facet_name in self.FACET_TRANSLATIONS:
            targets = self.AMBIGUOUS_FACET_SHORTHANDS.get(
                facet_name, self.FACET_TRANSLATIONS.get(facet_name, [])
            )
            if not clean_text:
                return FacetMigrationRecord(
                    original_facet=facet_name,
                    source_taxonomy_version=source_taxonomy_version,
                    target_taxonomy_version=target_taxonomy_version,
                    migration_kind="ambiguous_legacy_mapping",
                    emitted_facets=[],
                    unresolved_candidate_facets=list(targets),
                    canonical_control_id=None,
                    source_text=clean_text,
                    mapping_reason=(
                        f"Legacy shorthand facet '{facet_name}' spans multiple canonical facets "
                        f"{targets} and cannot be disambiguated without source text."
                    ),
                    requires_human_review=True,
                )
            return FacetMigrationRecord(
                original_facet=facet_name,
                source_taxonomy_version=source_taxonomy_version,
                target_taxonomy_version=target_taxonomy_version,
                migration_kind="ambiguous_legacy_mapping",
                emitted_facets=[],
                unresolved_candidate_facets=list(targets),
                canonical_control_id=None,
                source_text=clean_text,
                mapping_reason=(
                    f"Legacy shorthand facet '{facet_name}' maps to multiple candidate facets "
                    f"{targets}; requires explicit evidence disambiguation."
                ),
                requires_human_review=True,
            )

        # 4. Unsupported / unknown legacy facet
        return FacetMigrationRecord(
            original_facet=facet_name,
            source_taxonomy_version=source_taxonomy_version,
            target_taxonomy_version=target_taxonomy_version,
            migration_kind="unsupported_legacy_facet",
            emitted_facets=[],
            unresolved_candidate_facets=[],
            canonical_control_id=None,
            source_text=clean_text,
            mapping_reason=f"Facet '{facet_name}' is not supported in canonical UCL or legacy migration tables.",
            requires_human_review=True,
        )

    def migrate_benchmark_case_to_v020(self, case: dict[str, Any]) -> dict[str, Any]:
        """Return a version-aligned copy of a benchmark case for Regulatory Pack v0.2.0.

        Preserves original legacy facets, source text, reviewer_status, and migration rationale.
        """
        migrated = copy.deepcopy(case)
        input_text = migrated.get("input_text", "")
        original_facets = list(migrated.get("expected_facets", []))
        new_facets: list[str] = []
        migration_records: list[dict[str, Any]] = []
        had_retired_migration = False

        for facet in original_facets:
            if facet in self.canonical_facets:
                if facet not in new_facets:
                    new_facets.append(facet)
                continue

            had_retired_migration = True
            rec = self.migrate_legacy_facet(facet, source_text=input_text)
            migration_records.append(rec.to_dict())
            for ef in rec.emitted_facets:
                if ef not in new_facets:
                    new_facets.append(ef)

        if had_retired_migration:
            migrated["expected_facets"] = new_facets
            migrated["legacy_taxonomy_migration"] = {
                "source_taxonomy_version": "1.0.0-pre-e4.1",
                "target_taxonomy_version": "0.2.0",
                "original_expected_facets": original_facets,
                "migrated_expected_facets": new_facets,
                "unresolved_candidate_facets": [
                    uf
                    for r in migration_records
                    for uf in r["unresolved_candidate_facets"]
                ],
                "records": migration_records,
                "reviewer_status": migrated.get("reviewer_status", "unverified"),
            }
        return migrated

    def build_v020_aligned_dataset(self, v2_dataset: dict[str, Any]) -> dict[str, Any]:
        """Construct the Pack v0.2.0 version-aligned dataset view without altering historical V2."""
        aligned = copy.deepcopy(v2_dataset)
        aligned["dataset_id"] = "DEEPAUDIT-P1-EVAL-V2-PACK-V020"
        aligned["version"] = "2.2.0-pack-v0.2.0"
        aligned["derived_from_dataset"] = v2_dataset.get("dataset_id", "DEEPAUDIT-P1-EVAL-V2")
        aligned["derived_from_version"] = v2_dataset.get("version", "2.1.0-p1b0")
        aligned["regulatory_pack_version"] = "0.2.0"
        aligned["ucl_canonical_controls"] = self.canonical_control_count
        aligned["ucl_canonical_facets"] = self.canonical_facet_count

        migrated_cases: list[dict[str, Any]] = []
        migrated_case_summaries: list[dict[str, Any]] = []
        for case in aligned.get("cases", []):
            mc = self.migrate_benchmark_case_to_v020(case)
            migrated_cases.append(mc)
            if "legacy_taxonomy_migration" in mc:
                migrated_case_summaries.append(
                    {
                        "case_id": mc["case_id"],
                        "split": mc.get("split"),
                        **mc["legacy_taxonomy_migration"],
                    }
                )

        aligned["cases"] = migrated_cases
        aligned["taxonomy_migration_summary"] = {
            "source_taxonomy_version": "1.0.0-pre-e4.1 (155 facets)",
            "target_taxonomy_version": f"0.2.0 ({self.canonical_facet_count} facets)",
            "migrated_case_count": len(migrated_case_summaries),
            "migrated_cases": migrated_case_summaries,
        }
        return aligned

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
