export type Fact = boolean | null;
export const factLabels = {
  apra_regulated: "APRA-regulated entity",
  handles_personal_information: "Processes personal information",
  makes_or_assists_significant_decisions:
    "Makes or assists significant decisions",
  handles_regulated_complaints: "Handles regulated complaints",
  idr_obligations: "Entity-specific IDR duty confirmed",
  third_party_ai_service: "Uses third-party AI services",
  material_service_provider: "CPS 230 service materiality confirmed",
  supports_critical_operation: "Supports a critical operation",
  eu_establishment_or_market: "EU establishment or market nexus",
  eu_output_used: "AI outputs used in the EU",
  eu_deployer_or_provider_role: "Relevant EU provider/deployer role",
  nist_ai_rmf_adopted: "Organisation has adopted NIST AI RMF",
  iso_42001_adopted: "Organisation has adopted ISO 42001",
} as const;
export type FactKey = keyof typeof factLabels;
export const emptyFacts = Object.fromEntries(
  Object.keys(factLabels).map((key) => [key, null]),
) as Record<FactKey, Fact>;

export function parseFact(value: string): Fact {
  return value === "true" ? true : value === "false" ? false : null;
}

export function buildPayload(
  name: string,
  facts: Record<FactKey, Fact>,
  threshold: string,
) {
  const amount = threshold.trim() === "" ? null : Number(threshold);
  if (amount !== null && (!Number.isFinite(amount) || amount < 0)) {
    throw new Error(
      "Approval threshold must be a non-negative AUD amount or left unknown.",
    );
  }
  return {
    use_case: {
      name: name.trim() || "Untitled AI use case",
      ...facts,
      approval_threshold_aud: amount,
    },
    questionnaire_pack: "DEMO_BANKING_V1",
    persist: false,
  };
}

export interface Gap {
  gap_id: string;
  title: string;
  gap_type: string;
  severity: string;
  missing_facets: string[];
  recommendation: string;
  evidence_required: string[];
}
export interface Obligation {
  obligation_id: string;
  title: string;
  instrument: string;
  provision: string;
  authority: string;
  source_url: string;
  applicability: { status: string; reason: string };
  confirmed_status: string;
  provisional_status: string;
  candidate_question_ids: string[];
  confirmed_question_ids: string[];
  confirmed_missing_facets: string[];
  suggested_questions: string[];
  evidence_requirements: string[];
}
export interface Assessment {
  assessment_id: string;
  created_at: string;
  regulatory_pack_version: string;
  questionnaire_sha256: string;
  results?: Obligation[];
  gaps?: Gap[];
  policy_gaps?: Gap[];
  questionnaire_gaps?: Gap[];
  control_conflicts?: Gap[];
  implementation_evidence_gaps?: Gap[];
  metrics?: Record<string, number>;
  warnings?: string[];
  selection_warning?: string;
}
export function gapsFor(result: Assessment): Gap[] {
  return (
    result.gaps ?? [
      ...(result.policy_gaps ?? []),
      ...(result.questionnaire_gaps ?? []),
      ...(result.control_conflicts ?? []),
      ...(result.implementation_evidence_gaps ?? []),
    ]
  );
}
