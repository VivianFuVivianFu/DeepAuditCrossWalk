import { describe, it, expect } from "vitest";
import {
  buildDocumentAssessmentPayload,
  buildPayload,
  derivePolicyLifecycleStatus,
  emptyFacts,
  gapsFor,
  isBaselineEligible,
  parseFact,
} from "../app/analysis";

describe("public assessment contract", () => {
  it("preserves unknown applicability instead of silently denying duties", () => {
    const payload = buildPayload("Refund agent", emptyFacts, "");
    expect(payload.use_case.idr_obligations).toBeNull();
    expect(payload.use_case.material_service_provider).toBeNull();
    expect(payload.use_case.approval_threshold_aud).toBeNull();
    expect(payload.persist).toBe(false);
    expect(payload.questionnaire_pack).toBe("DEMO_BANKING_V1");
  });
  it("distinguishes a confirmed no from missing input", () => {
    expect(parseFact("false")).toBe(false);
    expect(parseFact("unknown")).toBeNull();
    expect(parseFact("true")).toBe(true);
  });
  it("rejects non-finite and negative monetary boundaries", () => {
    for (const threshold of ["NaN", "Infinity", "-1"])
      expect(() => buildPayload("", emptyFacts, threshold)).toThrow();
    expect(
      buildPayload("", emptyFacts, "0").use_case.approval_threshold_aud,
    ).toBe(0);
  });
  it("does not duplicate gaps from a policy response exposing the computed gaps field", () => {
    expect(
      gapsFor({
        assessment_id: "a",
        created_at: "",
        regulatory_pack_version: "",
        questionnaire_sha256: "",
        gaps: [],
        policy_gaps: [],
      }),
    ).toEqual([]);
  });
});

describe("document-first two-upload assessment contract (PR 2)", () => {
  it("requires an uploaded questionnaire_id and blocks DEMO_BANKING_V1 in customer assessments", () => {
    expect(() =>
      buildDocumentAssessmentPayload({
        questionnaireId: "",
        assessmentMode: "regulatory_only",
        facts: emptyFacts,
        threshold: "",
      }),
    ).toThrow(/questionnaire/i);

    expect(() =>
      buildDocumentAssessmentPayload({
        questionnaireId: "DEMO_BANKING_V1",
        assessmentMode: "regulatory_only",
        facts: emptyFacts,
        threshold: "",
      }),
    ).toThrow(/DEMO_BANKING_V1/);
  });

  it("builds a regulatory_only questionnaire payload without enterprise_baseline_id and preserves unknown applicability", () => {
    const payload = buildDocumentAssessmentPayload({
      questionnaireId: "QBANK-123456789ABC",
      assessmentMode: "regulatory_only",
      facts: emptyFacts,
      threshold: "",
      organisationName: "Bank A",
      enterpriseBaselineId: "should-be-ignored-in-regulatory-only",
    });
    expect(payload).toEqual({
      action: "assess_coverage",
      questionnaire_id: "QBANK-123456789ABC",
      assessment_mode: "regulatory_only",
      assessment_target_type: "questionnaire",
      use_case: {
        name: "Bank A",
        ...emptyFacts,
        approval_threshold_aud: null,
      },
    });
    expect("enterprise_baseline_id" in payload).toBe(false);
    expect("questionnaire_pack" in payload).toBe(false);
  });

  it("requires an explicit enterprise_baseline_id when assessmentMode is enterprise_enhanced", () => {
    expect(() =>
      buildDocumentAssessmentPayload({
        questionnaireId: "QBANK-123456789ABC",
        assessmentMode: "enterprise_enhanced",
        facts: emptyFacts,
        threshold: "50000",
        enterpriseBaselineId: "",
      }),
    ).toThrow(/Enterprise Baseline/i);

    const payload = buildDocumentAssessmentPayload({
      questionnaireId: "QBANK-123456789ABC",
      assessmentMode: "enterprise_enhanced",
      facts: { ...emptyFacts, apra_regulated: true },
      threshold: "50000",
      enterpriseBaselineId: "BASE-001",
      enterpriseBaselineVersion: "1.2.0",
    });
    expect(payload.assessment_mode).toBe("enterprise_enhanced");
    expect(payload.enterprise_baseline_id).toBe("BASE-001");
    expect(payload.enterprise_baseline_version).toBe("1.2.0");
    expect(payload.use_case.approval_threshold_aud).toBe(50000);
    expect(payload.use_case.apra_regulated).toBe(true);
  });

  it("computes policy lifecycle status and baseline eligibility accurately", () => {
    const basePolicy = {
      policy_id: "POL-1",
      tenant_id: "t1",
      name: "AI Policy",
      version: "1.0.0",
      category: "ai_governance",
      authority_level: "enterprise_policy",
      file_sha256: "abc",
      created_at: "",
      clauses: [],
    };
    expect(derivePolicyLifecycleStatus(basePolicy)).toBe("Draft");

    const proposedClause = {
      clause_id: "C1",
      policy_id: "POL-1",
      tenant_id: "t1",
      source_name: "AI Policy",
      clause_number: "1.1",
      text: "Rule",
      control_facets: ["human_approval_required"],
      control_mappings: [],
      is_unmapped: false,
      review_status: "proposed" as const,
    };
    expect(
      derivePolicyLifecycleStatus({ ...basePolicy, clauses: [proposedClause] }),
    ).toBe("Pending Review");

    expect(
      derivePolicyLifecycleStatus({
        ...basePolicy,
        clauses: [{ ...proposedClause, review_status: "approved" }],
      }),
    ).toBe("Approved (Eligible)");

    expect(
      derivePolicyLifecycleStatus({
        ...basePolicy,
        clauses: [{ ...proposedClause, review_status: "rejected" }],
      }),
    ).toBe("Rejected");

    expect(
      isBaselineEligible({
        baseline_id: "B1",
        tenant_id: "t1",
        name: "Base",
        version: "1.0.0",
        revision: 1,
        status: "active",
        policy_ids: ["POL-1"],
        confirmed_control_ids: [],
        approved_clause_ids: ["C1"],
        baseline_sha256: "fp",
        created_at: "",
      }),
    ).toBe(true);

    expect(
      isBaselineEligible({
        baseline_id: "B2",
        tenant_id: "t1",
        name: "Base",
        version: "1.0.0",
        revision: 1,
        status: "active",
        policy_ids: ["POL-1"],
        confirmed_control_ids: [],
        approved_clause_ids: [],
        clause_snapshots: [proposedClause],
        baseline_sha256: "fp",
        created_at: "",
      }),
    ).toBe(false);
  });
});
