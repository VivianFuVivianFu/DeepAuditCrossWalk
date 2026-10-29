"""Synthetic HTTP restart check for the optional persistent container stack."""

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(path, payload=None, *, tenant=None):
    headers = {
        "X-Tenant-ID": tenant
        or os.getenv("BANKING_CROSSWALK_TENANT_ID", "public-demo"),
        "X-API-Key": os.getenv("CROSSWALK_API_KEY", ""),
        "X-Actor": os.getenv("BANKING_CROSSWALK_ACTOR", ""),
        "X-Role": os.getenv("BANKING_CROSSWALK_ROLE", ""),
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode() if payload is not None else None
    base = os.getenv("SMOKE_API_URL", "http://127.0.0.1:8000")
    with urllib.request.urlopen(
        urllib.request.Request(base + path, data=data, headers=headers), timeout=10
    ) as response:
        return json.load(response)


def fingerprint(report):
    # Report generation time changes between reads; persisted records do not.
    content = {
        "assessment": report["assessment"],
        "audit_events": report["audit_events"],
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["create", "verify"])
    args = parser.parse_args()
    anchor = Path("local-data/persistence-smoke.json")
    for attempt in range(30):
        try:
            assert request("/ready")["stateful_storage"] == "postgresql"
            break
        except (OSError, AssertionError):
            if attempt == 29:
                raise RuntimeError("Persistent API failed readiness") from None
            time.sleep(0.5)
    if args.phase == "create":
        assessment = request(
            "/v1/assessments/coverage",
            {
                "use_case": {
                    "name": "Synthetic container restart",
                    "apra_regulated": True,
                }
            },
        )
        gap = assessment["gaps"][0]
        reviewed = request(
            f"/v1/gaps/{gap['gap_id']}/review",
            {
                "action": "close",
                "comment": "Synthetic restart test with evidence references",
                "validated": True,
                "scope_rechecked": True,
                "approved": True,
                "evidence_artifact_ids": ["synthetic-container-evidence"],
                "retest_record_id": "synthetic-container-retest",
                "expected_revision": gap["revision"],
            },
        )
        assert reviewed["status"] == "closed"
        report = request(f"/v1/assessments/{assessment['assessment_id']}/report")
        anchor.parent.mkdir(exist_ok=True)
        anchor.write_text(
            json.dumps(
                {"id": assessment["assessment_id"], "sha256": fingerprint(report)}
            ),
            encoding="utf-8",
        )
        print("Persistent API created an assessment and evidence-gated review.")
    else:
        data = json.loads(anchor.read_text(encoding="utf-8"))
        report = request(f"/v1/assessments/{data['id']}/report")
        assert fingerprint(report) == data["sha256"], (
            "Records changed or disappeared after container restart"
        )
        assert report["assessment"]["gaps"][0]["status"] == "closed"
        try:
            request(f"/v1/assessments/{data['id']}/report", tenant="different-bank")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Production tenant binding failed")
        print(
            "Container restart verified: report, closure, audit history and production tenant binding."
        )


if __name__ == "__main__":
    main()
