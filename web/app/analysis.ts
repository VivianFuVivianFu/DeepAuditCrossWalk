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

export function parseThresholdAud(threshold: string): number | null {
  const amount = threshold.trim() === "" ? null : Number(threshold);
  if (amount !== null && (!Number.isFinite(amount) || amount < 0)) {
    throw new Error(
      "Approval threshold must be a non-negative AUD amount or left unknown.",
    );
  }
  return amount;
}

export function buildPayload(
  name: string,
  facts: Record<FactKey, Fact>,
  threshold: string,
) {
  const amount = parseThresholdAud(threshold);
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

export type AssessmentMode = "regulatory_only" | "enterprise_enhanced";
export type AssessmentTargetType = "questionnaire" | "strategy";

export type DocumentAssessmentPayload = {
  action: "assess_coverage";
  questionnaire_id: string;
  assessment_mode: AssessmentMode;
  assessment_target_type: "questionnaire";
  enterprise_baseline_id?: string;
  enterprise_baseline_version?: string;
  use_case: Record<FactKey, Fact> & {
    name: string;
    approval_threshold_aud: number | null;
  };
};

export function buildDocumentAssessmentPayload(params: {
  questionnaireId: string;
  assessmentMode: AssessmentMode;
  facts: Record<FactKey, Fact>;
  threshold: string;
  organisationName?: string;
  enterpriseBaselineId?: string;
  enterpriseBaselineVersion?: string;
}): DocumentAssessmentPayload {
  const qid = params.questionnaireId.trim();
  if (!qid) {
    throw new Error(
      "Upload or select an enterprise questionnaire (.xlsx) before running an assessment.",
    );
  }
  if (qid === "DEMO_BANKING_V1") {
    throw new Error(
      "DEMO_BANKING_V1 is reserved for the synthetic demo and cannot be used for customer questionnaire assessment.",
    );
  }
  const amount = parseThresholdAud(params.threshold);
  if (params.assessmentMode === "enterprise_enhanced") {
    const bid = (params.enterpriseBaselineId || "").trim();
    if (!bid) {
      throw new Error(
        "Select an eligible approved Enterprise Baseline before running an Enterprise-Enhanced assessment.",
      );
    }
    return {
      action: "assess_coverage" as const,
      questionnaire_id: qid,
      assessment_mode: "enterprise_enhanced" as const,
      assessment_target_type: "questionnaire" as const,
      enterprise_baseline_id: bid,
      ...(params.enterpriseBaselineVersion?.trim()
        ? { enterprise_baseline_version: params.enterpriseBaselineVersion.trim() }
        : {}),
      use_case: {
        name:
          (params.organisationName || "").trim() ||
          "Organisation Governance Context",
        ...params.facts,
        approval_threshold_aud: amount,
      },
    };
  }

  return {
    action: "assess_coverage" as const,
    questionnaire_id: qid,
    assessment_mode: "regulatory_only" as const,
    assessment_target_type: "questionnaire" as const,
    use_case: {
      name:
        (params.organisationName || "").trim() ||
        "Organisation Governance Context",
      ...params.facts,
      approval_threshold_aud: amount,
    },
  };
}

export interface QuestionRecordItem {
  question_id: string;
  question_text: string;
  risk_domain?: string | null;
  answer_options?: string[];
  source_version: string;
  source_sheet: string;
  question_type: string;
  source_location?: string | null;
  provenance?: Record<string, unknown>;
}

export interface QuestionBankResponse {
  metadata: {
    questionnaire_id: string;
    source_filename: string;
    source_sha256: string;
    source_version: string;
    header_fingerprint: string;
    sheets: Record<string, string>;
    core_question_count: number;
    warnings: string[];
  };
  questions: QuestionRecordItem[];
  routing_metadata?: Record<string, unknown>;
}

export interface ClauseControlMappingItem {
  mapping_id: string;
  clause_id: string;
  control_id: string;
  relationship: string;
  mapped_facets?: string[];
  confidence: number;
  rationale: string;
  review_status: "proposed" | "approved" | "confirmed" | "rejected";
  reviewer_actor?: string | null;
  reviewer_role?: string | null;
  review_comment?: string | null;
  reviewed_at?: string | null;
}

export interface EnterpriseClauseItem {
  clause_id: string;
  policy_id: string;
  tenant_id: string;
  source_name: string;
  clause_number?: string | null;
  text: string;
  mandatory?: boolean;
  required_approval_role?: string | null;
  thresholds_aud?: number[];
  threshold_currency?: string | null;
  threshold_operator?: string | null;
  approval_timing?: string | null;
  control_facets: string[];
  control_mappings: ClauseControlMappingItem[];
  is_unmapped: boolean;
  review_status:
    | "unreviewed"
    | "proposed"
    | "approved"
    | "confirmed"
    | "rejected";
  reviewer_actor?: string | null;
  reviewer_role?: string | null;
  review_comment?: string | null;
  reviewed_at?: string | null;
}

export interface EnterprisePolicyItem {
  policy_id: string;
  tenant_id: string;
  name: string;
  version: string;
  category: string;
  authority_level: string;
  file_sha256?: string;
  clauses: EnterpriseClauseItem[];
  created_at: string;
}

export interface EnterpriseBaselineItem {
  baseline_id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  version: string;
  revision: number;
  status: string;
  policy_ids: string[];
  confirmed_control_ids: string[];
  approved_clause_ids?: string[];
  clause_snapshots?: EnterpriseClauseItem[];
  baseline_sha256?: string | null;
  created_at: string;
}

export type PolicyLifecycleState =
  | "Draft"
  | "Pending Review"
  | "Approved (Eligible)"
  | "Rejected";

export function derivePolicyLifecycleStatus(
  policy: EnterprisePolicyItem,
  clausesOverride?: EnterpriseClauseItem[],
): PolicyLifecycleState {
  const clauses = clausesOverride ?? policy.clauses ?? [];
  if (clauses.length === 0) return "Draft";
  const hasApprovedClause = clauses.some(
    (c) => c.review_status === "approved" || c.review_status === "confirmed",
  );
  if (hasApprovedClause) return "Approved (Eligible)";
  const allRejected = clauses.every((c) => c.review_status === "rejected");
  if (allRejected) return "Rejected";
  return "Pending Review";
}

export function isBaselineEligible(baseline: EnterpriseBaselineItem): boolean {
  if (baseline.status !== "active") return false;
  if (
    Array.isArray(baseline.approved_clause_ids) &&
    baseline.approved_clause_ids.length > 0
  ) {
    return true;
  }
  return (baseline.clause_snapshots ?? []).some(
    (c) => c.review_status === "approved" || c.review_status === "confirmed",
  );
}

export interface Gap {
  gap_id: string;
  title: string;
  gap_type: string;
  severity: string;
  status?: string;
  coverage_status?: string;
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
export interface EnterpriseClauseCoverageItem {
  clause_id: string;
  policy_id: string;
  source_name: string;
  applicability_status: string;
  clause_approval_status: string;
  control_mapping_approval_status: string;
  questionnaire_to_facet_approval_status: string;
  coverage_status: string;
  implementation_evidence_status: string;
  operational_effectiveness_status: string;
  required_facets: string[];
  covered_facets: string[];
  missing_facets: string[];
  needs_review_facets?: string[];
  confirmed_question_ids: string[];
  candidate_question_ids: string[];
  rationale?: string | null;
}
export interface Assessment {
  assessment_id: string;
  created_at: string;
  regulatory_pack_version: string;
  questionnaire_id?: string;
  questionnaire_sha256: string;
  assessment_mode?: string;
  assessment_target_type?: string;
  results?: Obligation[];
  enterprise_clause_coverage?: EnterpriseClauseCoverageItem[];
  gaps?: Gap[];
  policy_gaps?: Gap[];
  questionnaire_gaps?: Gap[];
  control_conflicts?: Gap[];
  implementation_evidence_gaps?: Gap[];
  enterprise_gaps?: Gap[];
  enterprise_baseline_id?: string;
  enterprise_baseline_version?: string;
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
      ...(result.enterprise_gaps ?? []),
    ]
  );
}
