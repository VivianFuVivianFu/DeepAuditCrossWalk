"""Security, privacy, prompt-injection sanitization, and citation controls for E3 LLM calls."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import re
import threading
import time
from typing import Deque, Iterator, Optional

from ..models import AtomicObligation
from .types import (
    CitationVerificationError,
    ConfidentialityPolicyError,
    DataClassification,
    DeploymentEdition,
    LLMProviderKind,
    LLMRuntimeConfig,
    ProviderConfigurationError,
    ProviderQuotaError,
    QuestionnaireSemanticMatchAnalysis,
    SemanticMatchingMode,
    SemanticRelationshipAnalysis,
)


_INJECTION_PATTERNS = (
    re.compile(r"<\s*/?\s*(?:system|assistant|user|developer|tool|instruction)[^>]*>", re.I),
    re.compile(r"\[/?(?:INST|SYS|SYSTEM|PROMPT)\]", re.I),
    re.compile(r"(?im)^\s*(?:ignore\s+(?:all\s+)?previous\s+instructions|override\s+system\s+prompt|system\s+override|always\s+return\s+equivalent|mark\s+as\s+approved)\b.*$"),
    re.compile(r"<\|[^|>]{1,40}\|>"),
)

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"sk-[0-9A-Za-z\-_]{16,}"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)([?&](?:api_key|key|token)=)[^&\s]+"),
)

_LOCALHOST_HTTP_PREFIXES = ("http://127.0.0.1", "http://localhost", "http://[::1]")


def sanitize_untrusted_text(text: str, *, max_chars: int = 4000) -> str:
    """Neutralize control chars and prompt-injection directives in untrusted document text."""
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\ufeff]", " ", text)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub(" [sanitized-untrusted-directive] ", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + " ..."
    return cleaned


def scrub_secrets(text: str) -> str:
    """Redact API keys, Bearer tokens, and key query parameters from logs and errors."""
    out = str(text or "")
    for pat in _SECRET_PATTERNS:
        if pat.groups:
            out = pat.sub(r"\1[REDACTED]", out)
        else:
            out = pat.sub("[REDACTED]", out)
    return out


def validate_endpoint_url(url: Optional[str], *, label: str) -> str:
    """Ensure external LLM endpoints use HTTPS (allow plain HTTP only for loopback dev)."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise ProviderConfigurationError(f"{label} endpoint URL is required.")
    lower = raw.lower()
    if lower.startswith("https://"):
        return raw
    if any(lower.startswith(prefix) for prefix in _LOCALHOST_HTTP_PREFIXES):
        return raw
    raise ProviderConfigurationError(
        f"{label} must use https:// (plain http:// is allowed only for loopback addresses)."
    )


def resolve_provider_api_key(
    config: LLMRuntimeConfig,
    *,
    provider: LLMProviderKind,
    purpose: str,
) -> Optional[str]:
    """Enforce credential isolation between Official Hosted Edition and Self-Hosted Edition.

    - Official Hosted (`official_hosted`): uses server-side `HOSTED_GEMINI_API_KEY`
      (or explicit `GEMINI_API_KEY` in single-tenant dev) for Gemini.
    - Self-Hosted (`self_hosted`): STRICTLY rejects/ignores `HOSTED_GEMINI_API_KEY`;
      requires the user's own `GEMINI_API_KEY` or `LLM_*_API_KEY`.
    """
    if provider in {LLMProviderKind.DISABLED, LLMProviderKind.MOCK}:
        return None

    if provider == LLMProviderKind.GEMINI:
        if config.edition == DeploymentEdition.OFFICIAL_HOSTED:
            key = (config.hosted_gemini_api_key or "").strip()
            if not key:
                raise ProviderConfigurationError(
                    "Official hosted edition requires server-side HOSTED_GEMINI_API_KEY."
                )
            return key
        # Self-hosted open-source edition must NEVER inherit the project's hosted key
        key = (config.gemini_api_key or "").strip()
        if not key:
            raise ProviderConfigurationError(
                "Self-hosted edition requires user-supplied GEMINI_API_KEY; "
                "it never inherits the project's hosted key."
            )
        if (
            config.hosted_gemini_api_key
            and key == config.hosted_gemini_api_key.strip()
        ):
            raise ProviderConfigurationError(
                "Self-hosted edition cannot share or inherit HOSTED_GEMINI_API_KEY."
            )
        return key

    if provider == LLMProviderKind.OPENAI_COMPATIBLE:
        if purpose == "embedding":
            key = (config.openai_embedding_api_key or config.openai_api_key or "").strip()
        else:
            key = (config.openai_reasoning_api_key or config.openai_api_key or "").strip()
        if not key:
            raise ProviderConfigurationError(
                f"OpenAI-compatible {purpose} provider requires user-supplied API credentials."
            )
        return key

    raise ProviderConfigurationError(f"Unsupported provider '{provider}'.")


def enforce_free_tier_confidentiality(
    config: LLMRuntimeConfig,
    *,
    provider: LLMProviderKind,
    data_classification: DataClassification,
    tenant_id: Optional[str] = None,
) -> None:
    """Prevent sending real confidential customer documents to Gemini free-tier APIs.

    Even if `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER` is set in the environment,
    `DataClassification.CONFIDENTIAL_ENTERPRISE` strictly requires `GEMINI_BILLING_TIER=paid`
    (only `PUBLIC_OR_SYNTHETIC` or `public-demo` inputs may touch free-tier Gemini).
    """
    if provider != LLMProviderKind.GEMINI:
        return
    if config.gemini_billing_tier == "paid":
        return
    if data_classification == DataClassification.PUBLIC_OR_SYNTHETIC:
        return
    if tenant_id == "public-demo":
        return
    raise ConfidentialityPolicyError(
        "Blocked attempt to send confidential enterprise policy content to Google Gemini "
        "free-tier service (where inputs may be used for product improvement/human review). "
        "Configure GEMINI_BILLING_TIER=paid with an enterprise billing project, use a "
        "private self-hosted OpenAI-compatible endpoint, or operate in deterministic mode."
    )


def enforce_runtime_confidentiality(
    config: LLMRuntimeConfig,
    *,
    data_classification: DataClassification,
    tenant_id: Optional[str] = None,
) -> None:
    """Enforce data-classification policy across active providers before credential/provider init."""
    if not config.semantic_matching_enabled or config.matching_mode == SemanticMatchingMode.DISABLED:
        return
    enforce_free_tier_confidentiality(
        config,
        provider=config.embedding_provider,
        data_classification=data_classification,
        tenant_id=tenant_id,
    )
    if config.matching_mode == SemanticMatchingMode.HYBRID:
        enforce_free_tier_confidentiality(
            config,
            provider=config.reasoning_provider,
            data_classification=data_classification,
            tenant_id=tenant_id,
        )


def _normalise_for_quote(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _quote_grounded_in(quote: str, source_text: str) -> bool:
    q_norm = _normalise_for_quote(quote)
    s_norm = _normalise_for_quote(source_text)
    if not q_norm or not s_norm:
        return False
    if q_norm in s_norm:
        return True
    # Allow minor punctuation/elision differences if >= 80% of substantial tokens appear cleanly
    q_tokens = [tok for tok in q_norm.split() if len(tok) >= 3]
    if len(q_tokens) < 3:
        return False
    s_tokens = set(s_norm.split())
    overlap = sum(1 for tok in q_tokens if tok in s_tokens)
    return (overlap / len(q_tokens)) >= 0.80


def validate_semantic_citation(
    analysis: SemanticRelationshipAnalysis | QuestionnaireSemanticMatchAnalysis,
    *,
    source_text: str,
    obligation: AtomicObligation,
) -> None:
    """Reject fabricated obligation IDs, mismatched provisions, or ungrounded quotes."""
    if analysis.cited_obligation_id.strip() != obligation.obligation_id:
        raise CitationVerificationError(
            f"Fabricated or mismatched obligation citation: model cited "
            f"'{analysis.cited_obligation_id}' instead of '{obligation.obligation_id}'."
        )
    cited_prov_norm = _normalise_for_quote(analysis.cited_provision)
    expected_prov_norm = _normalise_for_quote(obligation.provision)
    # Strip English words 'section'/'sections'/'paragraph'/'article' -> 's'/'ss'/'para'/'art' for fair normalisation
    cited_compact = re.sub(r"\bsections?\b", "ss", cited_prov_norm)
    expected_compact = re.sub(r"\bsections?\b", "ss", expected_prov_norm)
    cited_toks = {t for t in cited_compact.split() if len(t) >= 2}
    expected_toks = {t for t in expected_compact.split() if len(t) >= 2}
    has_shared_specific_tok = any(
        t in expected_toks and (any(ch.isdigit() for ch in t) or t in {"app", "cps", "cpg", "rg", "rep", "nccp", "art", "oaic", "ndb", "naic"})
        for t in cited_toks
    )
    prov_matches = (
        cited_prov_norm == expected_prov_norm
        or expected_prov_norm in cited_prov_norm
        or (
            len(cited_prov_norm) >= 4
            and cited_prov_norm in expected_prov_norm
            and has_shared_specific_tok
        )
        or (has_shared_specific_tok and len(cited_toks & expected_toks) >= 2 and all(t in expected_toks for t in cited_toks if any(ch.isdigit() for ch in t)))
    )
    if not prov_matches:
        raise CitationVerificationError(
            f"Fabricated provision citation: model cited '{analysis.cited_provision}' "
            f"for obligation '{obligation.obligation_id}' (expected '{obligation.provision}')."
        )

    source_quote = (
        analysis.supporting_clause_quote
        if isinstance(analysis, SemanticRelationshipAnalysis)
        else analysis.supporting_question_quote
    )
    if not _quote_grounded_in(source_quote, source_text):
        raise CitationVerificationError(
            "Model supporting source quote is not grounded in the input document text."
        )

    ob_corpus = " ".join(
        [
            obligation.instrument,
            obligation.provision,
            obligation.title,
            obligation.concise_obligation_summary,
            obligation.control_objective or "",
        ]
    )
    if not _quote_grounded_in(analysis.supporting_obligation_quote, ob_corpus):
        raise CitationVerificationError(
            f"Model obligation quote is not grounded in '{obligation.obligation_id}'."
        )


class APICallBudgetTracker:
    """Thread-safe per-run call count, RPM window, and concurrency guard."""

    def __init__(
        self,
        *,
        max_calls_per_run: int = 40,
        max_calls_per_minute: int = 30,
        max_concurrency: int = 4,
    ) -> None:
        self.max_calls_per_run = max(1, max_calls_per_run)
        self.max_calls_per_minute = max(1, max_calls_per_minute)
        self._semaphore = threading.Semaphore(max(1, max_concurrency))
        self._lock = threading.Lock()
        self._run_calls = 0
        self._timestamps: Deque[float] = deque()

    @property
    def calls_used(self) -> int:
        with self._lock:
            return self._run_calls

    def acquire(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._run_calls >= self.max_calls_per_run:
                raise ProviderQuotaError(
                    f"Per-run LLM API call budget exceeded ({self.max_calls_per_run} calls)."
                )
            while self._timestamps and (now - self._timestamps[0]) > 60.0:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_calls_per_minute:
                raise ProviderQuotaError(
                    f"Per-minute LLM API rate budget exceeded ({self.max_calls_per_minute} RPM)."
                )
            self._run_calls += 1
            self._timestamps.append(now)

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
