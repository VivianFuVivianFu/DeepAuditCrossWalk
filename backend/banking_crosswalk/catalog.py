"""Load the banking pack and adapt the existing AIAF catalogue."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List

from .models import (
    QuestionBank,
    QuestionnaireMetadata,
    QuestionRecord,
    RegulatoryPack,
)


PACKAGE_DIR = Path(__file__).resolve().parent
REGULATORY_PACK_PATH = PACKAGE_DIR / "data" / "regulatory_pack.v0.1.json"
AIAF_CATALOG_PATH = PACKAGE_DIR / "data" / "demo_questionnaire.json"


def _stable_core_id(text: str) -> str:
    normalised = " ".join(text.lower().split())
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:12].upper()
    return f"AIAF-CORE-{digest}"


def _unique(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def load_regulatory_pack(path: Path | str = REGULATORY_PACK_PATH) -> RegulatoryPack:
    """Load and validate the versioned pack.

    Pydantic validation makes a malformed or duplicated facet list fail fast
    before an assessment can be created.
    """

    raw = Path(path).read_text(encoding="utf-8")
    pack = RegulatoryPack.model_validate_json(raw)
    ids = [item.obligation_id for item in pack.obligations]
    if len(ids) != len(set(ids)):
        raise ValueError("Regulatory pack contains duplicate obligation IDs")
    source_ids = {source.source_id for source in pack.sources}
    missing = sorted({item.source_id for item in pack.obligations} - source_ids)
    if missing:
        raise ValueError(f"Obligations reference missing sources: {missing}")
    return pack


def load_aiaf_question_bank(path: Path | str = AIAF_CATALOG_PATH) -> QuestionBank:
    """Adapt a catalogue; the bundled default contains original synthetic questions.

    The adapter name is retained from the extracted engine. An authorised AIAF
    workbook is imported separately through ``import_aiaf_workbook``. No NSW
    workbook or questionnaire text is bundled in this repository.
    """

    catalog_path = Path(path)
    raw_bytes = catalog_path.read_bytes()
    catalog = json.loads(raw_bytes.decode("utf-8"))
    version = str(catalog.get("version") or "AIAF-Questionnaire-v1")
    questions: List[QuestionRecord] = []

    for index, item in enumerate(catalog.get("core_questions", [])):
        text = str(item.get("question") or "").strip()
        if not text:
            continue
        options = item.get("options") or []
        tags = _unique(option.get("tag", "") for option in options)
        questions.append(
            QuestionRecord(
                question_id=_stable_core_id(text),
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
        questionnaire_id=f"AIAF-{hashlib.sha256(raw_bytes).hexdigest()[:12]}",
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
            "Bundled synthetic demonstration questions, not the NSW AIAF question bank. Import an authorised workbook for a real assessment."
        ],
    )
    return QuestionBank(
        metadata=metadata,
        questions=questions,
        triggers=catalog.get("triggers", []),
        routing_metadata={
            "focus_selection": "all response_tags AND any phase_tags",
            "source": catalog_path.name,
        },
    )


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
