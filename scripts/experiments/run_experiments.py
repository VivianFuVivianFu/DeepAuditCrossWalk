"""Main experiment execution script for Phase P1B-1.

Runs Head-to-Head evaluation of Engine A0 (Historical Production Baseline) vs
Engine A1 (Enhanced Deterministic Rules Engine) across:
  1. V2 Development Split (105 cases)
  2. Supplemental Adversarial Split (36 cases)
  3. V2 Holdout Split (51 cases)

Outputs structured result artifacts to scripts/experiments/artifacts/.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .canonical_adapter import CanonicalMappingAdapter
from .engine_a0 import EngineA0
from .engine_a1 import EngineA1
from .evaluator import evaluate_dataset


def get_git_commit(repo_root: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def run_all_experiments():
    repo_root = Path(__file__).resolve().parent.parent.parent
    v2_path = repo_root / "P1_EVALUATION_DATASET_V2.json"
    supp_path = repo_root / "P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json"
    ucl_path = repo_root / "UNIFIED_CONTROL_LIBRARY.json"
    artifacts_dir = repo_root / "scripts" / "experiments" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    git_commit = get_git_commit(repo_root)
    v2_hash = compute_sha256(v2_path)
    supp_hash = compute_sha256(supp_path)
    ucl_hash = compute_sha256(ucl_path)

    print("================================================================================")
    print("  PHASE P1B-1: DETERMINISTIC BASELINE EXPERIMENT (A0 vs A1)")
    print("================================================================================")
    print(f"Git Commit:              {git_commit}")
    print(f"P1_EVALUATION_DATASET_V2 SHA-256: {v2_hash[:16]}...")
    print(f"SUPPLEMENTAL DATASET SHA-256:     {supp_hash[:16]}...")
    print(f"UNIFIED CONTROL LIBRARY SHA-256:  {ucl_hash[:16]}...")
    print("--------------------------------------------------------------------------------")

    with open(v2_path, "r", encoding="utf-8") as f:
        v2_data = json.load(f)
    with open(supp_path, "r", encoding="utf-8") as f:
        supp_data = json.load(f)

    v2_dev = [c for c in v2_data["cases"] if c.get("split") == "development"]
    v2_holdout = [c for c in v2_data["cases"] if c.get("split") == "holdout"]
    supp_dev = supp_data.get("cases", [])

    print("Loaded Splits:")
    print(f"  - V2 Development:         {len(v2_dev)} cases")
    print(f"  - Supplemental Adversarial:{len(supp_dev)} cases")
    print(f"  - V2 Holdout (Frozen):    {len(v2_holdout)} cases")
    print("--------------------------------------------------------------------------------")

    adapter = CanonicalMappingAdapter(ucl_path)
    engine_a0 = EngineA0(adapter)
    engine_a1 = EngineA1(ucl_path)
    canonical_facet_universe = adapter.canonical_facets

    experiments = [
        ("A0", "Production Baseline (A0)", engine_a0),
        ("A1", "Enhanced Rules (A1)", engine_a1),
    ]

    splits = [
        ("dev", "V2 Development", v2_dev),
        ("supp", "Supplemental Adversarial", supp_dev),
        ("holdout", "V2 Holdout", v2_holdout),
    ]

    all_results: dict[str, dict[str, Any]] = {"A0": {}, "A1": {}}

    for eng_code, eng_name, engine in experiments:
        print(f"\n[Executing Engine {eng_code}: {eng_name}]")
        for split_code, split_name, cases in splits:
            print(f"  -> Running on {split_name} ({len(cases)} cases)...", end="", flush=True)
            res = evaluate_dataset(engine, cases, canonical_facet_universe)
            all_results[eng_code][split_code] = res
            print(" Done.")

            # Save individual artifact
            out_file = artifacts_dir / f"{eng_code.lower()}_{split_code}_results.json"
            meta_payload = {
                "engine": eng_code,
                "engine_name": eng_name,
                "split": split_code,
                "split_name": split_name,
                "total_cases": len(cases),
                "git_commit": git_commit,
                "v2_hash": v2_hash,
                "supp_hash": supp_hash,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "metrics": res["overall"],
                "by_normative_class": res["by_normative_class"],
                "by_category": res["by_category"],
                "by_length_tier": res["by_length_tier"],
                "individual_case_results": res["individual_case_results"],
            }
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(meta_payload, f, indent=2)

    # Build Comparison Summary
    summary_table = {}
    for split_code, split_name, cases in splits:
        m0 = all_results["A0"][split_code]["overall"]
        m1 = all_results["A1"][split_code]["overall"]

        summary_table[split_code] = {
            "split_name": split_name,
            "total_cases": len(cases),
            "A0": {
                "atomic_f1": m0["layer_a_atomic"]["f1"],
                "facet_f1_micro": m0["layer_b_facets"]["f1_micro"],
                "facet_coverage": m0["layer_b_facets"]["canonical_facet_coverage_rate"],
                "top1_recall": m0["layer_c_controls"]["top1_recall"],
                "top3_recall": m0["layer_c_controls"]["top3_recall"],
                "mrr": m0["layer_c_controls"]["mrr"],
                "ctrl_f1_micro": m0["layer_c_controls"]["micro_f1"],
                "suppression_accuracy": m0["layer_c_normative_safety"]["suppression_accuracy"],
                "false_trigger_rate": m0["layer_c_normative_safety"]["false_trigger_rate"],
                "threshold_accuracy": m0["layer_f_thresholds"]["threshold_accuracy"],
                "latency_mean_ms": m0["performance_latency_ms"]["mean"],
            },
            "A1": {
                "atomic_f1": m1["layer_a_atomic"]["f1"],
                "facet_f1_micro": m1["layer_b_facets"]["f1_micro"],
                "facet_coverage": m1["layer_b_facets"]["canonical_facet_coverage_rate"],
                "top1_recall": m1["layer_c_controls"]["top1_recall"],
                "top3_recall": m1["layer_c_controls"]["top3_recall"],
                "mrr": m1["layer_c_controls"]["mrr"],
                "ctrl_f1_micro": m1["layer_c_controls"]["micro_f1"],
                "suppression_accuracy": m1["layer_c_normative_safety"]["suppression_accuracy"],
                "false_trigger_rate": m1["layer_c_normative_safety"]["false_trigger_rate"],
                "threshold_accuracy": m1["layer_f_thresholds"]["threshold_accuracy"],
                "latency_mean_ms": m1["performance_latency_ms"]["mean"],
            },
            "delta_A1_minus_A0": {
                "atomic_f1": round(m1["layer_a_atomic"]["f1"] - m0["layer_a_atomic"]["f1"], 4),
                "facet_f1_micro": round(m1["layer_b_facets"]["f1_micro"] - m0["layer_b_facets"]["f1_micro"], 4),
                "facet_coverage": round(m1["layer_b_facets"]["canonical_facet_coverage_rate"] - m0["layer_b_facets"]["canonical_facet_coverage_rate"], 4),
                "top1_recall": round(m1["layer_c_controls"]["top1_recall"] - m0["layer_c_controls"]["top1_recall"], 4),
                "top3_recall": round(m1["layer_c_controls"]["top3_recall"] - m0["layer_c_controls"]["top3_recall"], 4),
                "mrr": round(m1["layer_c_controls"]["mrr"] - m0["layer_c_controls"]["mrr"], 4),
                "ctrl_f1_micro": round(m1["layer_c_controls"]["micro_f1"] - m0["layer_c_controls"]["micro_f1"], 4),
                "suppression_accuracy": round(m1["layer_c_normative_safety"]["suppression_accuracy"] - m0["layer_c_normative_safety"]["suppression_accuracy"], 4),
                "false_trigger_rate": round(m1["layer_c_normative_safety"]["false_trigger_rate"] - m0["layer_c_normative_safety"]["false_trigger_rate"], 4),
                "threshold_accuracy": round(m1["layer_f_thresholds"]["threshold_accuracy"] - m0["layer_f_thresholds"]["threshold_accuracy"], 4),
            }
        }

    comparison_payload = {
        "git_commit": git_commit,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_hashes": {
            "v2_hash": v2_hash,
            "supp_hash": supp_hash,
            "ucl_hash": ucl_hash,
        },
        "summary_table": summary_table,
    }
    comp_file = artifacts_dir / "comparison_summary.json"
    with open(comp_file, "w", encoding="utf-8") as f:
        json.dump(comparison_payload, f, indent=2)

    print("\n================================================================================")
    print("  HEAD-TO-HEAD SUMMARY: ENGINE A0 vs ENGINE A1")
    print("================================================================================")
    print(f"{'Split':<25} | {'Metric':<25} | {'A0 (Baseline)':<12} | {'A1 (Enhanced)':<12} | {'Delta':<10}")
    print("-" * 90)

    for split_code, data in summary_table.items():
        sname = data["split_name"]
        print(f"[{sname}]")
        metrics_to_show = [
            ("Facet F1 Micro", "facet_f1_micro"),
            ("Facet UCL Coverage", "facet_coverage"),
            ("Top-1 Control Recall", "top1_recall"),
            ("Top-3 Control Recall", "top3_recall"),
            ("Control MRR", "mrr"),
            ("Control Micro F1", "ctrl_f1_micro"),
            ("Suppression Accuracy", "suppression_accuracy"),
            ("False Trigger Rate", "false_trigger_rate"),
            ("Threshold Accuracy", "threshold_accuracy"),
            ("Mean Latency (ms)", "latency_mean_ms"),
        ]
        for label, mkey in metrics_to_show:
            val0 = data["A0"].get(mkey, 0.0)
            val1 = data["A1"].get(mkey, 0.0)
            delta = data.get("delta_A1_minus_A0", {}).get(mkey, round(val1 - val0, 4))
            delta_str = f"{delta:+.4f}" if isinstance(delta, float) else f"{delta}"
            print(f"  {label:<23} | {val0:<12.4f} | {val1:<12.4f} | {delta_str:<10}")
        print("-" * 90)

    print(f"\nAll artifacts successfully saved to: {artifacts_dir}")


if __name__ == "__main__":
    run_all_experiments()
