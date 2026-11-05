"""Data models for Phase P1B semantic mapping experiments.

These models define the standardised prediction, evaluation, and reporting interfaces
for experimental engines (A0, A1, B, C). No ground-truth labels are ever passed to engines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ThresholdAST:
    """Parsed numerical threshold constraint."""
    amount: float
    operator: str  # '>=', '>', '<=', '<', '='
    currency: str | None = "AUD"
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidatePrediction:
    """A single predicted control or facet mapping candidate."""
    clause_id: str
    canonical_control_id: str | None = None
    canonical_facet_id: str | None = None
    score: float = 1.0
    review_status: str = "proposed"  # Invariant: ALWAYS "proposed", never "approved"
    normative_type: str | None = None
    is_suppressed: bool = False
    is_ambiguous: bool = False
    rationale: str = ""
    threshold_ast: ThresholdAST | None = None

    def __post_init__(self):
        # Enforce governance safety constraint: candidate review status must be proposed
        if self.review_status != "proposed":
            raise ValueError(
                f"CandidatePrediction review_status must be 'proposed', got '{self.review_status}'"
            )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.threshold_ast:
            d["threshold_ast"] = self.threshold_ast.to_dict()
        return d


@dataclass
class ExtractionResult:
    """The complete prediction payload emitted by an experimental engine for an input text."""
    case_id: str
    extracted_clauses: list[str] = field(default_factory=list)
    candidate_facets: list[str] = field(default_factory=list)
    candidate_controls: list[str] = field(default_factory=list)
    ranked_mappings: list[CandidatePrediction] = field(default_factory=list)
    threshold_ast: ThresholdAST | None = None
    is_suppressed: bool = False
    detected_normative_type: str | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "extracted_clauses": self.extracted_clauses,
            "candidate_facets": self.candidate_facets,
            "candidate_controls": self.candidate_controls,
            "ranked_mappings": [m.to_dict() for m in self.ranked_mappings],
            "threshold_ast": self.threshold_ast.to_dict() if self.threshold_ast else None,
            "is_suppressed": self.is_suppressed,
            "detected_normative_type": self.detected_normative_type,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class CaseEvaluationResult:
    """Detailed per-case evaluation scorecard across all layers."""
    case_id: str
    split: str
    category: str
    normative_type: str
    expected_candidate_behavior: str
    input_length_chars: int
    length_tier: str  # 'short' (<100), 'medium' (100-300), 'long' (>300)

    # Layer A: Atomic Segmentation / Requirement Extraction
    atomic_tp: int = 0
    atomic_fp: int = 0
    atomic_fn: int = 0

    # Layer B: Canonical Facet Multi-Label Classification
    facet_tp: int = 0
    facet_fp: int = 0
    facet_fn: int = 0
    predicted_facets: list[str] = field(default_factory=list)
    expected_facets: list[str] = field(default_factory=list)

    # Layer C: Canonical Unified Control Ranking & Safety
    top1_match: bool = False
    top3_match: bool = False
    top5_match: bool = False
    reciprocal_rank: float = 0.0
    predicted_controls: list[str] = field(default_factory=list)
    expected_controls: list[str] = field(default_factory=list)
    false_control_trigger: bool = False
    correct_suppression: bool = False

    # Layer F: Numeric Interval AST Validation
    threshold_evaluated: bool = False
    threshold_correct: bool = False

    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
