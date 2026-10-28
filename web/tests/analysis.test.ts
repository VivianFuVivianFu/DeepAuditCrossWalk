import { describe, it, expect } from "vitest";
import { buildPayload, emptyFacts, gapsFor, parseFact } from "../app/analysis";

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
