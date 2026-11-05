"""Script to audit all AIAF references across the repository."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re


def audit_repository():
    repo_root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\baiaf\b", re.IGNORECASE)

    active_runtime_files = []
    test_files = []
    script_files = []
    documentation_files = []
    historical_audit_files = []

    inventory = {}

    for root, dirs, files in os.walk(repo_root):
        if any(ignored in root for ignored in [".git", ".venv", ".pytest_cache", ".ruff_cache", "node_modules", ".vercel"]):
            continue
        for file in files:
            path = Path(root) / file
            rel_path = path.relative_to(repo_root).as_posix()
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            matches = []
            for i, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    matches.append((i, line.strip()))

            if matches:
                inventory[rel_path] = matches
                if rel_path.startswith("backend/banking_crosswalk/") or rel_path.startswith("web/"):
                    active_runtime_files.append(rel_path)
                elif "test" in rel_path.lower():
                    test_files.append(rel_path)
                elif rel_path.startswith("scripts/"):
                    script_files.append(rel_path)
                elif rel_path.endswith(".md"):
                    if any(prefix in rel_path for prefix in ["AUDIT", "P0_", "P1_", "DUAL_MODE", "END_TO_END"]):
                        historical_audit_files.append(rel_path)
                    else:
                        documentation_files.append(rel_path)

    print(f"Total files with AIAF: {len(inventory)}")
    print(f"  - Active Runtime: {len(active_runtime_files)}")
    print(f"  - Tests: {len(test_files)}")
    print(f"  - Scripts: {len(script_files)}")
    print(f"  - Documentation: {len(documentation_files)}")
    print(f"  - Historical Audit Records: {len(historical_audit_files)}")

    with open(repo_root / "scripts" / "aiaf_audit_data.json", "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)


if __name__ == "__main__":
    audit_repository()
