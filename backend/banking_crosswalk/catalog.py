"""Load the banking pack and adapt the existing AIAF catalogue."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, List, Optional

from .models import (
    AtomicObligation,
    ObligationControlMappingCatalogue,
    QuestionBank,
    QuestionnaireMetadata,
    QuestionRecord,
    RegulatoryPack,
    SourceRecord,
    UnifiedControlLibrary,
)


PACKAGE_DIR = Path(__file__).resolve().parent
REGULATORY_PACK_PATH = PACKAGE_DIR / "data" / "regulatory_pack.v0.1.json"
SOURCE_REGISTER_PATH = PACKAGE_DIR / "data" / "regulatory_source_register.csv"
ATOMIC_OBLIGATION_CATALOGUE_PATH = (
    PACKAGE_DIR / "data" / "atomic_obligation_catalogue.json"
)
UNIFIED_CONTROL_LIBRARY_PATH = (
    PACKAGE_DIR / "data" / "unified_control_library.json"
)
OBLIGATION_CONTROL_MAPPINGS_PATH = (
    PACKAGE_DIR / "data" / "obligation_control_mappings.json"
)
DEMO_CATALOG_PATH = PACKAGE_DIR / "data" / "demo_questionnaire.json"
AIAF_CATALOG_PATH = DEMO_CATALOG_PATH
PRIVATE_REGULATORY_OVERLAY_ENV = "BANKING_CROSSWALK_PRIVATE_OVERLAY_PATH"


def _stable_core_id(text: str) -> str:
    normalised = " ".join(text.lower().split())
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:12].upper()
    return f"DEMO-{digest}"


def _unique(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def load_regulatory_pack(
    path: Path | str = REGULATORY_PACK_PATH,
    private_overlay_path: Optional[Path | str] = None,
) -> RegulatoryPack:
    """Load and validate the versioned pack, optionally applying a private licensed overlay.

    Pydantic validation makes a malformed or duplicated facet list fail fast
    before an assessment can be created. Proprietary standard text (e.g. ISO/IEC
    42001, 23894, 27001 licensed clauses) can be merged at runtime from a path
    configured via ``BANKING_CROSSWALK_PRIVATE_OVERLAY_PATH`` without committing
    copyrighted text to the public repository.
    """

    raw = Path(path).read_text(encoding="utf-8")
    pack = RegulatoryPack.model_validate_json(raw)

    overlay_target = private_overlay_path or os.environ.get(
        PRIVATE_REGULATORY_OVERLAY_ENV
    )
    if overlay_target:
        overlay_file = Path(overlay_target)
        if not overlay_file.exists():
            raise FileNotFoundError(
                f"Configured private regulatory overlay not found: {overlay_file}"
            )
        overlay_data = json.loads(overlay_file.read_text(encoding="utf-8"))
        overlay_sources = [
            SourceRecord.model_validate(item)
            for item in overlay_data.get("sources", [])
        ]
        overlay_obligations = [
            AtomicObligation.model_validate(item)
            for item in overlay_data.get("obligations", [])
        ]
        source_map = {src.source_id: src for src in pack.sources}
        for src in overlay_sources:
            source_map[src.source_id] = src
        obligation_map = {ob.obligation_id: ob for ob in pack.obligations}
        for ob in overlay_obligations:
            obligation_map[ob.obligation_id] = ob
        pack = pack.model_copy(
            update={
                "sources": list(source_map.values()),
                "obligations": list(obligation_map.values()),
            }
        )

    ids = [item.obligation_id for item in pack.obligations]
    if len(ids) != len(set(ids)):
        raise ValueError("Regulatory pack contains duplicate obligation IDs")
    source_ids = {source.source_id for source in pack.sources}
    missing = sorted({item.source_id for item in pack.obligations} - source_ids)
    if missing:
        raise ValueError(f"Obligations reference missing sources: {missing}")
    return pack


def load_source_register(
    path: Path | str = SOURCE_REGISTER_PATH,
) -> List[SourceRecord]:
    """Load the regulatory source register from CSV and validate each SourceRecord."""
    records: List[SourceRecord] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            entity_types_raw = row.get("applicable_entity_types") or ""
            entity_types = [
                item.strip()
                for item in entity_types_raw.split(";")
                if item.strip()
            ]
            payload = dict(row)
            payload["applicable_entity_types"] = entity_types
            records.append(SourceRecord.model_validate(payload))
    return records


def load_atomic_obligation_catalogue(
    path: Path | str = ATOMIC_OBLIGATION_CATALOGUE_PATH,
) -> List[AtomicObligation]:
    """Load and validate the standalone atomic obligation catalogue."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        AtomicObligation.model_validate(item)
        for item in data.get("obligations", [])
    ]


def load_unified_control_library(
    path: Path | str = UNIFIED_CONTROL_LIBRARY_PATH,
) -> UnifiedControlLibrary:
    """Load and validate the unified control library."""
    raw = Path(path).read_text(encoding="utf-8")
    return UnifiedControlLibrary.model_validate_json(raw)


def load_obligation_control_mappings(
    path: Path | str = OBLIGATION_CONTROL_MAPPINGS_PATH,
) -> ObligationControlMappingCatalogue:
    """Load and validate the obligation-to-control crosswalk mappings."""
    raw = Path(path).read_text(encoding="utf-8")
    return ObligationControlMappingCatalogue.model_validate_json(raw)


def load_demo_questionnaire(path: Path | str = DEMO_CATALOG_PATH) -> QuestionBank:
    """Load the bundled demonstration questionnaire containing synthetic governance questions.

    This neutral catalogue demonstrates governance crosswalk checks without NSW AIAF dependencies.
    Organisations evaluate their own assurance questionnaires by importing an XLSX workbook.
    """

    catalog_path = Path(path)
    raw_bytes = catalog_path.read_bytes()
    catalog = json.loads(raw_bytes.decode("utf-8"))
    version = str(catalog.get("version") or "SYNTHETIC-DEMO-1.0")
    questions: List[QuestionRecord] = []

    for index, item in enumerate(catalog.get("core_questions", [])):
        text = str(item.get("question") or "").strip()
        if not text:
            continue
        qid = str(item.get("id") or f"DEMO-Q{index + 1:02d}").strip()
        options = item.get("options") or []
        tags = _unique(option.get("tag", "") for option in options)
        questions.append(
            QuestionRecord(
                question_id=qid,
                question_text=text,
                response_tags=tags,
                answer_options=_unique(
                    option.get("response", "") for option in options
                ),
                source_version=version,
                source_sheet="Questions",
                question_type="core" if index < 16 else "benefit",
                source_location=f"Questions group {index + 1}",
                routing_logic={
                    "response_options": [
                        {
                            "response": option.get("response", ""),
                            "tag": option.get("tag", ""),
                        }
                        for option in options
                    ]
                },
            )
        )

    for item in catalog.get("focus_questions", []):
        question_id = str(item.get("id") or "").strip()
        text = str(item.get("question") or "").strip()
        if not question_id or not text:
            continue
        default_answer = str(item.get("default_answer") or "").strip()
        questions.append(
            QuestionRecord(
                question_id=question_id,
                question_text=text,
                risk_domain=str(item.get("risk_area") or "").strip() or None,
                risk_factor_ids=_unique(item.get("risk_factor_ids") or []),
                treatment_ids=_unique(item.get("treatment_ids") or []),
                response_tags=_unique(item.get("response_tags") or []),
                phase_tags=_unique(item.get("phase_tags") or []),
                sme_tags=_unique(item.get("sme_tags") or []),
                answer_options=[default_answer] if default_answer else [],
                source_version=version,
                source_sheet="ALL Focus Questions",
                question_type="focus",
                source_location=f"ALL Focus Questions:{question_id}",
                routing_logic={
                    "has_all_keys": _unique(item.get("response_tags") or []),
                    "has_any_phase_tag": _unique(item.get("phase_tags") or []),
                },
            )
        )

    metadata = QuestionnaireMetadata(
        questionnaire_id=f"DEMO-{hashlib.sha256(raw_bytes).hexdigest()[:12]}",
        source_filename=catalog_path.name,
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        source_version=version,
        core_question_count=min(16, len(catalog.get("core_questions", []))),
        benefit_question_count=max(0, len(catalog.get("core_questions", [])) - 16),
        focus_question_count=len(catalog.get("focus_questions", [])),
        trigger_count=len(catalog.get("triggers", [])),
        treatment_count=int(
            catalog.get("total_treatments") or len(catalog.get("treatments", {}))
        ),
        risk_count=int(catalog.get("total_risks") or len(catalog.get("risks", {}))),
        warnings=[
            "Bundled synthetic demonstration questions. Upload an enterprise questionnaire (.xlsx) for an organisation-specific assessment."
        ],
    )
    return QuestionBank(
        metadata=metadata,
        questions=questions,
        triggers=catalog.get("triggers", []),
        routing_metadata={
            "focus_selection": "all response_tags AND any phase_tags",
            "source": catalog_path.name,
            "selection_mode": "full_questionnaire",
        },
    )


def load_aiaf_question_bank(path: Path | str = DEMO_CATALOG_PATH) -> QuestionBank:
    """Deprecated alias for load_demo_questionnaire.

    Retained for backward compatibility. Emits a DeprecationWarning.
    """
    import warnings

    warnings.warn(
        "load_aiaf_question_bank is deprecated and will be removed in a future release. "
        "Use load_demo_questionnaire instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return load_demo_questionnaire(path)


def validate_regulatory_pack(pack: RegulatoryPack) -> dict:
    obligations = pack.obligations
    return {
        "pack_id": pack.pack_id,
        "version": pack.version,
        "verified_as_of": pack.verified_as_of.isoformat(),
        "source_count": len(pack.sources),
        "obligation_count": len(obligations),
        "binding_count": sum(
            item.authority.value in {"binding", "enforceable_guidance"}
            for item in obligations
        ),
        "voluntary_count": sum(
            item.authority.value == "voluntary" for item in obligations
        ),
        "organisation_scope_count": sum(
            item.assessment_scope == "organisation" for item in obligations
        ),
        "review_statuses": sorted({item.review_status.value for item in obligations}),
        "valid": True,
        "disclaimer": pack.disclaimer,
        "sources": [source.model_dump(mode="json") for source in pack.sources],
    }
