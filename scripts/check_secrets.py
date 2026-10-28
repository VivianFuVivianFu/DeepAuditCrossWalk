#!/usr/bin/env python3
"""Fail when a likely credential is present in the publishable working tree.

The scanner deliberately reports only the detector name and location. It never
prints the matching value, which keeps CI logs from becoming another leak.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 10 * 1024 * 1024
DETECTORS = {
    "Anthropic API key": re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}"),
    # A bare ``sk-`` is intentionally not enough: URLs containing words such
    # as ``risk-management`` otherwise become false positives. Cover the
    # documented modern prefixes and the fixed-length legacy token format.
    "OpenAI API key": re.compile(
        rb"(?:sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{48})"
    ),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
PLACEHOLDER_MARKERS = (b"example", b"placeholder", b"replace", b"test", b"your-key")


def publishable_files() -> list[Path]:
    """Return tracked and non-ignored untracked files, without following links."""

    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def scan_file(path: Path) -> list[tuple[str, int]]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return []
        data = path.read_bytes()
    except OSError as exc:
        print(f"secret-scan: could not read {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
        return [("unreadable file", 0)]

    # Null bytes are a reliable enough signal for binary assets. Source and
    # structured data remain scanned byte-for-byte without decoding surprises.
    if b"\0" in data[:8192]:
        return []

    findings: list[tuple[str, int]] = []
    for detector, pattern in DETECTORS.items():
        for match in pattern.finditer(data):
            if any(marker in match.group(0).lower() for marker in PLACEHOLDER_MARKERS):
                continue
            line = data.count(b"\n", 0, match.start()) + 1
            findings.append((detector, line))
    return findings


def main() -> int:
    findings: list[tuple[Path, str, int]] = []
    for path in publishable_files():
        for detector, line in scan_file(path):
            findings.append((path.relative_to(ROOT), detector, line))

    if findings:
        print("Potential credentials detected; values are intentionally redacted:", file=sys.stderr)
        for path, detector, line in findings:
            suffix = f":{line}" if line else ""
            print(f"  {path}{suffix} [{detector}]", file=sys.stderr)
        return 1

    print("Secret scan passed: no recognised credential patterns in publishable files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
