"""FastAPI router for Banking Regulatory Crosswalk MVP v1."""

from __future__ import annotations

import base64
import binascii
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import load_regulatory_pack, validate_regulatory_pack
from .coverage import evaluate_questionnaire_coverage
from .importer import MAX_WORKBOOK_BYTES, import_aiaf_workbook
from .models import (
    BankingUseCase,
    CoverageAssessment,
    GapRecord,
    MappingDecision,
    PolicyGapAssessment,
    PolicyPack,
    QuestionBank,
    QuestionRoutingSnapshot,
    ReviewStatus,
)
from .policy import assess_policy_gaps, extract_policy_pack
from .store import NotFoundError, store


regulatory_pack = load_regulatory_pack()

RawTenantHeader = Annotated[
    str, Header(alias="X-Tenant-ID", min_length=1, max_length=128)
]
ActorHeader = Annotated[str, Header(alias="X-Actor", min_length=1, max_length=256)]
RoleHeader = Annotated[str, Header(alias="X-Role", min_length=1, max_length=64)]


def _require_crosswalk_api_key(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
) -> None:
    """Authenticate the server-to-server gateway before trusting context headers."""

    configured = os.getenv("CROSSWALK_API_KEY", "")
    if os.getenv("ENV") == "production" and not configured:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: CROSSWALK_API_KEY is required in production.",
        )
    if configured and (
        not x_api_key or not secrets.compare_digest(x_api_key, configured)
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing X-API-Key header"
        )


def _tenant_context(x_tenant_id: RawTenantHeader) -> str:
    """Bind production requests to the tenant configured on the trusted gateway."""

    if os.getenv("ENV") == "production":
        expected = os.getenv("BANKING_CROSSWALK_TENANT_ID", "demo-bank")
        if not secrets.compare_digest(x_tenant_id, expected):
            raise HTTPException(
                status_code=403,
                detail="Tenant context does not match the server-bound tenant",
            )
    return x_tenant_id


TenantHeader = Annotated[str, Depends(_tenant_context)]


def _validate_reviewer_identity(actor: str, role: str) -> None:
    """Reject spoofed reviewer identity in production service deployments."""

    if os.getenv("ENV") != "production":
        return
    expected_actor = os.getenv("BANKING_CROSSWALK_ACTOR", "demo.reviewer@bank.example")
    expected_role = os.getenv("BANKING_CROSSWALK_ROLE", "reviewer")
    if not secrets.compare_digest(actor, expected_actor) or not secrets.compare_digest(
        role.lower(), expected_role.lower()
    ):
        raise HTTPException(
            status_code=403, detail="Reviewer identity is not server-authorised"
        )


def _allow_ephemeral_crosswalk_state() -> bool:
    """Return whether this process may rely on its in-memory Crosswalk store.

    Local development and tests intentionally use the runnable in-memory MVP.
    Production must fail closed unless a durable repository is wired, or an
    operator explicitly opts into ephemeral demo behaviour.  DATABASE_URL is
    not considered here: the Crosswalk SQLModel schema is a contract only and
    is not currently connected to ``TenantStore``.
    """

    if getattr(store, "is_durable", False):
        return True
    if os.getenv("ENV", "").strip().lower() != "production":
        return True
    return os.getenv("ALLOW_EPHEMERAL_CROSSWALK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _require_crosswalk_state() -> None:
    """Reject stateful Crosswalk operations that would be lost on restart."""

    if not _allow_ephemeral_crosswalk_state():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Stateful Banking Crosswalk operations require a durable repository. "
                "The current in-memory MVP is disabled in production."
            ),
        )


router = APIRouter(
    prefix="/v1",
    tags=["Banking Crosswalk"],
    dependencies=[Depends(_require_crosswalk_api_key)],
)


class QuestionnaireImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(
        default="aiaf.excel.xlsx",
        min_length=1,
        max_length=255,
        pattern=r"^[^/\\\x00]+\.xlsx$",
    )
    workbook_base64: str = Field(
        max_length=4 * ((MAX_WORKBOOK_BYTES + 2) // 3),
        description="Base64-encoded XLSX bytes; the workbook is parsed read-only and not retained",
    )


class QuestionnaireRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questionnaire_id: Optional[str] = None
    response_tags: List[str] = Field(default_factory=list, max_length=2000)
    phase_tags: List[str] = Field(default_factory=list, max_length=100)


class PolicyFileImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(
        min_length=1, max_length=255, pattern=r"^[^/\\\x00]+\.(pdf|docx|txt|md)$"
    )
    file_base64: str = Field(max_length=4 * ((20 * 1024 * 1024 + 2) // 3))
    name: str = Field(min_length=1, max_length=256)
    version: str = Field(default="unversioned", min_length=1, max_length=128)


class CoverageAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: Optional[str] = None
    use_case: Optional[BankingUseCase] = None
    questionnaire_id: Optional[str] = None
    questionnaire_pack: Optional[Literal["DEMO_BANKING_V1"]] = None
    assessment_mode: Literal["provisional"] = "provisional"
    routing_snapshot_id: Optional[str] = None
    persist: bool = True

    @model_validator(mode="after")
    def one_use_case_source(self) -> "CoverageAssessmentRequest":
        if bool(self.use_case_id) == bool(self.use_case):
            raise ValueError("Provide exactly one of use_case_id or use_case")
        if self.questionnaire_id and self.questionnaire_pack:
            raise ValueError("Provide questionnaire_id or questionnaire_pack, not both")
        return self


class PolicyImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=10 * 1024 * 1024)
    version: str = Field(default="unversioned", min_length=1, max_length=128)


class PolicyGapAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: Optional[str] = None
    policy_pack_id: Optional[str] = None
    use_case: Optional[BankingUseCase] = None
    policy_name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    policy_text: Optional[str] = Field(
        default=None, min_length=1, max_length=10 * 1024 * 1024
    )
    policy_version: str = Field(default="unversioned", min_length=1, max_length=128)
    questionnaire_id: Optional[str] = None
    questionnaire_pack: Optional[Literal["DEMO_BANKING_V1"]] = None
    routing_snapshot_id: Optional[str] = None
    persist: bool = True

    @model_validator(mode="after")
    def stored_or_inline(self) -> "PolicyGapAssessmentRequest":
        if bool(self.use_case_id) == bool(self.use_case):
            raise ValueError("Provide exactly one of use_case_id or inline use_case")
        if bool(self.policy_pack_id) == bool(self.policy_text):
            raise ValueError(
                "Provide exactly one of policy_pack_id or inline policy_text"
            )
        if self.questionnaire_id and self.questionnaire_pack:
            raise ValueError("Provide questionnaire_id or questionnaire_pack, not both")
        return self


class MappingReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_id: str
    facet: str
    question_id: str
    review_status: Literal["approved", "rejected"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = Field(min_length=3)
    questionnaire_id: Optional[str] = None


class GapReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["start_review", "close", "reject", "reopen"]
    comment: str = Field(min_length=3)
    validated: bool = False
    scope_rechecked: bool = False
    approved: bool = False
    evidence_artifact_ids: List[str] = Field(default_factory=list, max_length=100)
    retest_record_id: Optional[str] = None


def _not_found(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0]))


def _assessment_question_snapshot(
    question_bank: QuestionBank, routing_snapshot: Optional[QuestionRoutingSnapshot]
) -> QuestionBank:
    """Use routed focus questions only; never infer coverage from the entire bank.

    Core and approved overlay questions are always in scope. Focus questions
    come only from a server-generated, tenant-scoped routing snapshot.
    """

    available = {item.question_id: item for item in question_bank.questions}
    selected = set(routing_snapshot.selected_question_ids if routing_snapshot else [])
    unknown = sorted(selected - set(available))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"selected_question_ids contains unknown IDs: {unknown[:10]}",
        )
    baseline = {
        item.question_id
        for item in question_bank.questions
        if item.question_type in {"core", "overlay"}
    }
    included_ids = baseline | selected
    mode = "routed_snapshot" if routing_snapshot else "core_only"
    warning = (
        None
        if routing_snapshot
        else "No routed focus-question snapshot was supplied; provisional coverage uses core and overlay questions only."
    )
    metadata = question_bank.metadata.model_copy(
        update={
            "warnings": list(
                dict.fromkeys(
                    [*question_bank.metadata.warnings, *([warning] if warning else [])]
                )
            )
        }
    )
    return question_bank.model_copy(
        update={
            "metadata": metadata,
            "questions": [
                item
                for item in question_bank.questions
                if item.question_id in included_ids
            ],
            "routing_metadata": {
                **question_bank.routing_metadata,
                "selection_mode": mode,
                "selection_warning": warning,
                "routing_snapshot_id": routing_snapshot.snapshot_id
                if routing_snapshot
                else None,
                "selected_question_ids": sorted(included_ids),
            },
        }
    )


def _route_focus_questions(
    question_bank: QuestionBank, response_tags: List[str], phase_tags: List[str]
) -> List[str]:
    """Apply the workbook's all-response-tags / any-phase-tag routing rule."""

    responses = {item.strip() for item in response_tags if item.strip()}
    phases = {item.strip() for item in phase_tags if item.strip()}
    selected: List[str] = []
    for question in question_bank.questions:
        if question.question_type != "focus":
            continue
        required_responses = set(question.routing_logic.get("has_all_keys") or [])
        allowed_phases = set(question.routing_logic.get("has_any_phase_tag") or [])
        if not required_responses.issubset(responses):
            continue
        if allowed_phases and not (allowed_phases & phases):
            continue
        selected.append(question.question_id)
    return selected


def _resolve_routing_snapshot(
    tenant_id: str,
    snapshot_id: Optional[str],
    question_bank: QuestionBank,
) -> Optional[QuestionRoutingSnapshot]:
    if not snapshot_id:
        return None
    try:
        snapshot = store.get_routing_snapshot(tenant_id, snapshot_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    if (
        snapshot.questionnaire_id != question_bank.metadata.questionnaire_id
        or snapshot.questionnaire_sha256 != question_bank.metadata.source_sha256
    ):
        raise HTTPException(
            status_code=409,
            detail="Routing snapshot does not match the selected questionnaire version",
        )
    return snapshot


@router.post("/questionnaires/import", response_model=QuestionBank)
def import_questionnaire(
    req: QuestionnaireImportRequest, x_tenant_id: TenantHeader
) -> QuestionBank:
    _require_crosswalk_state()
    try:
        raw = base64.b64decode(req.workbook_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="workbook_base64 is not valid base64"
        ) from exc
    try:
        bank = import_aiaf_workbook(raw, req.filename)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.save_questionnaire(x_tenant_id, bank)


@router.post(
    "/questionnaires/route", response_model=QuestionRoutingSnapshot, status_code=201
)
def route_questionnaire(
    req: QuestionnaireRouteRequest, x_tenant_id: TenantHeader
) -> QuestionRoutingSnapshot:
    _require_crosswalk_state()
    try:
        question_bank = store.get_questionnaire(x_tenant_id, req.questionnaire_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    response_tags = list(
        dict.fromkeys(item.strip() for item in req.response_tags if item.strip())
    )
    phase_tags = list(
        dict.fromkeys(item.strip() for item in req.phase_tags if item.strip())
    )
    snapshot = QuestionRoutingSnapshot(
        snapshot_id=str(uuid.uuid4()),
        tenant_id=x_tenant_id,
        questionnaire_id=question_bank.metadata.questionnaire_id,
        questionnaire_sha256=question_bank.metadata.source_sha256,
        response_tags=response_tags,
        phase_tags=phase_tags,
        selected_question_ids=_route_focus_questions(
            question_bank, response_tags, phase_tags
        ),
    )
    return store.save_routing_snapshot(x_tenant_id, snapshot)


@router.post("/regulatory-packs/validate")
def validate_pack(x_tenant_id: TenantHeader) -> dict:
    # The tenant header is required consistently even though the versioned
    # public regulatory pack is shared; this avoids accidental unaudited API
    # use when the router is deployed behind a multi-tenant gateway.
    _ = x_tenant_id
    return validate_regulatory_pack(regulatory_pack)


@router.post("/use-cases", response_model=BankingUseCase, status_code=201)
def create_use_case(
    use_case: BankingUseCase, x_tenant_id: TenantHeader
) -> BankingUseCase:
    _require_crosswalk_state()
    stored = use_case.model_copy(
        update={"use_case_id": use_case.use_case_id or str(uuid.uuid4())}
    )
    return store.save_use_case(x_tenant_id, stored)


@router.post(
    "/assessments/coverage", response_model=CoverageAssessment, status_code=201
)
def create_coverage_assessment(
    req: CoverageAssessmentRequest, x_tenant_id: TenantHeader
) -> CoverageAssessment:
    if (
        req.persist
        or req.use_case_id
        or req.questionnaire_id
        or req.routing_snapshot_id
    ):
        _require_crosswalk_state()
    try:
        use_case = req.use_case or store.get_use_case(
            x_tenant_id, req.use_case_id or ""
        )
        source_question_bank = store.get_questionnaire(
            x_tenant_id, req.questionnaire_id
        )
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    routing_snapshot = _resolve_routing_snapshot(
        x_tenant_id, req.routing_snapshot_id, source_question_bank
    )
    question_bank = _assessment_question_snapshot(
        source_question_bank, routing_snapshot
    )
    mappings = (
        store.mappings(
            x_tenant_id,
            questionnaire_id=source_question_bank.metadata.questionnaire_id,
            questionnaire_sha256=source_question_bank.metadata.source_sha256,
            regulatory_pack_id=regulatory_pack.pack_id,
            regulatory_pack_version=regulatory_pack.version,
        )
        if _allow_ephemeral_crosswalk_state()
        else []
    )
    assessment = evaluate_questionnaire_coverage(
        tenant_id=x_tenant_id,
        use_case=use_case,
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
        review_mappings=mappings,
    )
    if req.persist:
        store.save_assessment(x_tenant_id, assessment)
    return assessment


@router.post("/policies/import", response_model=PolicyPack, status_code=201)
def import_policy(req: PolicyImportRequest, x_tenant_id: TenantHeader) -> PolicyPack:
    _require_crosswalk_state()
    try:
        policy = extract_policy_pack(
            tenant_id=x_tenant_id, name=req.name, text=req.text, version=req.version
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.save_policy(x_tenant_id, policy)


@router.post("/policies/import-file", response_model=PolicyPack, status_code=201)
def import_policy_file(
    req: PolicyFileImportRequest, x_tenant_id: TenantHeader
) -> PolicyPack:
    _require_crosswalk_state()
    from .policy_documents import extract_policy_file

    try:
        content = base64.b64decode(req.file_base64, validate=True)
        text = extract_policy_file(req.filename, content)
        if not text.strip():
            raise ValueError("No policy text was extracted; scanned PDFs require OCR")
    except Exception as exc:
        # Untrusted parsers can echo file contents or internal locations in
        # exception text. Never return those details to upload clients.
        raise HTTPException(
            status_code=422,
            detail="Policy file could not be extracted within supported limits",
        ) from exc
    return import_policy(
        PolicyImportRequest(name=req.name, text=text, version=req.version), x_tenant_id
    )


@router.post(
    "/assessments/policy-gaps", response_model=PolicyGapAssessment, status_code=201
)
def create_policy_gap_assessment(
    req: PolicyGapAssessmentRequest, x_tenant_id: TenantHeader
) -> PolicyGapAssessment:
    if (
        req.persist
        or req.use_case_id
        or req.policy_pack_id
        or req.questionnaire_id
        or req.routing_snapshot_id
    ):
        _require_crosswalk_state()
    try:
        use_case = req.use_case or store.get_use_case(
            x_tenant_id, req.use_case_id or ""
        )
        if req.policy_text is not None:
            policy = extract_policy_pack(
                tenant_id=x_tenant_id,
                name=req.policy_name or "Enterprise policy",
                text=req.policy_text,
                version=req.policy_version,
            )
            if req.persist:
                policy = store.save_policy(x_tenant_id, policy)
        else:
            policy = store.get_policy(x_tenant_id, req.policy_pack_id or "")
        source_question_bank = store.get_questionnaire(
            x_tenant_id, req.questionnaire_id
        )
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    routing_snapshot = _resolve_routing_snapshot(
        x_tenant_id, req.routing_snapshot_id, source_question_bank
    )
    question_bank = _assessment_question_snapshot(
        source_question_bank, routing_snapshot
    )
    assessment = assess_policy_gaps(
        tenant_id=x_tenant_id,
        use_case=use_case,
        policy_pack=policy,
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
    )
    if req.persist:
        store.save_assessment(x_tenant_id, assessment)
    return assessment


@router.get("/assessments/{assessment_id}/gaps", response_model=List[GapRecord])
def get_gaps(assessment_id: str, x_tenant_id: TenantHeader) -> List[GapRecord]:
    _require_crosswalk_state()
    try:
        return store.gaps_for_assessment(x_tenant_id, assessment_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/mappings/review", response_model=MappingDecision)
def review_mapping(
    req: MappingReviewRequest,
    x_tenant_id: TenantHeader,
    x_actor: ActorHeader,
    x_role: RoleHeader,
) -> MappingDecision:
    _require_crosswalk_state()
    _validate_reviewer_identity(x_actor, x_role)
    if x_role.lower() not in {"legal", "compliance", "risk", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Mapping approval requires Legal, Compliance, Risk or Admin role",
        )
    try:
        question_bank = store.get_questionnaire(x_tenant_id, req.questionnaire_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    obligations = {item.obligation_id: item for item in regulatory_pack.obligations}
    obligation = obligations.get(req.obligation_id)
    if obligation is None:
        raise HTTPException(
            status_code=422,
            detail="Unknown obligation_id for the active regulatory pack",
        )
    if req.facet not in obligation.coverage_facets:
        raise HTTPException(
            status_code=422, detail="Facet does not belong to the selected obligation"
        )
    questions = {item.question_id: item for item in question_bank.questions}
    question = questions.get(req.question_id)
    if question is None:
        raise HTTPException(
            status_code=422,
            detail="Question does not belong to the selected questionnaire",
        )
    mapping = MappingDecision(
        obligation_id=req.obligation_id,
        facet=req.facet,
        question_id=req.question_id,
        review_status=ReviewStatus(req.review_status),
        confidence=req.confidence,
        reason=req.reason,
        source_reference=question.source_location
        or f"{question.source_sheet}:{question.question_id}",
        reviewer=x_actor,
        reviewer_role=x_role.lower(),
        reviewed_at=datetime.now(timezone.utc),
        questionnaire_id=question_bank.metadata.questionnaire_id,
        questionnaire_sha256=question_bank.metadata.source_sha256,
        regulatory_pack_id=regulatory_pack.pack_id,
        regulatory_pack_version=regulatory_pack.version,
        control_id=obligation.control_id,
    )
    return store.save_mapping(x_tenant_id, mapping, actor=x_actor)


@router.post("/gaps/{gap_id}/review", response_model=GapRecord)
def review_gap(
    gap_id: str,
    req: GapReviewRequest,
    x_tenant_id: TenantHeader,
    x_actor: ActorHeader,
    x_role: RoleHeader,
) -> GapRecord:
    _require_crosswalk_state()
    _validate_reviewer_identity(x_actor, x_role)
    if x_role.lower() not in {"legal", "compliance", "risk", "policy_owner", "admin"}:
        raise HTTPException(
            status_code=403, detail="Role is not authorised to review gaps"
        )
    try:
        gap = store.get_gap(x_tenant_id, gap_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    if req.action == "close" and not (
        req.validated
        and req.scope_rechecked
        and req.approved
        and req.evidence_artifact_ids
        and req.retest_record_id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Closing a gap requires validated remediation, scope recheck, authorised approval, "
                "at least one evidence artifact and a retest record"
            ),
        )
    status_map = {
        "start_review": "in_review",
        "close": "closed",
        "reject": "rejected",
        "reopen": "open",
    }
    reviewed = gap.model_copy(
        update={
            "status": status_map[req.action],
            "review_comment": req.comment,
            "reviewed_by": x_actor,
            "reviewer_role": x_role.lower(),
            "reviewed_at": datetime.now(timezone.utc),
            "closure_validated": req.validated if req.action == "close" else False,
            "closure_scope_rechecked": req.scope_rechecked
            if req.action == "close"
            else False,
            "closure_approved": req.approved if req.action == "close" else False,
            "closure_evidence_artifact_ids": (
                list(dict.fromkeys(req.evidence_artifact_ids))
                if req.action == "close"
                else []
            ),
            "closure_retest_record_id": (
                req.retest_record_id if req.action == "close" else None
            ),
        }
    )
    return store.save_gap(x_tenant_id, reviewed, actor=x_actor)


@router.get("/assessments/{assessment_id}/report")
def get_report(assessment_id: str, x_tenant_id: TenantHeader) -> dict:
    _require_crosswalk_state()
    try:
        assessment = store.get_assessment(x_tenant_id, assessment_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    return {
        "report_version": "1.0",
        "assessment_type": "policy_gaps"
        if isinstance(assessment, PolicyGapAssessment)
        else "questionnaire_coverage",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assessment": assessment.model_dump(mode="json"),
        "audit_events": store.audit_events(x_tenant_id),
        "legal_disclaimer": regulatory_pack.disclaimer,
    }
