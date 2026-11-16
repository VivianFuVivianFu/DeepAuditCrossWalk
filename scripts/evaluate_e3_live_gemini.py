#!/usr/bin/env python3
"""Reproducible CLI Evaluation Script for E3 / E3.1 Deterministic, Mock & Live Gemini Benchmarks.

Usage examples:
  # Offline reproducible mock calibration across E3.1 adversarial benchmark:
  python scripts/evaluate_e3_live_gemini.py --provider mock --benchmark e31 --split all

  # Live Gemini evaluation on synthetic datasets (free tier allowed strictly for synthetic data):
  GEMINI_API_KEY=... python scripts/evaluate_e3_live_gemini.py --provider gemini --probe-models --benchmark all --split all --rpm-delay 4.2 --output-json eval_live.json --output-md eval_live.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
BACKEND_TESTS_DIR = BACKEND_DIR / "tests"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_TESTS_DIR))

from banking_crosswalk.llm.eval_harness import (  # noqa: E402
    render_evaluation_markdown,
    run_evaluation_suite,
)
from banking_crosswalk.llm.security import scrub_secrets  # noqa: E402
from banking_crosswalk.llm.types import ProviderConfigurationError  # noqa: E402
from e31_calibration_dataset import E31_CALIBRATION_CLAUSES  # noqa: E402
from e3_benchmark_dataset import E3_EXTENDED_CLAUSES, E3_QUESTIONNAIRE_CASES  # noqa: E402
from e11_benchmark_dataset import (  # noqa: E402
    E11_BENCHMARK_CLAUSES,
    _build_docx_bytes,
    _build_pdf_bytes,
)


def _build_benchmark_doc_bytes(paragraphs: Sequence[str], fmt: str, title: str) -> bytes:
    if fmt == "pdf":
        return _build_pdf_bytes(paragraphs, title)
    if fmt == "docx":
        return _build_docx_bytes(paragraphs)
    return ("\n\n".join(paragraphs)).encode("utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate DeepAudit Crosswalk semantic matching across mock or live Gemini providers."
    )
    parser.add_argument(
        "--provider",
        choices=("mock", "gemini"),
        default="mock",
        help="Evaluation provider backend (default: mock).",
    )
    parser.add_argument(
        "--benchmark",
        choices=("e11", "e3", "e31", "questionnaire", "all"),
        default="e31",
        help="Benchmark suite to execute (default: e31).",
    )
    parser.add_argument(
        "--split",
        choices=("all", "dev", "held_out"),
        default="all",
        help="Dataset split filter (default: all).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GEMINI_REASONING_MODEL", "gemini-2.5-flash"),
        help="Gemini reasoning model ID (default: env GEMINI_REASONING_MODEL or gemini-2.5-flash).",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        help="Gemini embedding model ID (default: env GEMINI_EMBEDDING_MODEL or gemini-embedding-001).",
    )
    parser.add_argument(
        "--billing-tier",
        choices=("free", "paid"),
        default=os.getenv("GEMINI_BILLING_TIER", "free"),
        help="Gemini billing tier for rate-limit guidance (synthetic benchmarks are allowed on free tier).",
    )
    parser.add_argument(
        "--rpm-delay",
        type=float,
        default=0.0,
        help="Minimum interval in seconds between sequential Gemini API calls (e.g. 4.2 for 15 RPM free tier).",
    )
    parser.add_argument(
        "--probe-models",
        action="store_true",
        help="Probe configured Gemini models via GET /models before running benchmarks.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional output path to write full JSON metrics (no secrets written).",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional output path to write summary Markdown report.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    api_key = None
    if args.provider == "gemini":
        api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        if not api_key:
            sys.stderr.write(
                "ERROR: Missing live Gemini credentials. Export GEMINI_API_KEY in your shell "
                "environment before running --provider gemini. Never commit API keys to git.\n"
            )
            return 2

    datasets: Dict[str, Sequence[Any]] = {}
    if args.benchmark in {"e11", "all"}:
        datasets["e11"] = E11_BENCHMARK_CLAUSES
    if args.benchmark in {"e3", "all"}:
        datasets["e3"] = E3_EXTENDED_CLAUSES
    if args.benchmark in {"e31", "all"}:
        datasets["e31"] = E31_CALIBRATION_CLAUSES

    q_cases = E3_QUESTIONNAIRE_CASES if args.benchmark in {"questionnaire", "all"} else ()

    try:
        report = run_evaluation_suite(
            datasets=datasets,
            questionnaire_cases=q_cases,
            provider=args.provider,
            split=args.split,
            gemini_api_key=api_key,
            gemini_billing_tier=args.billing_tier,
            embedding_model=args.embedding_model,
            reasoning_model=args.model,
            rpm_min_interval_seconds=args.rpm_delay,
            probe_models=args.probe_models,
            doc_bytes_builder=_build_benchmark_doc_bytes,
        )
    except ProviderConfigurationError as exc:
        sys.stderr.write(f"CONFIGURATION ERROR: {scrub_secrets(str(exc))}\n")
        return 2
    except Exception as exc:
        sys.stderr.write(f"EVALUATION ERROR: {scrub_secrets(str(exc))}\n")
        return 1

    md_text = render_evaluation_markdown(report)
    print(md_text)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md_text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
