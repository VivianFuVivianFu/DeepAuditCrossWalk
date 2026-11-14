"""FastAPI router for Banking Regulatory Crosswalk MVP v1."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import load_demo_questionnaire, load_regulatory_pack, validate_regulatory_pack
from .coverage import evaluate_questionnaire_coverage
from .importer import MAX_WORKBOOK_BYTES, import_aiaf_workbook, import_questionnaire_workbook
from .models import (
    ClauseControlMapping,
    ClauseReviewStatus,
    EffectiveAssessmentBaseline,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    BankingUseCase,
    CoverageAssessment,
    GapRecord,
    MappingDecision,
    MappingRelationship,
    PolicyGapAssessment,
    PolicyPack,
    QuestionBank,
    QuestionRoutingSnapshot,
    ReconciliationDecision,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
    ReviewStatus,
)
from .policy import (
    assess_enterprise_policy_gaps,
    assess_policy_gaps,
    compile_enterprise_baseline,
    extract_enterprise_policy,
    extract_policy_pack,
    verify_baseline_integrity,
)
from .reconciliation import (
    compose_effective_assessment_baseline,
    evaluate_reconciliation_staleness,
    generate_reconciliation_candidates,
    review_reconciliation_decision,
)
from .store import ConflictError, NotFoundError, store


regulatory_pack = load_regulatory_pack()

RawTenantHeader = Annotated[
    str, Header(alias="X-Tenant-ID", min_length=1, max_length=128)
]
ActorHeader = Annotated[str, Header(alias="X-Actor", min_length=1, max_length=256)]
RoleHeader = Annotated[str, Header(alias="X-Role", min_length=1, max_length=64)]
OptionalActorHeader = Annotated[
    Optional[str], Header(alias="X-Actor", max_length=256)
]
OptionalRoleHeader = Annotated[
    Optional[str], Header(alias="X-Role", max_length=64)
]
WorkspaceContextHeader = Annotated[
    Optional[str], Header(alias="X-Workspace-Context", max_length=4096)
]

READER_ROLES = {
    "viewer",
    "analyst",
    "contributor",
    "reviewer",
    "compliance",
    "legal",
    "risk",
    "policy_owner",
    "admin",
    "assurance",
    "general counsel",
    "general_counsel",
}
CONTRIBUTOR_ROLES = {
    "analyst",
    "contributor",
    "reviewer",
    "compliance",
    "legal",
    "risk",
    "policy_owner",
    "admin",
    "assurance",
    "general counsel",
    "general_counsel",
}
REVIEWER_ROLES = {
    "reviewer",
    "compliance",
    "legal",
    "risk",
    "policy_owner",
    "admin",
    "assurance",
    "counsel",
    "general counsel",
    "general_counsel",
    "lead counsel",
    "lead_counsel",
    "control_architect",
    "auditor",
    "audit",
}
NON_REVIEWER_ROLES = {
    "viewer",
    "read_only",
    "readonly",
    "analyst",
    "contributor",
}
ADMIN_ROLES = {"admin"}


def _normalize_role(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    r = role.strip().lower().replace("-", "_").replace(" ", "_")
    if r in {"viewer", "read_only", "readonly"}:
        return "viewer"
    if r in {"analyst", "contributor"}:
        return "analyst"
    if r in {"admin", "administrator"}:
        return "admin"
    if r in {
        "reviewer",
        "compliance",
        "legal",
        "risk",
        "policy_owner",
        "assurance",
        "counsel",
        "general_counsel",
        "lead_counsel",
        "control_architect",
        "auditor",
        "audit",
    }:
        return "reviewer"
    return r


def _actors_match(header_actor: str, body_actor: str) -> bool:
    h = header_actor.strip()
    b = body_actor.strip()
    if _constant_match(h, b):
        return True
    if "@" in h and _constant_match(h.split("@")[0].lower(), b.lower()):
        return True
    if "@" in b and _constant_match(b.split("@")[0].lower(), h.lower()):
        return True
    return False


def _production() -> bool:
    return os.getenv("ENV", "").strip().lower() == "production"


def _constant_match(value: str, expected: str) -> bool:
    return secrets.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


def _verify_signed_workspace_context(
    raw_context: Optional[str],
    expected_tenant: str,
    header_actor: Optional[str] = None,
    header_role: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Verify HMAC-SHA256 signed X-Workspace-Context assertion from trusted gateway."""
    is_public_demo = expected_tenant.strip().lower() == "public-demo"
    if is_public_demo and not raw_context:
        return None

    secret = (
        os.getenv("CROSSWALK_CONTEXT_SECRET", "").strip()
        or os.getenv("WORKSPACE_SESSION_SECRET", "").strip()
    )

    if not secret:
        return None

    if _production() and len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="Backend configuration error: WORKSPACE_SESSION_SECRET (>= 32 chars) is required for private tenant access",
        )

    if not raw_context or "." not in raw_context:
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed signed X-Workspace-Context assertion",
        )

    body_b64, provided_sig = raw_context.rsplit(".", 1)
    expected_sig = hmac.new(
        secret.encode("utf-8"), body_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not _constant_match(provided_sig.lower(), expected_sig.lower()):
        raise HTTPException(
            status_code=401,
            detail="Invalid X-Workspace-Context signature",
        )

    padding = "=" * (-len(body_b64) % 4)
    try:
        payload = json.loads(
            base64.urlsafe_b64decode((body_b64 + padding).encode("ascii")).decode(
                "utf-8"
            )
        )
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail="Invalid X-Workspace-Context payload"
        ) from exc

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp <= time.time():
        raise HTTPException(
            status_code=401, detail="Expired X-Workspace-Context assertion"
        )

    ctx_tenant = str(payload.get("tenant_id") or "").strip()
    if not ctx_tenant or not _constant_match(ctx_tenant, expected_tenant):
        raise HTTPException(
            status_code=403,
            detail="X-Tenant-ID does not match signed workspace context tenant",
        )

    ctx_user = str(payload.get("user_id") or "").strip()
    if not ctx_user:
        raise HTTPException(
            status_code=401, detail="Signed workspace context is missing user_id"
        )
    if header_actor and not _actors_match(header_actor.strip(), ctx_user):
        raise HTTPException(
            status_code=403,
            detail="X-Actor header does not match signed workspace context user_id",
        )

    ctx_roles = {
        str(r).strip().lower()
        for r in (payload.get("roles") or [])
        if str(r).strip()
    }
    if header_role and header_role.strip().lower() not in ctx_roles:
        raise HTTPException(
            status_code=403,
            detail="X-Role header is not authorised in signed workspace context",
        )

    return payload


def _require_crosswalk_api_key(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
) -> None:
    """Authenticate the server-to-server gateway before trusting context headers."""

    configured = os.getenv("CROSSWALK_API_KEY", "")
    if _production() and not configured:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: CROSSWALK_API_KEY is required in production.",
        )
    if configured and (not x_api_key or not _constant_match(x_api_key, configured)):
        raise HTTPException(
            status_code=401, detail="Invalid or missing X-API-Key header"
        )


def _tenant_context(
    x_tenant_id: RawTenantHeader,
    x_workspace_context: WorkspaceContextHeader = None,
    x_actor: OptionalActorHeader = None,
    x_role: OptionalRoleHeader = None,
) -> str:
    """Bind production requests to the tenant configured on the trusted gateway."""

    if not x_tenant_id.strip():
        raise HTTPException(status_code=422, detail="Tenant context must not be blank")
    _verify_signed_workspace_context(
        x_workspace_context,
        expected_tenant=x_tenant_id,
        header_actor=x_actor,
        header_role=x_role,
    )
    if _production():
        expected = os.getenv("BANKING_CROSSWALK_TENANT_ID", "")
        if expected and not _constant_match(x_tenant_id, expected):
            raise HTTPException(
                status_code=403,
                detail="Tenant context does not match the server-bound tenant",
            )
        if not expected and not x_workspace_context:
            raise HTTPException(
                status_code=403,
                detail="Tenant context is not bound to a verified workspace session",
            )
    return x_tenant_id


TenantHeader = Annotated[str, Depends(_tenant_context)]


def _enforce_role_if_present(
    role: Optional[str],
    allowed_roles: set[str],
    action_description: str,
) -> None:
    if role is None:
        return
    norm = role.strip().lower()
    if norm not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{norm}' is not authorised for {action_description}",
        )


def _reject_public_demo_tenant(tenant_id: str) -> None:
    if tenant_id.strip().lower() == "public-demo":
        raise HTTPException(
            status_code=403,
            detail="The 'public-demo' tenant is restricted to stateless synthetic demo assessments",
        )



def _validate_reviewer_identity(
    actor: str,
    role: str,
    header_actor: Optional[str] = None,
    header_role: Optional[str] = None,
    x_workspace_context: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Enforce verified reviewer identity and role authorisation across all modes."""
    raw_role = (role or "").strip().lower()
    norm_role = _normalize_role(role) or ""
    if norm_role in NON_REVIEWER_ROLES or (
        norm_role not in REVIEWER_ROLES and raw_role not in REVIEWER_ROLES
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' is not authorised to review or approve requirements",
        )
    if header_actor is not None and not _actors_match(header_actor, actor):
        raise HTTPException(
            status_code=403,
            detail="X-Actor header does not match review payload actor",
        )
    if header_role is not None:
        raw_h = header_role.strip().lower()
        norm_h = _normalize_role(header_role) or ""
        if norm_h in NON_REVIEWER_ROLES or (
            norm_h not in REVIEWER_ROLES and raw_h not in REVIEWER_ROLES
        ):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{header_role}' is not authorised to review or approve requirements",
            )
        if norm_h != norm_role and not _constant_match(raw_h, raw_role):
            raise HTTPException(
                status_code=403,
                detail="X-Role header does not match review payload role",
            )

    if x_workspace_context and tenant_id:
        ctx = _verify_signed_workspace_context(
            x_workspace_context,
            expected_tenant=tenant_id,
            header_actor=actor,
            header_role=role,
        )
        if ctx is not None:
            return

    if not _production():
        return
    expected_actor = os.getenv("BANKING_CROSSWALK_ACTOR", "")
    expected_role = os.getenv("BANKING_CROSSWALK_ROLE", "")
    if not expected_actor.strip() or not expected_role.strip():
        raise HTTPException(
            status_code=503,
            detail="Reviewer identity is not configured on this service",
        )
    if not _constant_match(actor, expected_actor) or not _constant_match(
        role.lower(), expected_role.lower()
    ):
        raise HTTPException(
            status_code=403, detail="Reviewer identity is not server-authorised"
        )


def _allow_ephemeral_crosswalk_state() -> bool:
    """Return whether this process may rely on its in-memory Crosswalk store.

    Local development and tests intentionally use the runnable in-memory MVP.
    Production fails closed unless a migrated PostgreSQL repository is wired,
    or an operator explicitly opts into ephemeral demo behaviour. Merely
    setting DATABASE_URL does not bypass startup and runtime storage checks.
    """

    if getattr(store, "is_durable", False):
        return True
    if not _production():
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
        default="questionnaire.xlsx",
        min_length=1,
        max_length=255,
        pattern=r"^[^/\\\x00]+\.xlsx$",
    )
    workbook_base64: str = Field(
        max_length=4 * ((MAX_WORKBOOK_BYTES + 2) // 3),
        description="Base64-encoded XLSX bytes; the workbook is parsed read-only and not retained",
    )
    sheet_names: Optional[List[str]] = Field(default=None, max_length=50)
    column_mapping: Optional[Dict[str, str]] = Field(default=None)


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
    assessment_mode: Optional[
        Literal["regulatory_only", "enterprise_enhanced", "provisional"]
    ] = "regulatory_only"
    assessment_target_type: Optional[
        Literal["questionnaire", "strategy", "use_case"]
    ] = "questionnaire"
    routing_snapshot_id: Optional[str] = None
    selection_mode: Optional[
        Literal["full_questionnaire", "core_only", "routed_snapshot"]
    ] = None
    enterprise_baseline_id: Optional[str] = None
    enterprise_baseline_version: Optional[str] = None
    persist: bool = True

    @model_validator(mode="after")
    def one_use_case_source(self) -> "CoverageAssessmentRequest":
        if self.use_case_id and self.use_case is not None:
            raise ValueError("Provide at most one of use_case_id or use_case")
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
    enterprise_baseline_id: Optional[str] = None
    enterprise_policy_ids: Optional[List[str]] = None
    routing_snapshot_id: Optional[str] = None
    persist: bool = True

    @model_validator(mode="after")
    def stored_or_inline(self) -> "PolicyGapAssessmentRequest":
        if self.use_case_id and self.use_case is not None:
            raise ValueError("Provide at most one of use_case_id or inline use_case")
        has_enterprise = bool(self.enterprise_baseline_id or self.enterprise_policy_ids)
        if not has_enterprise:
            if bool(self.policy_pack_id) == bool(self.policy_text):
                raise ValueError(
                    "Provide exactly one of policy_pack_id, inline policy_text, or enterprise_baseline_id"
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
    expected_revision: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def nonempty_closure_references(self):
        if self.action == "close":
            if any(not value.strip() for value in self.evidence_artifact_ids):
                raise ValueError("Evidence artifact references must not be blank")
            if self.retest_record_id is not None and not self.retest_record_id.strip():
                raise ValueError("Retest reference must not be blank")
        return self


def _not_found(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0]))


def _assessment_question_snapshot(
    question_bank: QuestionBank,
    routing_snapshot: Optional[QuestionRoutingSnapshot],
    selection_mode: Optional[str] = None,
) -> QuestionBank:
    """Resolve the assessment question snapshot.

    For general imported questionnaires, the default evaluates the full questionnaire.
    For routed questionnaires with a snapshot, only the baseline and routed focus questions apply.
    """

    available = {item.question_id: item for item in question_bank.questions}
    selected = set(routing_snapshot.selected_question_ids if routing_snapshot else [])
    unknown = sorted(selected - set(available))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"selected_question_ids contains unknown IDs: {unknown[:10]}",
        )

    if routing_snapshot:
        baseline = {
            item.question_id
            for item in question_bank.questions
            if item.question_type in {"core", "overlay"}
        }
        included_ids = baseline | selected
        mode = "routed_snapshot"
        warning = None
    elif selection_mode == "core_only" or (
        selection_mode != "full_questionnaire"
        and any(q.question_type == "focus" for q in question_bank.questions)
        and any(q.question_type == "core" for q in question_bank.questions)
        and not any(q.question_type in {"general", "question"} for q in question_bank.questions)
    ):
        baseline = {
            item.question_id
            for item in question_bank.questions
            if item.question_type in {"core", "overlay"}
        }
        included_ids = baseline
        mode = "core_only"
        warning = (
            "No routed focus-question snapshot was supplied; provisional coverage uses core and overlay questions only."
        )
    else:
        # Full questionnaire mode (default for imported general questionnaires)
        included_ids = set(available)
        mode = "full_questionnaire"
        warning = None

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
    req: QuestionnaireImportRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> QuestionBank:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "importing questionnaires")
    try:
        raw = base64.b64decode(req.workbook_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="workbook_base64 is not valid base64"
        ) from exc
    try:
        bank = import_questionnaire_workbook(
            raw,
            filename=req.filename,
            sheet_names=req.sheet_names,
            column_mapping=req.column_mapping,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.save_questionnaire(x_tenant_id, bank)


@router.get("/questionnaires", response_model=List[QuestionBank])
def list_questionnaires_endpoint(
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[QuestionBank]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "listing questionnaires")
    return store.list_questionnaires(x_tenant_id)


@router.get("/questionnaires/{questionnaire_id}", response_model=QuestionBank)
def get_questionnaire_endpoint(
    questionnaire_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> QuestionBank:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "reading questionnaires")
    try:
        return store.get_tenant_questionnaire(x_tenant_id, questionnaire_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/questionnaires/route", response_model=QuestionRoutingSnapshot, status_code=201
)
def route_questionnaire(
    req: QuestionnaireRouteRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> QuestionRoutingSnapshot:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "routing questionnaires")
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
    use_case: BankingUseCase,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> BankingUseCase:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "creating use cases")
    stored = use_case.model_copy(
        update={"use_case_id": use_case.use_case_id or str(uuid.uuid4())}
    )
    return store.save_use_case(x_tenant_id, stored)


@router.post(
    "/assessments/coverage", response_model=CoverageAssessment, status_code=201
)
def create_coverage_assessment(
    req: CoverageAssessmentRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> CoverageAssessment:
    if (
        req.persist
        or req.use_case_id
        or req.questionnaire_id
        or req.routing_snapshot_id
        or req.enterprise_baseline_id
    ):
        _reject_public_demo_tenant(x_tenant_id)
        _require_crosswalk_state()
    if x_tenant_id.strip().lower() != "public-demo":
        _enforce_role_if_present(
            x_role, CONTRIBUTOR_ROLES, "running coverage assessments"
        )
    try:
        if req.use_case is not None:
            use_case = req.use_case
        elif req.use_case_id:
            use_case = store.get_use_case(x_tenant_id, req.use_case_id)
        else:
            use_case = BankingUseCase.enterprise_baseline()
        source_question_bank = store.get_questionnaire(
            x_tenant_id, req.questionnaire_id
        )
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    routing_snapshot = _resolve_routing_snapshot(
        x_tenant_id, req.routing_snapshot_id, source_question_bank
    )
    question_bank = _assessment_question_snapshot(
        source_question_bank,
        routing_snapshot,
        selection_mode=getattr(req, "selection_mode", None),
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
    target_type = req.assessment_target_type or "questionnaire"
    if target_type == "strategy":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "AI Governance Strategy Assessment is not yet implemented in production. "
                "Supported target type: 'questionnaire'."
            ),
        )
    elif target_type == "use_case" and not req.questionnaire_id and not req.questionnaire_pack:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Direct AI Use Case Operational Telemetry Assessment without a questionnaire "
                "is not yet implemented in production. Supported target type: 'questionnaire'."
            ),
        )

    mode = req.assessment_mode or "regulatory_only"

    enterprise_baseline = None
    enterprise_clauses = []

    if mode == "regulatory_only":
        if req.enterprise_baseline_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="enterprise_baseline_id cannot be provided when assessment_mode is 'regulatory_only'",
            )
        if req.enterprise_baseline_version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="enterprise_baseline_version cannot be provided when assessment_mode is 'regulatory_only'",
            )
        enterprise_baseline = None
        enterprise_clauses = []
    elif mode == "enterprise_enhanced":
        if not req.enterprise_baseline_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="enterprise_baseline_id is required when assessment_mode is 'enterprise_enhanced'",
            )
        try:
            enterprise_baseline = store.get_enterprise_baseline(
                x_tenant_id, req.enterprise_baseline_id
            )
        except NotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Enterprise baseline not found for this tenant",
            ) from exc

        if enterprise_baseline.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Enterprise baseline '{req.enterprise_baseline_id}' is not active",
            )

        has_approved = any(
            c.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
            for c in (enterprise_baseline.clause_snapshots or ())
        )
        if not has_approved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Enterprise baseline '{req.enterprise_baseline_id}' contains no approved or confirmed clauses and is not eligible for enterprise_enhanced assessment",
            )

        if (
            req.enterprise_baseline_version
            and enterprise_baseline.version != req.enterprise_baseline_version
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Enterprise baseline version mismatch: expected "
                    f"'{req.enterprise_baseline_version}', found '{enterprise_baseline.version}'"
                ),
            )

        if not verify_baseline_integrity(enterprise_baseline):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Baseline integrity error: cryptographic fingerprint mismatch",
            )

        if enterprise_baseline.clause_snapshots:
            enterprise_clauses = list(enterprise_baseline.clause_snapshots)
        else:
            for pid in enterprise_baseline.policy_ids:
                try:
                    p = store.get_enterprise_policy(x_tenant_id, pid)
                    enterprise_clauses.extend(p.clauses)
                except NotFoundError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Baseline integrity error: referenced policy '{pid}' cannot be resolved for this tenant",
                    ) from exc
    elif mode == "provisional":
        enterprise_baseline = None
        enterprise_clauses = []
        if req.enterprise_baseline_id:
            try:
                enterprise_baseline = store.get_enterprise_baseline(
                    x_tenant_id, req.enterprise_baseline_id
                )
                if enterprise_baseline.clause_snapshots:
                    enterprise_clauses = list(enterprise_baseline.clause_snapshots)
                else:
                    for pid in enterprise_baseline.policy_ids:
                        try:
                            p = store.get_enterprise_policy(x_tenant_id, pid)
                            enterprise_clauses.extend(p.clauses)
                        except NotFoundError:
                            pass
            except NotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Enterprise baseline not found for this tenant",
                ) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported assessment mode '{mode}'",
        )

    assessment = evaluate_questionnaire_coverage(
        tenant_id=x_tenant_id,
        use_case=use_case,
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
        review_mappings=mappings,
        enterprise_baseline=enterprise_baseline,
        enterprise_clauses=enterprise_clauses,
        assessment_mode=mode,
        assessment_target_type=target_type,
    )
    if enterprise_baseline is not None:
        eff_baselines = store.list_effective_baselines(
            x_tenant_id, baseline_id=enterprise_baseline.baseline_id
        )
        if eff_baselines:
            latest_eff = eff_baselines[-1]
            assessment = assessment.model_copy(
                update={
                    "effective_baseline_id": latest_eff.effective_baseline_id,
                    "effective_baseline_sha256": latest_eff.effective_baseline_sha256,
                }
            )
    if req.persist:
        store.save_assessment(x_tenant_id, assessment)
    return assessment


@router.post("/policies/import", response_model=PolicyPack, status_code=201)
def import_policy(
    req: PolicyImportRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> PolicyPack:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "importing policies")
    try:
        policy = extract_policy_pack(
            tenant_id=x_tenant_id, name=req.name, text=req.text, version=req.version
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.save_policy(x_tenant_id, policy)


@router.post("/policies/import-file", response_model=PolicyPack, status_code=201)
def import_policy_file(
    req: PolicyFileImportRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> PolicyPack:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "importing policy files")
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
        PolicyImportRequest(name=req.name, text=text, version=req.version),
        x_tenant_id,
        x_role=x_role,
    )


@router.post(
    "/assessments/policy-gaps", response_model=PolicyGapAssessment, status_code=201
)
def create_policy_gap_assessment(
    req: PolicyGapAssessmentRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> PolicyGapAssessment:
    if (
        req.persist
        or req.use_case_id
        or req.policy_pack_id
        or req.questionnaire_id
        or req.routing_snapshot_id
        or req.enterprise_baseline_id
        or req.enterprise_policy_ids
    ):
        _reject_public_demo_tenant(x_tenant_id)
        _require_crosswalk_state()
    if x_tenant_id.strip().lower() != "public-demo":
        _enforce_role_if_present(
            x_role, CONTRIBUTOR_ROLES, "running policy gap assessments"
        )
    try:
        if req.use_case is not None:
            use_case = req.use_case
        elif req.use_case_id:
            use_case = store.get_use_case(x_tenant_id, req.use_case_id)
        else:
            use_case = BankingUseCase.enterprise_baseline()
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
        source_question_bank,
        routing_snapshot,
        selection_mode=getattr(req, "selection_mode", None),
    )
    if req.enterprise_baseline_id or req.enterprise_policy_ids:
        policies_to_assess = []
        if req.enterprise_baseline_id:
            baseline = store.get_enterprise_baseline(x_tenant_id, req.enterprise_baseline_id)
            for pid in baseline.policy_ids:
                policies_to_assess.append(store.get_enterprise_policy(x_tenant_id, pid))
        if req.enterprise_policy_ids:
            for pid in req.enterprise_policy_ids:
                policies_to_assess.append(store.get_enterprise_policy(x_tenant_id, pid))
        assessment = assess_enterprise_policy_gaps(
            tenant_id=x_tenant_id,
            use_case=use_case,
            policies=policies_to_assess,
            question_bank=question_bank,
            regulatory_pack=regulatory_pack,
            baseline_id=req.enterprise_baseline_id,
        )
    else:
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
def get_gaps(
    assessment_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[GapRecord]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "reading assessment gaps")
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
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _validate_reviewer_identity(x_actor, x_role)
    if x_role.lower() not in {"reviewer", "legal", "compliance", "risk", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Mapping approval requires Reviewer, Legal, Compliance, Risk or Admin role",
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
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    if x_role.lower() not in {"reviewer", "legal", "compliance", "risk", "policy_owner", "admin"}:
        raise HTTPException(
            status_code=403, detail="Role is not authorised to review gaps"
        )
    if not _production():
        pass
    else:
        expected_actor = os.getenv("BANKING_CROSSWALK_ACTOR", "")
        expected_role = os.getenv("BANKING_CROSSWALK_ROLE", "")
        if not expected_actor.strip() or not expected_role.strip():
            raise HTTPException(
                status_code=503,
                detail="Reviewer identity is not configured on this service",
            )
        if not _constant_match(x_actor, expected_actor) or not _constant_match(
            x_role.lower(), expected_role.lower()
        ):
            raise HTTPException(
                status_code=403, detail="Reviewer identity is not server-authorised"
            )
    try:
        gap = store.get_gap(x_tenant_id, gap_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    if req.expected_revision is not None and req.expected_revision != gap.revision:
        raise HTTPException(
            status_code=409, detail="Gap changed; refresh before reviewing again"
        )
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
def get_report(
    assessment_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> dict:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "reading assessment reports")
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


class EnterprisePolicyImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=10 * 1024 * 1024)
    version: str = Field(default="1.0.0", min_length=1, max_length=128)
    category: str = Field(default="general", max_length=64)
    authority_level: EnterpriseAuthorityLevel = EnterpriseAuthorityLevel.ENTERPRISE_POLICY
    effective_date: Optional[datetime] = None


class EnterprisePolicyFileImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    filename: str = Field(min_length=1, max_length=256)
    file_base64: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1, max_length=128)
    category: str = Field(default="general", max_length=64)
    authority_level: EnterpriseAuthorityLevel = EnterpriseAuthorityLevel.ENTERPRISE_POLICY
    effective_date: Optional[datetime] = None


class ClauseReviewRequest(BaseModel):
    status: ClauseReviewStatus
    actor: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=64)
    control_mappings: Optional[List[ClauseControlMapping]] = None
    review_comment: Optional[str] = None


class ClauseMappingReviewRequest(BaseModel):
    status: ClauseReviewStatus
    actor: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=64)
    relationship: Optional[MappingRelationship] = None
    mapped_facets: Optional[List[str]] = None
    review_comment: Optional[str] = None


class DeleteResponse(BaseModel):
    status: str
    policy_id: str

class EnterpriseBaselineCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: Optional[str] = None
    policy_ids: List[str] = Field(default_factory=list)
    version: Optional[str] = "1.0.0"
    status: Optional[str] = "active"


# ─────────────────────────────────────────────────────────────────────────────
# Enterprise Policy Layer REST API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/enterprise/policies/import", response_model=EnterprisePolicy, status_code=201)
def import_enterprise_policy(
    req: EnterprisePolicyImportRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> EnterprisePolicy:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "importing enterprise policies")
    try:
        policy = extract_enterprise_policy(
            tenant_id=x_tenant_id,
            name=req.name,
            text=req.text,
            version=req.version,
            category=req.category,
            authority_level=req.authority_level,
            effective_date=req.effective_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.save_enterprise_policy(x_tenant_id, policy)


@router.post("/enterprise/policies/import-file", response_model=EnterprisePolicy, status_code=201)
def import_enterprise_policy_file(
    req: EnterprisePolicyFileImportRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> EnterprisePolicy:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, CONTRIBUTOR_ROLES, "importing enterprise policy files")
    from .policy_documents import extract_policy_file

    try:
        content = base64.b64decode(req.file_base64, validate=True)
        text = extract_policy_file(req.filename, content)
        if not text.strip():
            raise ValueError("No policy text was extracted; scanned PDFs require OCR")
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Policy file could not be extracted within supported limits",
        ) from exc
    return import_enterprise_policy(
        EnterprisePolicyImportRequest(
            name=req.name,
            text=text,
            version=req.version,
            category=req.category,
            authority_level=req.authority_level,
            effective_date=req.effective_date,
        ),
        x_tenant_id,
        x_role=x_role,
    )


@router.get("/enterprise/policies", response_model=List[EnterprisePolicy])
def list_enterprise_policies(
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[EnterprisePolicy]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "listing enterprise policies")
    return store.list_enterprise_policies(x_tenant_id)


@router.get("/enterprise/policies/{policy_id}", response_model=EnterprisePolicy)
def get_enterprise_policy_endpoint(
    policy_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> EnterprisePolicy:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "reading enterprise policies")
    try:
        return store.get_enterprise_policy(x_tenant_id, policy_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete("/enterprise/policies/{policy_id}", status_code=200)
def delete_enterprise_policy_endpoint(
    policy_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> DeleteResponse:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, ADMIN_ROLES, "deleting enterprise policies")
    store.delete_enterprise_policy(x_tenant_id, policy_id)
    return DeleteResponse(status="deleted", policy_id=policy_id)


@router.get("/enterprise/policies/{policy_id}/clauses", response_model=List[EnterpriseClause])
def list_policy_clauses_endpoint(
    policy_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[EnterpriseClause]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "listing policy clauses")
    return store.list_enterprise_clauses(x_tenant_id, policy_id=policy_id)


@router.put("/enterprise/clauses/{clause_id}/review", response_model=EnterpriseClause)
def review_enterprise_clause_endpoint(
    clause_id: str,
    req: ClauseReviewRequest,
    x_tenant_id: TenantHeader,
    x_actor: OptionalActorHeader = None,
    x_role: OptionalRoleHeader = None,
    x_workspace_context: WorkspaceContextHeader = None,
) -> EnterpriseClause:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _validate_reviewer_identity(
        req.actor,
        req.role,
        header_actor=x_actor,
        header_role=x_role,
        x_workspace_context=x_workspace_context,
        tenant_id=x_tenant_id,
    )
    try:
        return store.update_clause_review(
            x_tenant_id,
            clause_id,
            status=req.status,
            actor=req.actor,
            role=req.role,
            mappings=req.control_mappings,
            review_comment=req.review_comment,
        )
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.put(
    "/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
    response_model=ClauseControlMapping,
)
def review_enterprise_clause_mapping_endpoint(
    clause_id: str,
    mapping_id: str,
    req: ClauseMappingReviewRequest,
    x_tenant_id: TenantHeader,
    x_actor: OptionalActorHeader = None,
    x_role: OptionalRoleHeader = None,
    x_workspace_context: WorkspaceContextHeader = None,
) -> ClauseControlMapping:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _validate_reviewer_identity(
        req.actor,
        req.role,
        header_actor=x_actor,
        header_role=x_role,
        x_workspace_context=x_workspace_context,
        tenant_id=x_tenant_id,
    )
    try:
        return store.update_clause_mapping_review(
            x_tenant_id,
            clause_id,
            mapping_id,
            status=req.status,
            actor=req.actor,
            role=req.role,
            relationship=req.relationship,
            mapped_facets=req.mapped_facets,
            review_comment=req.review_comment,
        )
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.post("/enterprise/baselines", response_model=EnterpriseBaseline, status_code=201)
def create_enterprise_baseline_endpoint(
    req: EnterpriseBaselineCreateRequest,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> EnterpriseBaseline:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, REVIEWER_ROLES, "compiling an enterprise baseline"
    )
    policies = []
    for pid in req.policy_ids:
        try:
            pol = store.get_enterprise_policy(x_tenant_id, pid)
            policies.append(pol)
        except NotFoundError as exc:
            raise _not_found(exc) from exc

    existing = store.list_enterprise_baselines(x_tenant_id)
    same_name = [b for b in existing if b.name == req.name]
    revision = max([b.revision for b in same_name], default=0) + 1

    try:
        baseline = compile_enterprise_baseline(
            tenant_id=x_tenant_id,
            name=req.name,
            description=req.description,
            policies=policies,
            version=req.version or "1.0.0",
            revision=revision,
            status=req.status or "active",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    try:
        return store.save_enterprise_baseline(x_tenant_id, baseline)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/enterprise/baselines", response_model=List[EnterpriseBaseline])
def list_enterprise_baselines_endpoint(
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[EnterpriseBaseline]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "listing enterprise baselines")
    return store.list_enterprise_baselines(x_tenant_id)


@router.get("/enterprise/baselines/{baseline_id}", response_model=EnterpriseBaseline)
def get_enterprise_baseline_endpoint(
    baseline_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> EnterpriseBaseline:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(x_role, READER_ROLES, "reading enterprise baselines")
    try:
        return store.get_enterprise_baseline(x_tenant_id, baseline_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc


class ReconcileBaselineRequest(BaseModel):
    use_case_id: Optional[str] = None
    use_case: Optional[BankingUseCase] = None
    include_non_applicable: bool = False
    force_regenerate: bool = False


class ReconciliationReviewRequest(BaseModel):
    decision_status: ReconciliationDecisionStatus
    approved_relationship: Optional[ReconciliationRelationship] = None
    actor: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=64)
    comment: Optional[str] = None
    expected_revision: Optional[int] = None


class ComposeEffectiveBaselineRequest(BaseModel):
    use_case_id: Optional[str] = None
    use_case: Optional[BankingUseCase] = None
    as_of_date: Optional[str] = None


def _resolve_baseline_and_policies(
    tenant_id: str, baseline_id: str
) -> tuple[EnterpriseBaseline, List[EnterprisePolicy]]:
    try:
        baseline = store.get_enterprise_baseline(tenant_id, baseline_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    if not verify_baseline_integrity(baseline):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Baseline integrity error: cryptographic fingerprint mismatch",
        )
    policies: List[EnterprisePolicy] = []
    for pid in baseline.policy_ids:
        try:
            policies.append(store.get_enterprise_policy(tenant_id, pid))
        except NotFoundError:
            pass
    return baseline, policies


@router.post(
    "/enterprise/baselines/{baseline_id}/reconcile",
    response_model=List[ReconciliationDecision],
    status_code=201,
)
@router.post(
    "/enterprise-baselines/{baseline_id}/reconcile",
    response_model=List[ReconciliationDecision],
    status_code=201,
)
def reconcile_enterprise_baseline_endpoint(
    baseline_id: str,
    x_tenant_id: TenantHeader,
    req: Optional[ReconcileBaselineRequest] = None,
    x_actor: OptionalActorHeader = None,
    x_role: OptionalRoleHeader = None,
) -> List[ReconciliationDecision]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, CONTRIBUTOR_ROLES, "generating requirement reconciliation candidates"
    )
    baseline, policies = _resolve_baseline_and_policies(x_tenant_id, baseline_id)
    body = req or ReconcileBaselineRequest()

    use_case: Optional[BankingUseCase] = None
    if body.use_case is not None:
        use_case = body.use_case
    elif body.use_case_id:
        try:
            use_case = store.get_use_case(x_tenant_id, body.use_case_id)
        except NotFoundError as exc:
            raise _not_found(exc) from exc

    candidates = generate_reconciliation_candidates(
        tenant_id=x_tenant_id,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=policies,
        use_case=use_case,
        include_non_applicable=body.include_non_applicable,
    )

    existing = {
        d.reconciliation_id: evaluate_reconciliation_staleness(
            d,
            enterprise_baseline=baseline,
            regulatory_pack=regulatory_pack,
            policies=policies,
        )
        for d in store.list_reconciliation_decisions(
            x_tenant_id, baseline_id=baseline_id
        )
    }

    to_save: List[ReconciliationDecision] = []
    for cand in candidates:
        prev = existing.get(cand.reconciliation_id)
        if (
            prev is not None
            and not body.force_regenerate
            and not prev.is_stale
            and prev.decision_status
            in {
                ReconciliationDecisionStatus.APPROVED,
                ReconciliationDecisionStatus.REJECTED,
            }
        ):
            to_save.append(prev)
        else:
            to_save.append(cand)

    return store.save_reconciliation_decisions(
        x_tenant_id, to_save, actor=x_actor or "system"
    )


@router.get(
    "/enterprise/baselines/{baseline_id}/reconciliations",
    response_model=List[ReconciliationDecision],
)
@router.get(
    "/enterprise-baselines/{baseline_id}/reconciliations",
    response_model=List[ReconciliationDecision],
)
def list_baseline_reconciliations_endpoint(
    baseline_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[ReconciliationDecision]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, READER_ROLES, "listing requirement reconciliations"
    )
    baseline, policies = _resolve_baseline_and_policies(x_tenant_id, baseline_id)
    decisions = store.list_reconciliation_decisions(
        x_tenant_id, baseline_id=baseline_id
    )
    return [
        evaluate_reconciliation_staleness(
            d,
            enterprise_baseline=baseline,
            regulatory_pack=regulatory_pack,
            policies=policies,
        )
        for d in decisions
    ]


@router.get(
    "/enterprise/baselines/{baseline_id}/reconciliations/unresolved",
    response_model=List[ReconciliationDecision],
)
@router.get(
    "/enterprise-baselines/{baseline_id}/reconciliations/unresolved",
    response_model=List[ReconciliationDecision],
)
def list_unresolved_reconciliations_endpoint(
    baseline_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[ReconciliationDecision]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, READER_ROLES, "listing unresolved requirement reconciliations"
    )
    all_decisions = list_baseline_reconciliations_endpoint(
        baseline_id=baseline_id, x_tenant_id=x_tenant_id, x_role=x_role
    )
    unresolved: List[ReconciliationDecision] = []
    for d in all_decisions:
        effective_rel = d.approved_relationship or d.validated_relationship
        if (
            d.is_stale
            or d.decision_status
            in {
                ReconciliationDecisionStatus.PROPOSED,
                ReconciliationDecisionStatus.NEEDS_REVIEW,
            }
            or effective_rel
            in {
                ReconciliationRelationship.POTENTIAL_CONFLICT,
                ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
                ReconciliationRelationship.UNDETERMINED,
            }
        ):
            unresolved.append(d)
    return unresolved


@router.put(
    "/enterprise/reconciliations/{reconciliation_id}/review",
    response_model=ReconciliationDecision,
)
@router.post(
    "/enterprise/reconciliations/{reconciliation_id}/review",
    response_model=ReconciliationDecision,
)
@router.post(
    "/reconciliations/{reconciliation_id}/review",
    response_model=ReconciliationDecision,
)
def review_reconciliation_endpoint(
    reconciliation_id: str,
    req: ReconciliationReviewRequest,
    x_tenant_id: TenantHeader,
    x_actor: OptionalActorHeader = None,
    x_role: OptionalRoleHeader = None,
    x_workspace_context: WorkspaceContextHeader = None,
) -> ReconciliationDecision:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _validate_reviewer_identity(
        req.actor,
        req.role,
        header_actor=x_actor,
        header_role=x_role,
        x_workspace_context=x_workspace_context,
        tenant_id=x_tenant_id,
    )
    try:
        existing = store.get_reconciliation_decision(x_tenant_id, reconciliation_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc

    baseline, policies = _resolve_baseline_and_policies(
        x_tenant_id, existing.enterprise_baseline_id
    )
    checked = evaluate_reconciliation_staleness(
        existing,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=policies,
    )
    try:
        reviewed = review_reconciliation_decision(
            checked,
            decision_status=req.decision_status,
            actor=req.actor,
            role=req.role,
            approved_relationship=req.approved_relationship,
            comment=req.comment,
            expected_revision=req.expected_revision,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        if "Stale revision" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return store.save_reconciliation_decision(
        x_tenant_id, reviewed, actor=req.actor
    )


@router.post(
    "/enterprise/baselines/{baseline_id}/effective-baseline",
    response_model=EffectiveAssessmentBaseline,
    status_code=201,
)
@router.post(
    "/enterprise-baselines/{baseline_id}/effective-baseline",
    response_model=EffectiveAssessmentBaseline,
    status_code=201,
)
def compose_effective_baseline_endpoint(
    baseline_id: str,
    x_tenant_id: TenantHeader,
    req: Optional[ComposeEffectiveBaselineRequest] = None,
    x_actor: OptionalActorHeader = None,
    x_role: OptionalRoleHeader = None,
) -> EffectiveAssessmentBaseline:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, CONTRIBUTOR_ROLES, "composing an effective assessment baseline"
    )
    baseline, policies = _resolve_baseline_and_policies(x_tenant_id, baseline_id)
    body = req or ComposeEffectiveBaselineRequest()

    use_case: Optional[BankingUseCase] = None
    if body.use_case is not None:
        use_case = body.use_case
    elif body.use_case_id:
        try:
            use_case = store.get_use_case(x_tenant_id, body.use_case_id)
        except NotFoundError as exc:
            raise _not_found(exc) from exc

    decisions = store.list_reconciliation_decisions(
        x_tenant_id, baseline_id=baseline_id
    )
    try:
        effective = compose_effective_assessment_baseline(
            tenant_id=x_tenant_id,
            regulatory_pack=regulatory_pack,
            use_case=use_case,
            enterprise_baseline=baseline,
            reconciliation_decisions=decisions,
            policies=policies,
            as_of_date=body.as_of_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return store.save_effective_baseline(
        x_tenant_id, effective, actor=x_actor or "system"
    )


@router.get(
    "/enterprise/effective-baselines/{effective_baseline_id}",
    response_model=EffectiveAssessmentBaseline,
)
@router.get(
    "/effective-baselines/{effective_baseline_id}",
    response_model=EffectiveAssessmentBaseline,
)
def get_effective_baseline_endpoint(
    effective_baseline_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> EffectiveAssessmentBaseline:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, READER_ROLES, "reading effective assessment baselines"
    )
    try:
        return store.get_effective_baseline(x_tenant_id, effective_baseline_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/enterprise/baselines/{baseline_id}/effective-baselines",
    response_model=List[EffectiveAssessmentBaseline],
)
def list_effective_baselines_endpoint(
    baseline_id: str,
    x_tenant_id: TenantHeader,
    x_role: OptionalRoleHeader = None,
) -> List[EffectiveAssessmentBaseline]:
    _reject_public_demo_tenant(x_tenant_id)
    _require_crosswalk_state()
    _enforce_role_if_present(
        x_role, READER_ROLES, "listing effective assessment baselines"
    )
    _resolve_baseline_and_policies(x_tenant_id, baseline_id)
    return store.list_effective_baselines(x_tenant_id, baseline_id=baseline_id)
