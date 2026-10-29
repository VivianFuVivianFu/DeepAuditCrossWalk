"""Storage contract, restart, rollback and real PostgreSQL RLS regressions."""

import os
import uuid

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from banking_crosswalk import api, schema
from banking_crosswalk.database import create_database_engine, upgrade_database
from banking_crosswalk.models import BankingUseCase, MappingDecision, ReviewStatus
from banking_crosswalk.sql_store import SQLTenantStore
from banking_crosswalk.store import ConflictError, NotFoundError, StorageUnavailable


@pytest.fixture(params=["sqlite", "postgresql"])
def repository(request, tmp_path):
    if request.param == "postgresql":
        url = os.getenv("TEST_DATABASE_URL")
        if not url:
            pytest.skip(
                "TEST_DATABASE_URL is absent; real PostgreSQL is exercised in CI"
            )
    else:
        url = f"sqlite:///{tmp_path / 'repository.sqlite3'}"
        engine = create_database_engine(url)
        upgrade_database(engine)
        upgrade_database(engine)  # An already-applied migration must be a no-op.
        engine.dispose()
    repo = SQLTenantStore(url, production=request.param == "postgresql")
    yield repo, url, f"test-{uuid.uuid4()}"
    repo.close()


def create_assessment(repo, tenant, monkeypatch, *, policy=False):
    monkeypatch.setattr(api, "store", repo)
    if policy:
        return api.create_policy_gap_assessment(
            api.PolicyGapAssessmentRequest(
                use_case=BankingUseCase(apra_regulated=True),
                policy_text="All refunds above AUD 500 require human approval before payment execution.",
            ),
            tenant,
        )
    return api.create_coverage_assessment(
        api.CoverageAssessmentRequest(
            use_case=BankingUseCase(apra_regulated=True),
        ),
        tenant,
    )


def test_restart_preserves_use_case_routing_policy_and_assessment(
    repository, monkeypatch
):
    repo, url, tenant = repository
    monkeypatch.setattr(api, "store", repo)
    use_case = api.create_use_case(
        BankingUseCase(name="Synthetic restart test"), tenant
    )
    bank = repo.get_questionnaire(tenant).model_copy(deep=True)
    bank.metadata.questionnaire_id = f"synthetic-{uuid.uuid4()}"
    repo.save_questionnaire(tenant, bank)
    snapshot = api.route_questionnaire(
        api.QuestionnaireRouteRequest(questionnaire_id=bank.metadata.questionnaire_id),
        tenant,
    )
    policy = api.import_policy(
        api.PolicyImportRequest(
            name="Synthetic", text="Human approval must be logged."
        ),
        tenant,
    )
    assessment = api.create_policy_gap_assessment(
        api.PolicyGapAssessmentRequest(
            use_case_id=use_case.use_case_id,
            policy_pack_id=policy.policy_pack_id,
            questionnaire_id=bank.metadata.questionnaire_id,
            routing_snapshot_id=snapshot.snapshot_id,
        ),
        tenant,
    )
    repo.close()
    restored = SQLTenantStore(url)
    try:
        assert (
            restored.get_use_case(tenant, use_case.use_case_id).name
            == "Synthetic restart test"
        )
        assert (
            restored.get_questionnaire(tenant, bank.metadata.questionnaire_id) == bank
        )
        assert restored.get_routing_snapshot(tenant, snapshot.snapshot_id) == snapshot
        assert restored.get_policy(tenant, policy.policy_pack_id) == policy
        assert restored.get_assessment(tenant, assessment.assessment_id) == assessment
        assert len(restored.audit_events(tenant)) == 5
        for method, object_id in (
            (restored.get_use_case, use_case.use_case_id),
            (restored.get_questionnaire, bank.metadata.questionnaire_id),
            (restored.get_routing_snapshot, snapshot.snapshot_id),
            (restored.get_policy, policy.policy_pack_id),
            (restored.get_assessment, assessment.assessment_id),
        ):
            with pytest.raises(NotFoundError):
                method(f"other-{tenant}", object_id)
    finally:
        restored.close()


@pytest.mark.parametrize("policy", [False, True])
def test_reviews_survive_restart_and_stale_review_cannot_overwrite(
    repository, monkeypatch, policy
):
    repo, url, tenant = repository
    assessment = create_assessment(repo, tenant, monkeypatch, policy=policy)
    original = repo.get_gap(tenant, assessment.gaps[0].gap_id)
    first = repo.save_gap(
        tenant, original.model_copy(update={"status": "in_review"}), "first.reviewer"
    )
    assert first.revision == 2
    with pytest.raises(ConflictError):
        repo.save_gap(
            tenant, original.model_copy(update={"status": "closed"}), "stale.reviewer"
        )
    assert len(repo.audit_events(tenant)) == (3 if policy else 2)
    restored = SQLTenantStore(url)
    try:
        assert restored.get_gap(tenant, original.gap_id).status == "in_review"
        assert (
            restored.get_assessment(tenant, assessment.assessment_id).gaps[0].revision
            == 2
        )
        event = restored.audit_events(tenant)[-1]
        assert event["actor"] == "first.reviewer"
        assert event["detail"]["status"] == "in_review"
    finally:
        restored.close()


def test_assessment_gaps_and_audit_roll_back_together(repository, monkeypatch):
    repo, _, tenant = repository
    monkeypatch.setattr(api, "store", repo)
    assessment = api.create_coverage_assessment(
        api.CoverageAssessmentRequest(
            use_case=BankingUseCase(apra_regulated=True),
            persist=False,
        ),
        tenant,
    )
    monkeypatch.setattr(
        repo,
        "_record",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("injected audit failure")
        ),
    )
    with pytest.raises(RuntimeError, match="injected audit failure"):
        repo.save_assessment(tenant, assessment)
    with pytest.raises(NotFoundError):
        repo.get_assessment(tenant, assessment.assessment_id)
    with pytest.raises(NotFoundError):
        repo.get_gap(tenant, assessment.gaps[0].gap_id)
    assert repo.audit_events(tenant) == []


def test_review_and_audit_roll_back_together(repository, monkeypatch):
    repo, _, tenant = repository
    assessment = create_assessment(repo, tenant, monkeypatch)
    gap = repo.get_gap(tenant, assessment.gaps[0].gap_id)

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(repo, "_record", fail)
    with pytest.raises(RuntimeError):
        repo.save_gap(tenant, gap.model_copy(update={"status": "closed"}), "reviewer")
    assert repo.get_gap(tenant, gap.gap_id) == gap


def test_mapping_identity_versions_and_rejection_history_survive_restart(repository):
    repo, url, tenant = repository
    mapping = MappingDecision(
        obligation_id="O1",
        facet="scope",
        question_id="Q1",
        review_status=ReviewStatus.APPROVED,
        questionnaire_id="bank",
        questionnaire_sha256="v1",
        regulatory_pack_id="pack",
        regulatory_pack_version="v1",
        reviewer="Synthetic Reviewer",
        reason="Synthetic control review",
    )
    repo.save_mapping(tenant, mapping, "Synthetic Reviewer")
    repo.save_mapping(
        tenant,
        mapping.model_copy(update={"review_status": ReviewStatus.REJECTED}),
        "Second Reviewer",
    )
    repo.save_mapping(
        tenant,
        mapping.model_copy(update={"questionnaire_sha256": "v2"}),
        "Synthetic Reviewer",
    )
    restored = SQLTenantStore(url)
    try:
        assert (
            restored.mappings(tenant, questionnaire_sha256="v1")[0].review_status
            == ReviewStatus.REJECTED
        )
        assert (
            restored.mappings(tenant, questionnaire_sha256="v2")[0].review_status
            == ReviewStatus.APPROVED
        )
        assert len(restored.audit_events(tenant)) == 3
        assert restored.audit_events(tenant)[0]["detail"]["reason"] == mapping.reason
        assert restored.mappings(f"other-{tenant}") == []
    finally:
        restored.close()


def test_record_cannot_be_saved_under_a_different_tenant(repository, monkeypatch):
    repo, _, tenant = repository
    assessment = create_assessment(repo, tenant, monkeypatch)
    with pytest.raises(ValueError, match="tenant"):
        repo.save_assessment(f"other-{tenant}", assessment)


def test_blank_closure_references_and_stale_client_revision_are_rejected(
    repository, monkeypatch
):
    from fastapi import HTTPException
    from pydantic import ValidationError

    repo, _, tenant = repository
    assessment = create_assessment(repo, tenant, monkeypatch)
    with pytest.raises(ValidationError):
        api.GapReviewRequest(
            action="close",
            comment="Reviewed",
            evidence_artifact_ids=[" "],
            retest_record_id=" ",
        )
    with pytest.raises(HTTPException) as exc:
        api.review_gap(
            assessment.gaps[0].gap_id,
            api.GapReviewRequest(
                action="start_review", comment="Reviewed", expected_revision=99
            ),
            tenant,
            "Synthetic Reviewer",
            "risk",
        )
    assert exc.value.status_code == 409


def test_unmigrated_database_and_sqlite_production_fail_closed(tmp_path):
    url = f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}"
    with pytest.raises(StorageUnavailable):
        SQLTenantStore(url)
    engine = create_database_engine(url)
    upgrade_database(engine)
    engine.dispose()
    with pytest.raises(StorageUnavailable, match="PostgreSQL"):
        SQLTenantStore(url, production=True)


def test_api_lifespan_reconnects_to_persisted_records(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from banking_crosswalk.app import app

    url = f"sqlite:///{tmp_path / 'lifespan.sqlite3'}"
    engine = create_database_engine(url)
    upgrade_database(engine)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    tenant = "lifespan-test"
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        result = client.post(
            "/v1/assessments/coverage",
            headers={"X-Tenant-ID": tenant},
            json={"use_case": {"apra_regulated": True}},
        )
        assert result.status_code == 201
        assessment_id = result.json()["assessment_id"]
    with TestClient(app) as client:
        result = client.get(
            f"/v1/assessments/{assessment_id}/report", headers={"X-Tenant-ID": tenant}
        )
        assert result.status_code == 200
        assert result.json()["assessment"]["assessment_id"] == assessment_id


def test_configured_unavailable_database_never_falls_back_to_memory(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from banking_crosswalk.app import app

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'empty.sqlite3'}")
    with pytest.raises(StorageUnavailable):
        with TestClient(app):
            pass


def test_database_failures_are_sanitised_at_api_boundary(repository, monkeypatch):
    from fastapi.testclient import TestClient
    from banking_crosswalk.app import app

    repo, _, tenant = repository
    monkeypatch.setattr(api, "store", repo)

    def fail(*args, **kwargs):
        raise StorageUnavailable("driver error contains private-host and credential")

    monkeypatch.setattr(repo, "save_use_case", fail)
    response = TestClient(app).post(
        "/v1/use-cases", headers={"X-Tenant-ID": tenant}, json={"name": "Synthetic"}
    )
    assert response.status_code == 503
    assert "private-host" not in response.text
    assert "credential" not in response.text


def test_postgresql_rls_protects_queries_even_without_tenant_predicates(repository):
    repo, _, tenant = repository
    if repo.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only forced RLS test")
    repo.save_use_case(tenant, BankingUseCase(use_case_id=str(uuid.uuid4())))
    # A pooled connection must retain no tenant context after transaction end.
    with repo.engine.begin() as connection:
        assert connection.execute(sa.select(schema.use_cases)).all() == []
    with repo._transaction(f"other-{tenant}") as connection:
        assert connection.execute(sa.select(schema.use_cases)).all() == []
    with repo._transaction(tenant) as connection:
        assert len(connection.execute(sa.select(schema.use_cases)).all()) == 1
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        with repo.engine.begin() as connection:
            connection.execute(
                schema.use_cases.insert().values(
                    tenant_id=tenant, object_id="forged", payload={}
                )
            )


def test_postgresql_audit_cannot_be_modified_or_truncated(repository):
    repo, _, tenant = repository
    if repo.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only audit trigger test")
    repo.save_use_case(tenant, BankingUseCase(use_case_id=str(uuid.uuid4())))
    from sqlalchemy.exc import DBAPIError

    for statement in (
        schema.audit_events.update().values(payload={}),
        schema.audit_events.delete(),
        sa.text("TRUNCATE audit_events"),
    ):
        with pytest.raises(DBAPIError):
            with repo.engine.begin() as connection:
                connection.execute(
                    sa.text("SELECT set_config('crosswalk.tenant_id', :tenant, true)"),
                    {"tenant": tenant},
                )
                connection.execute(statement)
    assert len(repo.audit_events(tenant)) == 1
