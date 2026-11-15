"""Type definitions, configuration, and structured output schemas for E3 Semantic Matching.

All models enforce strict schema validation so probabilistic LLM outputs remain
strictly bounded as AI-suggested hypotheses prior to Stage C deterministic checks
and Stage D human review.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
import os

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import ReconciliationRelationship


class LLMProviderKind(str, Enum):
    DISABLED = "disabled"
    MOCK = "mock"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai_compatible"


class DeploymentEdition(str, Enum):
    SELF_HOSTED = "self_hosted"
    OFFICIAL_HOSTED = "official_hosted"


class SemanticMatchingMode(str, Enum):
    DISABLED = "disabled"
    EMBEDDING_ONLY = "embedding_only"
    HYBRID = "hybrid"


class DataClassification(str, Enum):
    PUBLIC_OR_SYNTHETIC = "public_or_synthetic"
    CONFIDENTIAL_ENTERPRISE = "confidential_enterprise"


# Known Gemini model lifecycle table (verified Nov 2026)
GEMINI_MODEL_DEPRECATION_REGISTRY: Dict[str, Dict[str, str]] = {
    "gemini-2.5-flash": {
        "status": "deprecated_scheduled_migration",
        "cutoff_date": "2026-12-01",
        "replacement_model": "gemini-3.5-flash-lite",
        "notice": (
            "gemini-2.5-flash is deprecated and scheduled for automatic request rerouting "
            "to gemini-3.5-flash-lite on 2026-12-01; configure GEMINI_REASONING_MODEL to a "
            "current generation model before cutoff."
        ),
    },
    "gemini-embedding-001": {
        "status": "active",
        "cutoff_date": "",
        "replacement_model": "",
        "notice": "gemini-embedding-001 remains supported beyond December 2026.",
    },
}


class LLMProviderError(RuntimeError):
    """Base error for provider failures (never includes secrets)."""


class ProviderConfigurationError(LLMProviderError):
    """Raised when provider credentials or edition boundaries are misconfigured."""


class ConfidentialityPolicyError(LLMProviderError):
    """Raised when confidential tenant data would be sent to a disallowed free-tier endpoint."""


class ProviderQuotaError(LLMProviderError):
    """Raised on HTTP 429 rate-limit / quota exhaustion or local budget exhaustion."""


class ProviderTimeoutError(LLMProviderError):
    """Raised when an HTTP call exceeds timeout bounds."""


class ProviderUnavailableError(LLMProviderError):
    """Raised on upstream 5xx / network unavailability."""


class ProviderOutputError(LLMProviderError):
    """Raised on malformed, non-JSON, or schema-invalid LLM output."""


class CitationVerificationError(ProviderOutputError):
    """Raised when an LLM cites an unknown obligation, wrong provision, or fabricated quote."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class LLMRuntimeConfig(BaseModel):
    """Provider-agnostic configuration with strict credential isolation & budgets."""

    model_config = ConfigDict(extra="forbid")

    edition: DeploymentEdition = DeploymentEdition.SELF_HOSTED
    semantic_matching_enabled: bool = False
    matching_mode: SemanticMatchingMode = SemanticMatchingMode.DISABLED

    embedding_provider: LLMProviderKind = LLMProviderKind.DISABLED
    reasoning_provider: LLMProviderKind = LLMProviderKind.DISABLED

    # Google Gemini configuration
    gemini_api_key: Optional[str] = Field(default=None, exclude=True, repr=False)
    hosted_gemini_api_key: Optional[str] = Field(default=None, exclude=True, repr=False)
    gemini_billing_tier: Literal["free", "paid"] = "free"
    allow_confidential_on_free_tier: bool = False
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_reasoning_model: str = "gemini-2.5-flash"
    gemini_embedding_dimensions: int = Field(default=256, ge=32, le=3072)
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Generic OpenAI-compatible configuration (separate embedding & reasoning supported)
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = Field(default=None, exclude=True, repr=False)
    openai_embedding_base_url: Optional[str] = None
    openai_embedding_api_key: Optional[str] = Field(default=None, exclude=True, repr=False)
    openai_embedding_model: Optional[str] = None
    openai_embedding_supported: bool = True
    openai_reasoning_base_url: Optional[str] = None
    openai_reasoning_api_key: Optional[str] = Field(default=None, exclude=True, repr=False)
    openai_reasoning_model: Optional[str] = None
    openai_structured_output_supported: bool = True

    # Safety, timeout & budget controls
    request_timeout_seconds: float = Field(default=15.0, ge=0.5, le=120.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.25, ge=0.0, le=5.0)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    max_calls_per_run: int = Field(default=40, ge=1, le=500)
    max_calls_per_minute: int = Field(default=30, ge=1, le=600)
    max_input_chars: int = Field(default=4000, ge=256, le=32000)
    max_output_tokens: int = Field(default=1024, ge=128, le=8192)
    top_k_candidates: int = Field(default=5, ge=1, le=15)

    @classmethod
    def from_env(cls) -> "LLMRuntimeConfig":
        """Build configuration from environment variables with safe open-source defaults."""
        edition_raw = (os.getenv("CROSSWALK_EDITION") or "self_hosted").strip().lower()
        edition = (
            DeploymentEdition.OFFICIAL_HOSTED
            if edition_raw == "official_hosted"
            else DeploymentEdition.SELF_HOSTED
        )
        enabled = _env_bool("SEMANTIC_MATCHING_ENABLED", False)
        mode_raw = (os.getenv("SEMANTIC_MATCHING_MODE") or "").strip().lower()
        if not enabled or mode_raw in {"", "disabled"}:
            mode = SemanticMatchingMode.DISABLED if not enabled else SemanticMatchingMode.HYBRID
        elif mode_raw == "embedding_only":
            mode = SemanticMatchingMode.EMBEDDING_ONLY
        else:
            mode = SemanticMatchingMode.HYBRID

        def _parse_provider(raw_val: Optional[str], fallback: LLMProviderKind) -> LLMProviderKind:
            cleaned = (raw_val or "").strip().lower()
            for member in LLMProviderKind:
                if member.value == cleaned:
                    return member
            return fallback

        emb_prov = _parse_provider(os.getenv("LLM_EMBEDDING_PROVIDER"), LLMProviderKind.DISABLED)
        rsn_prov = _parse_provider(os.getenv("LLM_REASONING_PROVIDER"), LLMProviderKind.DISABLED)

        billing = (os.getenv("GEMINI_BILLING_TIER") or "free").strip().lower()
        billing_tier: Literal["free", "paid"] = "paid" if billing == "paid" else "free"

        return cls(
            edition=edition,
            semantic_matching_enabled=enabled,
            matching_mode=mode,
            embedding_provider=emb_prov,
            reasoning_provider=rsn_prov,
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            hosted_gemini_api_key=os.getenv("HOSTED_GEMINI_API_KEY") or None,
            gemini_billing_tier=billing_tier,
            allow_confidential_on_free_tier=_env_bool(
                "ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER", False
            ),
            gemini_embedding_model=(
                os.getenv("GEMINI_EMBEDDING_MODEL") or "gemini-embedding-001"
            ).strip(),
            gemini_reasoning_model=(
                os.getenv("GEMINI_REASONING_MODEL") or "gemini-2.5-flash"
            ).strip(),
            gemini_embedding_dimensions=int(
                os.getenv("GEMINI_EMBEDDING_DIMENSIONS") or "256"
            ),
            openai_base_url=os.getenv("LLM_BASE_URL") or None,
            openai_api_key=os.getenv("LLM_API_KEY") or None,
            openai_embedding_base_url=os.getenv("LLM_EMBEDDING_BASE_URL") or None,
            openai_embedding_api_key=os.getenv("LLM_EMBEDDING_API_KEY") or None,
            openai_embedding_model=os.getenv("LLM_EMBEDDING_MODEL") or None,
            openai_embedding_supported=_env_bool("LLM_EMBEDDING_SUPPORTED", True),
            openai_reasoning_base_url=os.getenv("LLM_REASONING_BASE_URL") or None,
            openai_reasoning_api_key=os.getenv("LLM_REASONING_API_KEY") or None,
            openai_reasoning_model=os.getenv("LLM_REASONING_MODEL") or None,
            openai_structured_output_supported=_env_bool(
                "LLM_STRUCTURED_OUTPUT_SUPPORTED", True
            ),
            request_timeout_seconds=float(
                os.getenv("LLM_REQUEST_TIMEOUT_SECONDS") or "15.0"
            ),
            max_retries=int(os.getenv("LLM_MAX_RETRIES") or "2"),
            max_concurrency=int(os.getenv("LLM_MAX_CONCURRENCY") or "4"),
            max_calls_per_run=int(os.getenv("LLM_MAX_CALLS_PER_RUN") or "40"),
            max_calls_per_minute=int(os.getenv("LLM_MAX_CALLS_PER_MINUTE") or "30"),
            max_input_chars=int(os.getenv("LLM_MAX_INPUT_CHARS") or "4000"),
            max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS") or "1024"),
        )


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: List[str] = Field(min_length=1, max_length=64)
    task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY"] = (
        "RETRIEVAL_QUERY"
    )
    data_classification: DataClassification = DataClassification.CONFIDENTIAL_ENTERPRISE


class EmbeddingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vectors: List[List[float]]
    dimensions: int
    provider: str
    model: str
    latency_ms: float = 0.0
    token_count: int = 0


class SemanticRelationshipAnalysis(BaseModel):
    """Structured LLM Stage B interpretation output — always AI-proposed, never approved."""

    model_config = ConfigDict(extra="forbid")

    clause_id: str = Field(min_length=1, max_length=128)
    external_obligation_id: str = Field(min_length=1, max_length=128)
    cited_obligation_id: str = Field(min_length=1, max_length=128)
    cited_provision: str = Field(min_length=1, max_length=256)
    proposed_relationship: ReconciliationRelationship
    semantic_relevance: Literal["high", "medium", "low", "none"]
    confidence: float = Field(ge=0.0, le=1.0)
    operational_scope: str = Field(min_length=1, max_length=500)
    required_actions_and_prohibitions: List[str] = Field(default_factory=list)
    approval_authority: Optional[str] = Field(default=None, max_length=200)
    timing: Optional[str] = Field(default=None, max_length=200)
    numerical_thresholds: List[str] = Field(default_factory=list)
    conditions_and_exceptions: List[str] = Field(default_factory=list)
    potential_contradiction: bool = False
    contradiction_detail: Optional[str] = Field(default=None, max_length=500)
    missing_requirement_facets: List[str] = Field(default_factory=list)
    inferred_covered_facets: List[str] = Field(default_factory=list)
    uncertainty_flags: List[str] = Field(default_factory=list)
    supporting_clause_quote: str = Field(min_length=1, max_length=1200)
    supporting_obligation_quote: str = Field(min_length=1, max_length=1200)
    reasoning_summary: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def _ensure_non_empty_quotes(self) -> "SemanticRelationshipAnalysis":
        if not self.supporting_clause_quote.strip():
            raise ValueError("supporting_clause_quote cannot be blank.")
        if not self.supporting_obligation_quote.strip():
            raise ValueError("supporting_obligation_quote cannot be blank.")
        return self


class QuestionnaireSemanticMatchAnalysis(BaseModel):
    """Structured semantic match for Questionnaire-to-Requirement harness (proposed only)."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=128)
    external_obligation_id: str = Field(min_length=1, max_length=128)
    cited_obligation_id: str = Field(min_length=1, max_length=128)
    cited_provision: str = Field(min_length=1, max_length=256)
    semantic_relevance: Literal["high", "medium", "low", "none"]
    confidence: float = Field(ge=0.0, le=1.0)
    candidate_covered_facets: List[str] = Field(default_factory=list)
    missing_facets: List[str] = Field(default_factory=list)
    uncertainty_flags: List[str] = Field(default_factory=list)
    supporting_question_quote: str = Field(min_length=1, max_length=1000)
    supporting_obligation_quote: str = Field(min_length=1, max_length=1000)
    reasoning_summary: str = Field(min_length=1, max_length=1000)


class ProviderLifecycleWarning(BaseModel):
    model: str
    status: str
    cutoff_date: Optional[date] = None
    replacement_model: Optional[str] = None
    message: str


class UsageTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_provider: str = "disabled"
    embedding_model: Optional[str] = None
    reasoning_provider: str = "disabled"
    reasoning_model: Optional[str] = None
    embedding_calls: int = 0
    embedding_texts: int = 0
    embedding_cache_hits: int = 0
    reasoning_calls: int = 0
    fallback_events: int = 0
    quota_or_rate_limit_errors: int = 0
    citation_rejections: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_latency_ms: float = 0.0
    lifecycle_warnings: List[ProviderLifecycleWarning] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
