"""CI-only restore drill with synthetic data and a separately connected runtime role."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from banking_crosswalk import api
from banking_crosswalk.models import BankingUseCase
from banking_crosswalk.sql_store import SQLTenantStore
from banking_crosswalk.store import NotFoundError
from sqlalchemy.engine import make_url


def fingerprint(repo, tenant, assessment_id):
    report = {
        "assessment": repo.get_assessment(tenant, assessment_id).model_dump(
            mode="json"
        ),
        "events": repo.audit_events(tenant),
        "mappings": [value.model_dump(mode="json") for value in repo.mappings(tenant)],
    }
    return hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    if os.getenv("CI") != "true":
        raise SystemExit(
            "Restore verification is restricted to disposable CI databases"
        )
    anchor = Path("local-data/restore-anchor.json")
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if not args.seed:
        url = url.set(database="crosswalk_restore")
    repo = SQLTenantStore(url.render_as_string(hide_password=False), production=True)
    try:
        tenant = "synthetic-restore-drill"
        if args.seed:
            api.store = repo
            assessment = api.create_coverage_assessment(
                api.CoverageAssessmentRequest(
                    use_case=BankingUseCase(
                        name="Synthetic restore fixture", apra_regulated=True
                    ),
                ),
                tenant,
            )
            question = repo.get_questionnaire(tenant).questions[0]
            obligation = api.regulatory_pack.obligations[0]
            api.review_mapping(
                api.MappingReviewRequest(
                    obligation_id=obligation.obligation_id,
                    facet=obligation.coverage_facets[0],
                    question_id=question.question_id,
                    review_status="approved",
                    reason="Synthetic backup fixture review",
                ),
                tenant,
                "Synthetic Reviewer",
                "risk",
            )
            api.review_gap(
                assessment.gaps[0].gap_id,
                api.GapReviewRequest(
                    action="close",
                    comment="Synthetic backup fixture closure",
                    validated=True,
                    scope_rechecked=True,
                    approved=True,
                    evidence_artifact_ids=["synthetic-evidence"],
                    retest_record_id="synthetic-retest",
                    expected_revision=1,
                ),
                tenant,
                "Synthetic Reviewer",
                "risk",
            )
            data = {
                "assessment_id": assessment.assessment_id,
                "sha256": fingerprint(repo, tenant, assessment.assessment_id),
            }
            anchor.parent.mkdir(exist_ok=True)
            anchor.write_text(json.dumps(data), encoding="utf-8")
            print(
                "Synthetic review and evidence-gated closure seeded for restore drill."
            )
        else:
            data = json.loads(anchor.read_text(encoding="utf-8"))
            assert fingerprint(repo, tenant, data["assessment_id"]) == data["sha256"], (
                "Restored records differ"
            )
            assessment = repo.get_assessment(tenant, data["assessment_id"])
            assert assessment.gaps[0].status == "closed"
            assert assessment.gaps[0].closure_retest_record_id == "synthetic-retest"
            try:
                repo.get_assessment("different-tenant", data["assessment_id"])
            except NotFoundError:
                pass
            else:
                raise AssertionError("Restored tenant isolation failed")
            print(
                "Backup restore verified: assessment, closure evidence, mapping decisions, audit history and tenant isolation."
            )
    finally:
        repo.close()


if __name__ == "__main__":
    main()
