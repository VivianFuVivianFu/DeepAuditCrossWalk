"""Exercise the live independent web → API assessment pipeline with synthetic data."""
import json
import os
import urllib.request


def main():
    web = os.getenv("SMOKE_WEB_URL", "http://127.0.0.1:3000")
    api = os.getenv("SMOKE_API_URL", "http://127.0.0.1:8000")
    with urllib.request.urlopen(f"{api}/health", timeout=10) as response:
        assert json.load(response)["status"] == "ok"
    with urllib.request.urlopen(web, timeout=10) as response:
        assert b"DeepAudit" in response.read()
    for kind in ("coverage", "policy-gaps"):
        data = {"kind": kind, "use_case": {"name": "Synthetic smoke test", "apra_regulated": True, "handles_personal_information": True, "approval_threshold_aud": 500}}
        if kind == "policy-gaps":
            data["policy_text"] = "Refunds above AUD 500 require human approval before payment execution."
        request = urllib.request.Request(f"{web}/api/analysis", data=json.dumps(data).encode(), headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        assert result["assessment_id"]
        assert result["questionnaire_sha256"]
        if kind == "coverage":
            assert result["metrics"]["confirmed_coverage_rate"] == 0
            assert result["metrics"]["applicability_undetermined"] > 0
        else:
            assert result["questionnaire_gaps"]
        print(f"PASS {kind}: live web-to-API result with version traceability")


if __name__ == "__main__":
    main()
