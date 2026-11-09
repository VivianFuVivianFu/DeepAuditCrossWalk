"use client";

import { ChangeEvent, useEffect, useState } from "react";
import {
  Assessment,
  AssessmentMode,
  AssessmentTargetType,
  EnterpriseBaselineItem,
  EnterpriseClauseItem,
  EnterprisePolicyItem,
  Fact,
  FactKey,
  QuestionBankResponse,
  buildDocumentAssessmentPayload,
  buildPayload,
  derivePolicyLifecycleStatus,
  emptyFacts,
  factLabels,
  gapsFor,
  isBaselineEligible,
  parseFact,
} from "./analysis";

type PrimaryWorkspaceTab =
  | "assess_document"
  | "enterprise_policies"
  | "synthetic_demo";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const commaIdx = result.indexOf(",");
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.onerror = () => reject(new Error("Failed to read selected file."));
    reader.readAsDataURL(file);
  });
}

export default function Home() {
  const [activeTab, setActiveTab] =
    useState<PrimaryWorkspaceTab>("assess_document");

  // Shared Organisation Profile & Applicability Context (used across Document Assessment & Demo)
  const [orgName, setOrgName] = useState("Organisation Governance Context");
  const [facts, setFacts] = useState<Record<FactKey, Fact>>({ ...emptyFacts });
  const [threshold, setThreshold] = useState("");

  // Upload B — Assess a Governance Document state
  const [targetType, setTargetType] =
    useState<AssessmentTargetType>("questionnaire");
  const [questionnaires, setQuestionnaires] = useState<QuestionBankResponse[]>(
    [],
  );
  const [selectedQuestionnaireId, setSelectedQuestionnaireId] = useState("");
  const [assessmentMode, setAssessmentMode] =
    useState<AssessmentMode>("regulatory_only");
  const [selectedBaselineId, setSelectedBaselineId] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);

  // Upload A — Add Enterprise Policies (Optional) state
  const [policyInputMode, setPolicyInputMode] = useState<"file" | "text">(
    "file",
  );
  const [policyName, setPolicyName] = useState(
    "Delegated Financial Authority & AI Governance Policy",
  );
  const [policyVersion, setPolicyVersion] = useState("1.0.0");
  const [policyCategory, setPolicyCategory] = useState("ai_governance");
  const [policyAuthority, setPolicyAuthority] = useState("enterprise_policy");
  const [policyTextDraft, setPolicyTextDraft] = useState(
    "All AI-assisted refunds and credit adjustments >= $50,000 AUD require Senior Manager human approval before payment execution. Immutable audit logs must be retained for 7 years.",
  );
  const [policies, setPolicies] = useState<EnterprisePolicyItem[]>([]);
  const [selectedPolicyId, setSelectedPolicyId] = useState("");
  const [policyClauses, setPolicyClauses] = useState<
    Record<string, EnterpriseClauseItem[]>
  >({});
  const [baselineName, setBaselineName] = useState(
    "Enterprise AI Governance Baseline",
  );
  const [baselineVersion, setBaselineVersion] = useState("1.0.0");
  const [selectedPolicyIdsForBaseline, setSelectedPolicyIdsForBaseline] =
    useState<string[]>([]);
  const [baselines, setBaselines] = useState<EnterpriseBaselineItem[]>([]);

  // Synthetic Demo state (explicitly isolated secondary tab)
  const [demoKind, setDemoKind] = useState<"coverage" | "policy-gaps">(
    "coverage",
  );
  const [demoPolicyExcerpt, setDemoPolicyExcerpt] = useState(
    "All refunds above AUD 500 require human approval before payment execution. Approval logs must be retained.",
  );

  // Assessment Findings & status state
  const [result, setResult] = useState<Assessment | null>(null);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function callWorkspace(payload: Record<string, unknown>) {
    const response = await fetch("/api/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Workspace request failed.");
    }
    return data;
  }

  async function refreshWorkspaceInventory() {
    try {
      const [qList, pList, bList] = await Promise.all([
        callWorkspace({ action: "list_questionnaires" }),
        callWorkspace({ action: "list_policies" }),
        callWorkspace({ action: "list_baselines" }),
      ]);
      if (Array.isArray(qList)) {
        setQuestionnaires(qList);
        if (!selectedQuestionnaireId && qList.length > 0) {
          setSelectedQuestionnaireId(qList[0].metadata.questionnaire_id);
        }
      }
      if (Array.isArray(pList)) {
        setPolicies(pList);
        const clauseMap: Record<string, EnterpriseClauseItem[]> = {};
        for (const pol of pList as EnterprisePolicyItem[]) {
          clauseMap[pol.policy_id] = pol.clauses ?? [];
        }
        setPolicyClauses((prev) => ({ ...clauseMap, ...prev }));
        if (!selectedPolicyId && pList.length > 0) {
          setSelectedPolicyId(pList[0].policy_id);
        }
      }
      if (Array.isArray(bList)) {
        setBaselines(bList);
      }
    } catch {
      // Initial inventory load is best-effort when backend is starting up
    }
  }

  useEffect(() => {
    void refreshWorkspaceInventory();
  }, []);

  function updateFact(key: FactKey, value: Fact) {
    setFacts((current) => ({ ...current, [key]: value }));
    setResult(null);
  }

  function loadExampleProfile() {
    setFacts({
      ...emptyFacts,
      apra_regulated: true,
      handles_personal_information: true,
      handles_regulated_complaints: true,
      makes_or_assists_significant_decisions: true,
      third_party_ai_service: true,
      nist_ai_rmf_adopted: true,
    });
    setOrgName("Example Australian Bank Governance Profile");
    setThreshold("500");
    setResult(null);
  }

  async function handleQuestionnaireFileUpload(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setStatusMessage("");
    setResult(null);
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setError("Please select an enterprise questionnaire in .xlsx format.");
      return;
    }
    setUploadBusy(true);
    try {
      const workbookBase64 = await fileToBase64(file);
      const imported = (await callWorkspace({
        action: "import_questionnaire",
        filename: file.name,
        workbook_base64: workbookBase64,
      })) as QuestionBankResponse;
      setQuestionnaires((prev) => {
        const filtered = prev.filter(
          (item) =>
            item.metadata.questionnaire_id !==
            imported.metadata.questionnaire_id,
        );
        return [imported, ...filtered];
      });
      setSelectedQuestionnaireId(imported.metadata.questionnaire_id);
      setStatusMessage(
        `Imported questionnaire "${imported.metadata.source_filename}" (${imported.questions.length} questions extracted).`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Questionnaire import failed.",
      );
    } finally {
      setUploadBusy(false);
      event.target.value = "";
    }
  }

  async function runDocumentAssessment() {
    setBusy(true);
    setError("");
    setStatusMessage("");
    setResult(null);
    try {
      const selectedBaseline = baselines.find(
        (b) => b.baseline_id === selectedBaselineId,
      );
      const payload = buildDocumentAssessmentPayload({
        questionnaireId: selectedQuestionnaireId,
        assessmentMode,
        facts,
        threshold,
        organisationName: orgName,
        enterpriseBaselineId:
          assessmentMode === "enterprise_enhanced"
            ? selectedBaselineId
            : undefined,
        enterpriseBaselineVersion:
          assessmentMode === "enterprise_enhanced"
            ? selectedBaseline?.version
            : undefined,
      });
      const data = (await callWorkspace(payload)) as Assessment;
      setResult(data);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Document coverage assessment failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handlePolicyFileUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setStatusMessage("");
    setUploadBusy(true);
    try {
      const fileBase64 = await fileToBase64(file);
      const created = (await callWorkspace({
        action: "import_policy_file",
        name: policyName.trim() || file.name,
        filename: file.name,
        file_base64: fileBase64,
        version: policyVersion,
        category: policyCategory,
        authority_level: policyAuthority,
      })) as EnterprisePolicyItem;
      setPolicies((prev) => [
        created,
        ...prev.filter((p) => p.policy_id !== created.policy_id),
      ]);
      setPolicyClauses((prev) => ({
        ...prev,
        [created.policy_id]: created.clauses ?? [],
      }));
      setSelectedPolicyId(created.policy_id);
      setStatusMessage(
        `Imported policy "${created.name}" (${created.clauses.length} candidate clauses extracted for review).`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Policy file import failed.",
      );
    } finally {
      setUploadBusy(false);
      event.target.value = "";
    }
  }

  async function handlePolicyTextImport() {
    setError("");
    setStatusMessage("");
    setUploadBusy(true);
    try {
      const created = (await callWorkspace({
        action: "import_policy_text",
        name: policyName,
        text: policyTextDraft,
        version: policyVersion,
        category: policyCategory,
        authority_level: policyAuthority,
      })) as EnterprisePolicyItem;
      setPolicies((prev) => [
        created,
        ...prev.filter((p) => p.policy_id !== created.policy_id),
      ]);
      setPolicyClauses((prev) => ({
        ...prev,
        [created.policy_id]: created.clauses ?? [],
      }));
      setSelectedPolicyId(created.policy_id);
      setStatusMessage(
        `Extracted ${created.clauses.length} candidate clauses from "${created.name}". Review clauses and control mappings below.`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Policy text import failed.",
      );
    } finally {
      setUploadBusy(false);
    }
  }

  async function handleClauseReview(
    policyId: string,
    clauseId: string,
    status: "approved" | "rejected",
  ) {
    setError("");
    setStatusMessage("");
    setBusy(true);
    try {
      const updated = (await callWorkspace({
        action: "review_clause",
        clause_id: clauseId,
        status,
        review_comment: `Clause ${status} via Enterprise Policy Reviewer`,
      })) as EnterpriseClauseItem;
      setPolicyClauses((prev) => ({
        ...prev,
        [policyId]: (prev[policyId] ?? []).map((c) =>
          c.clause_id === clauseId ? updated : c,
        ),
      }));
      if (
        status === "approved" &&
        !selectedPolicyIdsForBaseline.includes(policyId)
      ) {
        setSelectedPolicyIdsForBaseline((prev) => [...prev, policyId]);
      }
      setStatusMessage(
        `Clause ${clauseId} marked ${status}. Control mappings remain separately review-gated.`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Clause review failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleMappingReview(
    policyId: string,
    clauseId: string,
    mappingId: string,
    status: "approved" | "rejected",
  ) {
    setError("");
    setStatusMessage("");
    setBusy(true);
    try {
      await callWorkspace({
        action: "review_clause_mapping",
        clause_id: clauseId,
        mapping_id: mappingId,
        status,
        review_comment: `Control mapping ${status} via Enterprise Policy Reviewer`,
      });
      const refreshedClauses = (await callWorkspace({
        action: "get_policy_clauses",
        policy_id: policyId,
      })) as EnterpriseClauseItem[];
      setPolicyClauses((prev) => ({
        ...prev,
        [policyId]: refreshedClauses,
      }));
      setStatusMessage(`Control mapping ${mappingId} marked ${status}.`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Control mapping review failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleCompileBaseline() {
    setError("");
    setStatusMessage("");
    setBusy(true);
    try {
      const compiled = (await callWorkspace({
        action: "create_baseline",
        name: baselineName,
        version: baselineVersion,
        policy_ids: selectedPolicyIdsForBaseline,
      })) as EnterpriseBaselineItem;
      setBaselines((prev) => [
        compiled,
        ...prev.filter((b) => b.baseline_id !== compiled.baseline_id),
      ]);
      setSelectedBaselineId(compiled.baseline_id);
      setStatusMessage(
        `Compiled Enterprise Baseline "${compiled.name}" v${compiled.version} (rev ${compiled.revision}) with ${compiled.confirmed_control_ids.length} confirmed control mappings.`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Baseline compilation failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function runSyntheticDemoAnalysis() {
    setBusy(true);
    setError("");
    setStatusMessage("");
    setResult(null);
    try {
      const payload = buildPayload(orgName, facts, threshold);
      const response = await fetch("/api/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payload,
          kind: demoKind,
          ...(demoKind === "policy-gaps"
            ? { policy_text: demoPolicyExcerpt }
            : {}),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Analysis failed");
      setResult(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  }

  function download() {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `crosswalk-${result.assessment_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const activeQuestionnaire = questionnaires.find(
    (q) => q.metadata.questionnaire_id === selectedQuestionnaireId,
  );
  const activePolicy = policies.find((p) => p.policy_id === selectedPolicyId);
  const activePolicyClauseList = selectedPolicyId
    ? (policyClauses[selectedPolicyId] ?? activePolicy?.clauses ?? [])
    : [];
  const eligibleBaselines = baselines.filter(isBaselineEligible);
  const gaps = result ? gapsFor(result) : [];

  return (
    <main>
      <nav>
        <a className="brand" href="/">
          DeepAudit<span>CrossWalk</span>
        </a>
        <div className="nav-links">
          <span className="badge applicable">
            Private Local Single-Tenant Workspace
          </span>
          <a
            href="https://github.com/VivianFuVivianFu/DeepAuditCrossWalk"
            target="_blank"
            rel="noreferrer"
          >
            GitHub ↗
          </a>
        </div>
      </nav>
      <header>
        <p className="eyebrow">
          AUSTRALIAN BANKING & FINANCIAL SERVICES · DOCUMENT-FIRST ASSURANCE
        </p>
        <h1>
          Find the requirements
          <br />
          your assessment misses.
        </h1>
        <p className="lead">
          Upload your existing AI Assurance Questionnaire (.xlsx) to evaluate
          regulatory coverage, or optionally build a reviewed Enterprise Policy
          Baseline. Coverage findings remain distinct from legal compliance.
        </p>
      </header>

      <div
        className="tabs primary-workflow-tabs"
        role="group"
        aria-label="Primary product workflows"
      >
        <button
          disabled={busy || uploadBusy}
          className={activeTab === "assess_document" ? "active" : ""}
          onClick={() => {
            setActiveTab("assess_document");
            setError("");
            setStatusMessage("");
          }}
        >
          1. Assess a Document (Primary)
        </button>
        <button
          disabled={busy || uploadBusy}
          className={activeTab === "enterprise_policies" ? "active" : ""}
          onClick={() => {
            setActiveTab("enterprise_policies");
            setError("");
            setStatusMessage("");
          }}
        >
          2. Add Enterprise Policies (Optional)
        </button>
        <button
          disabled={busy || uploadBusy}
          className={activeTab === "synthetic_demo" ? "active" : ""}
          onClick={() => {
            setActiveTab("synthetic_demo");
            setError("");
            setStatusMessage("");
          }}
        >
          Synthetic Demo Example (DEMO_BANKING_V1)
        </button>
      </div>

      {statusMessage && (
        <aside className="notice" role="status">
          {statusMessage}
        </aside>
      )}
      {error && (
        <p className="error banner-error" role="alert">
          {error}
        </p>
      )}

      {activeTab === "assess_document" && (
        <>
          <aside className="notice">
            <strong>Document-First Assessment (Upload B).</strong> Upload your
            organisation&apos;s AI Governance or Assurance Questionnaire (.xlsx)
            to evaluate question coverage against the Shared Regulatory Library
            and, when explicitly selected, an approved Enterprise Baseline.
            Uploaded questionnaires never create enterprise baseline rules.
          </aside>

          <section className="workspace">
            <div className="panel">
              <p className="eyebrow">01 / UPLOAD B — ASSESSMENT TARGET</p>
              <h2>Assess a governance document</h2>
              <div
                className="tabs"
                role="group"
                aria-label="Assessment target type"
              >
                <button
                  disabled={busy || uploadBusy}
                  className={targetType === "questionnaire" ? "active" : ""}
                  onClick={() => setTargetType("questionnaire")}
                >
                  AI Assurance Questionnaire (.xlsx)
                </button>
                <button
                  disabled={busy || uploadBusy}
                  className={targetType === "strategy" ? "active" : ""}
                  onClick={() => setTargetType("strategy")}
                >
                  AI Governance Strategy (Planned)
                </button>
              </div>

              {targetType === "strategy" ? (
                <div className="notice" role="note">
                  <strong>
                    AI Governance Strategy Assessment — Planned / Unavailable in
                    PR 2.
                  </strong>
                  <p>
                    Strategy documents (.docx, .pdf, .txt) require a dedicated
                    section and governance-commitment extraction engine (planned
                    for PR 4). DeepAudit Crosswalk does not fabricate
                    questionnaire items from strategy prose. Select{" "}
                    <strong>AI Assurance Questionnaire (.xlsx)</strong> to run a
                    document coverage assessment now.
                  </p>
                </div>
              ) : (
                <>
                  <label>
                    Upload Enterprise Questionnaire (.xlsx, max 20 MB)
                    <input
                      type="file"
                      accept=".xlsx"
                      aria-label="Upload Enterprise Questionnaire (.xlsx)"
                      disabled={busy || uploadBusy}
                      onChange={handleQuestionnaireFileUpload}
                    />
                    <small>
                      Parsed read-only with formula-injection and XML bomb
                      guards. Extracts Question IDs, original wording, worksheet
                      and row provenance, and SHA-256 hash.
                    </small>
                  </label>

                  {questionnaires.length > 0 && (
                    <label>
                      Uploaded tenant questionnaires ({questionnaires.length})
                      <select
                        aria-label="Uploaded tenant questionnaires"
                        value={selectedQuestionnaireId}
                        disabled={busy || uploadBusy}
                        onChange={(e) => {
                          setSelectedQuestionnaireId(e.target.value);
                          setResult(null);
                        }}
                      >
                        {questionnaires.map((q) => (
                          <option
                            key={q.metadata.questionnaire_id}
                            value={q.metadata.questionnaire_id}
                          >
                            {q.metadata.source_filename} (
                            {q.metadata.questionnaire_id} · {q.questions.length}{" "}
                            questions)
                          </option>
                        ))}
                      </select>
                    </label>
                  )}

                  {activeQuestionnaire ? (
                    <div
                      className="preview-box"
                      aria-label="Extracted question preview"
                    >
                      <div className="section-title">
                        <strong>
                          Extracted Question Preview (
                          {activeQuestionnaire.questions.length})
                        </strong>
                        <span className="badge applicable">
                          SHA-256:{" "}
                          {activeQuestionnaire.metadata.source_sha256.slice(
                            0,
                            12,
                          )}
                          …
                        </span>
                      </div>
                      <p className="muted">
                        ID: {activeQuestionnaire.metadata.questionnaire_id} ·
                        File: {activeQuestionnaire.metadata.source_filename} ·
                        Version: {activeQuestionnaire.metadata.source_version} ·
                        Sheets:{" "}
                        {Object.keys(activeQuestionnaire.metadata.sheets).join(
                          ", ",
                        )}
                      </p>
                      {activeQuestionnaire.metadata.warnings?.map((w, i) => (
                        <p key={i} className="notice">
                          {w}
                        </p>
                      ))}
                      <div className="question-preview-list">
                        {activeQuestionnaire.questions
                          .slice(0, 25)
                          .map((q) => (
                            <div key={q.question_id} className="preview-item">
                              <div>
                                <strong>{q.question_id}</strong>{" "}
                                <span className="badge">
                                  {q.source_location || q.source_sheet}
                                </span>
                                {q.risk_domain && (
                                  <span className="badge">{q.risk_domain}</span>
                                )}
                              </div>
                              <p>{q.question_text}</p>
                            </div>
                          ))}
                      </div>
                    </div>
                  ) : (
                    <p className="muted">
                      No enterprise questionnaire uploaded yet. Upload an .xlsx
                      workbook above to preview extracted questions and run a
                      coverage assessment.
                    </p>
                  )}

                  <hr className="divider" />

                  <p className="eyebrow">02 / ASSESSMENT MODE & BASELINE</p>
                  <div
                    className="tabs"
                    role="group"
                    aria-label="Assessment baseline mode"
                  >
                    <button
                      disabled={busy || uploadBusy}
                      className={
                        assessmentMode === "regulatory_only" ? "active" : ""
                      }
                      onClick={() => {
                        setAssessmentMode("regulatory_only");
                        setSelectedBaselineId("");
                        setResult(null);
                      }}
                    >
                      Regulatory-Only (Default)
                    </button>
                    <button
                      disabled={busy || uploadBusy}
                      className={
                        assessmentMode === "enterprise_enhanced" ? "active" : ""
                      }
                      onClick={() => {
                        setAssessmentMode("enterprise_enhanced");
                        if (!selectedBaselineId && eligibleBaselines[0]) {
                          setSelectedBaselineId(
                            eligibleBaselines[0].baseline_id,
                          );
                        }
                        setResult(null);
                      }}
                    >
                      Enterprise-Enhanced (Optional)
                    </button>
                  </div>

                  {assessmentMode === "regulatory_only" ? (
                    <p className="muted">
                      Evaluates your uploaded questionnaire exclusively against
                      applicable Shared Regulatory Library obligations. Tenant
                      enterprise policies and baselines are never loaded.
                    </p>
                  ) : eligibleBaselines.length > 0 ? (
                    <label>
                      Select Approved Enterprise Baseline
                      <select
                        aria-label="Select Approved Enterprise Baseline"
                        value={selectedBaselineId}
                        disabled={busy || uploadBusy}
                        onChange={(e) => {
                          setSelectedBaselineId(e.target.value);
                          setResult(null);
                        }}
                      >
                        <option value="">-- Select a baseline --</option>
                        {eligibleBaselines.map((b) => (
                          <option key={b.baseline_id} value={b.baseline_id}>
                            {b.name} · v{b.version} (rev {b.revision}) ·{" "}
                            {b.approved_clause_ids?.length ?? 0} approved
                            clauses · {b.confirmed_control_ids.length} confirmed
                            controls
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <div className="notice">
                      <p>
                        No eligible approved Enterprise Baseline is available
                        for this tenant yet.
                      </p>
                      <button
                        type="button"
                        onClick={() => setActiveTab("enterprise_policies")}
                      >
                        Add & Review Enterprise Policies →
                      </button>
                    </div>
                  )}

                  <button
                    className="primary"
                    disabled={
                      busy ||
                      uploadBusy ||
                      !selectedQuestionnaireId ||
                      (assessmentMode === "enterprise_enhanced" &&
                        !selectedBaselineId)
                    }
                    onClick={runDocumentAssessment}
                  >
                    {busy
                      ? "Assessing questionnaire…"
                      : "Run questionnaire assessment →"}
                  </button>
                </>
              )}
            </div>

            <div className="panel">
              <div className="section-title">
                <div>
                  <p className="eyebrow">03 / ORGANISATION CONTEXT (OPTIONAL)</p>
                  <h2>Applicability context</h2>
                </div>
                <button
                  className="quiet"
                  onClick={loadExampleProfile}
                  disabled={busy || uploadBusy}
                >
                  Load example
                </button>
              </div>
              <p className="muted">
                Legally significant applicability facts default to Undetermined
                and are never inferred from document keywords. Standalone AI
                Use Case Assessment is not required.
              </p>
              <fieldset disabled={busy || uploadBusy}>
                <label>
                  Organisation or assessment context label
                  <input
                    maxLength={200}
                    value={orgName}
                    onChange={(e) => {
                      setOrgName(e.target.value);
                      setResult(null);
                    }}
                  />
                </label>
                <div className="facts">
                  {Object.entries(factLabels).map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <select
                        aria-label={label}
                        value={
                          facts[key as FactKey] === null
                            ? "unknown"
                            : String(facts[key as FactKey])
                        }
                        onChange={(e) =>
                          updateFact(
                            key as FactKey,
                            parseFact(e.target.value),
                          )
                        }
                      >
                        <option value="unknown">Undetermined</option>
                        <option value="true">Yes — confirmed</option>
                        <option value="false">No — confirmed</option>
                      </select>
                    </label>
                  ))}
                </div>
                <label>
                  Human approval threshold (AUD)
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Unknown"
                    value={threshold}
                    onChange={(e) => {
                      setThreshold(e.target.value);
                      setResult(null);
                    }}
                  />
                </label>
              </fieldset>
              <div className="chain">
                External + Optional Enterprise Requirements → Atomic Facets →
                Uploaded Questions → Deterministic Validation → Human Review
              </div>
            </div>
          </section>
        </>
      )}

      {activeTab === "enterprise_policies" && (
        <>
          <aside className="notice">
            <strong>
              Add Enterprise Policies — Optional Baseline Builder (Upload A).
            </strong>{" "}
            Uploaded internal policies are tenant-owned Baseline Sources.
            Uploading a policy never approves its clauses or control mappings
            automatically, and never turns the policy into an Assessment Target.
          </aside>

          <section className="workspace">
            <div className="panel">
              <p className="eyebrow">01 / UPLOAD A — POLICY IMPORT</p>
              <h2>Import internal governance policy</h2>
              <div
                className="tabs"
                role="group"
                aria-label="Policy import source"
              >
                <button
                  disabled={busy || uploadBusy}
                  className={policyInputMode === "file" ? "active" : ""}
                  onClick={() => setPolicyInputMode("file")}
                >
                  Upload File (.pdf, .docx, .txt, .md)
                </button>
                <button
                  disabled={busy || uploadBusy}
                  className={policyInputMode === "text" ? "active" : ""}
                  onClick={() => setPolicyInputMode("text")}
                >
                  Paste Policy Text
                </button>
              </div>

              <fieldset disabled={busy || uploadBusy}>
                <label>
                  Policy document name
                  <input
                    maxLength={200}
                    value={policyName}
                    onChange={(e) => setPolicyName(e.target.value)}
                  />
                </label>
                <div className="facts">
                  <label>
                    Version
                    <input
                      maxLength={64}
                      value={policyVersion}
                      onChange={(e) => setPolicyVersion(e.target.value)}
                    />
                  </label>
                  <label>
                    Category
                    <select
                      aria-label="Policy category"
                      value={policyCategory}
                      onChange={(e) => setPolicyCategory(e.target.value)}
                    >
                      <option value="ai_governance">AI Governance Policy</option>
                      <option value="risk_management">
                        AI Risk Management Policy
                      </option>
                      <option value="delegated_authority">
                        Delegated Authority Policy
                      </option>
                      <option value="privacy">Privacy Policy</option>
                      <option value="cybersecurity">
                        Cybersecurity Standard
                      </option>
                      <option value="data_governance">
                        Data Governance Standard
                      </option>
                    </select>
                  </label>
                </div>
                <label>
                  Authority level
                  <select
                    aria-label="Authority level"
                    value={policyAuthority}
                    onChange={(e) => setPolicyAuthority(e.target.value)}
                  >
                    <option value="enterprise_policy">Enterprise Policy</option>
                    <option value="governance_standard">
                      Governance Standard
                    </option>
                    <option value="control_standard">Control Standard</option>
                    <option value="procedural_guideline">
                      Procedural Guideline
                    </option>
                  </select>
                </label>

                {policyInputMode === "file" ? (
                  <label>
                    Select policy file (.pdf, .docx, .txt, .md)
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt,.md"
                      aria-label="Select policy file"
                      onChange={handlePolicyFileUpload}
                    />
                  </label>
                ) : (
                  <>
                    <label>
                      Policy text
                      <textarea
                        rows={6}
                        value={policyTextDraft}
                        onChange={(e) => setPolicyTextDraft(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="primary"
                      disabled={!policyName.trim() || !policyTextDraft.trim()}
                      onClick={handlePolicyTextImport}
                    >
                      Extract candidate requirements →
                    </button>
                  </>
                )}
              </fieldset>

              <hr className="divider" />

              <p className="eyebrow">02 / COMPILE VERSIONED BASELINE</p>
              <h2>Create Enterprise Baseline</h2>
              <p className="muted">
                Only policies with at least one explicitly Approved clause can
                produce an eligible active Enterprise Baseline. Control mappings
                require separate approval before contributing to confirmed
                controls.
              </p>
              <label>
                Baseline name
                <input
                  value={baselineName}
                  onChange={(e) => setBaselineName(e.target.value)}
                />
              </label>
              <label>
                Baseline version
                <input
                  value={baselineVersion}
                  onChange={(e) => setBaselineVersion(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="primary"
                disabled={
                  busy ||
                  uploadBusy ||
                  selectedPolicyIdsForBaseline.length === 0 ||
                  !baselineName.trim()
                }
                onClick={handleCompileBaseline}
              >
                Compile approved baseline (
                {selectedPolicyIdsForBaseline.length} selected) →
              </button>

              {baselines.length > 0 && (
                <div className="baseline-list">
                  <h3>Compiled tenant baselines ({baselines.length})</h3>
                  {baselines.map((b) => {
                    const eligible = isBaselineEligible(b);
                    return (
                      <div key={b.baseline_id} className="preview-item">
                        <div className="section-title">
                          <strong>
                            {b.name} (v{b.version} · rev {b.revision})
                          </strong>
                          <span
                            className={`badge ${eligible ? "applicable" : "undetermined"}`}
                          >
                            {eligible ? "Eligible Active" : "Ineligible"}
                          </span>
                        </div>
                        <p className="muted">
                          Approved clauses:{" "}
                          {b.approved_clause_ids?.length ?? 0} · Confirmed
                          controls: {b.confirmed_control_ids.length} ·
                          Fingerprint:{" "}
                          {(b.baseline_sha256 || "").slice(0, 12) || "n/a"}…
                        </p>
                        {eligible && (
                          <button
                            type="button"
                            className="quiet"
                            onClick={() => {
                              setSelectedBaselineId(b.baseline_id);
                              setAssessmentMode("enterprise_enhanced");
                              setActiveTab("assess_document");
                            }}
                          >
                            Use in Document Assessment →
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="panel">
              <p className="eyebrow">
                03 / CLAUSE & CONTROL MAPPING HUMAN REVIEW
              </p>
              <h2>Review candidate requirements</h2>
              {policies.length === 0 ? (
                <p className="muted">
                  No internal policies imported yet. Upload a policy file or
                  extract policy text on the left to review candidate clauses
                  and control mappings.
                </p>
              ) : (
                <>
                  <label>
                    Select imported policy to review ({policies.length})
                    <select
                      aria-label="Select imported policy to review"
                      value={selectedPolicyId}
                      onChange={(e) => setSelectedPolicyId(e.target.value)}
                    >
                      {policies.map((p) => {
                        const status = derivePolicyLifecycleStatus(
                          p,
                          policyClauses[p.policy_id],
                        );
                        return (
                          <option key={p.policy_id} value={p.policy_id}>
                            {p.name} (v{p.version}) — [{status}]
                          </option>
                        );
                      })}
                    </select>
                  </label>

                  {activePolicy && (
                    <div className="policy-review-box">
                      <div className="section-title">
                        <div>
                          <strong>{activePolicy.name}</strong>
                          <p className="muted">
                            Policy ID: {activePolicy.policy_id} · Category:{" "}
                            {activePolicy.category} · SHA-256:{" "}
                            {(activePolicy.file_sha256 || "").slice(0, 12) ||
                              "n/a"}
                            …
                          </p>
                        </div>
                        <span className="badge applicable">
                          {derivePolicyLifecycleStatus(
                            activePolicy,
                            activePolicyClauseList,
                          )}
                        </span>
                      </div>

                      <label className="checkbox-row">
                        <input
                          type="checkbox"
                          checked={selectedPolicyIdsForBaseline.includes(
                            activePolicy.policy_id,
                          )}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setSelectedPolicyIdsForBaseline((prev) =>
                              checked
                                ? [...prev, activePolicy.policy_id]
                                : prev.filter(
                                    (id) => id !== activePolicy.policy_id,
                                  ),
                            );
                          }}
                        />
                        Include this policy when compiling Enterprise Baseline
                      </label>

                      {activePolicyClauseList.map((clause) => (
                        <div key={clause.clause_id} className="preview-item">
                          <div className="section-title">
                            <span>
                              <strong>
                                {clause.clause_number || clause.source_name}
                              </strong>{" "}
                              ({clause.clause_id})
                            </span>
                            <span
                              className={`badge ${
                                clause.review_status === "approved" ||
                                clause.review_status === "confirmed"
                                  ? "applicable"
                                  : clause.review_status === "rejected"
                                    ? "high"
                                    : "undetermined"
                              }`}
                            >
                              Clause: {clause.review_status}
                            </span>
                          </div>
                          <p>{clause.text}</p>
                          <p className="muted">
                            Facets:{" "}
                            {clause.control_facets.join(", ") ||
                              "none (mapping_incomplete)"}{" "}
                            {clause.thresholds_aud &&
                            clause.thresholds_aud.length > 0
                              ? `· Threshold: ${clause.threshold_operator || ">="} ${clause.thresholds_aud.join(", ")} ${clause.threshold_currency || "AUD"}`
                              : ""}{" "}
                            {clause.required_approval_role
                              ? `· Role: ${clause.required_approval_role}`
                              : ""}{" "}
                            {clause.approval_timing
                              ? `· Timing: ${clause.approval_timing}`
                              : ""}
                          </p>
                          <div className="action-row">
                            <button
                              type="button"
                              className="quiet"
                              disabled={busy}
                              onClick={() =>
                                handleClauseReview(
                                  activePolicy.policy_id,
                                  clause.clause_id,
                                  "approved",
                                )
                              }
                            >
                              Approve Clause
                            </button>
                            <button
                              type="button"
                              className="quiet"
                              disabled={busy}
                              onClick={() =>
                                handleClauseReview(
                                  activePolicy.policy_id,
                                  clause.clause_id,
                                  "rejected",
                                )
                              }
                            >
                              Reject Clause
                            </button>
                          </div>

                          {clause.control_mappings.length > 0 ? (
                            <div className="mappings-subbox">
                              <strong>
                                Candidate Control Mappings (Separate Approval
                                Required):
                              </strong>
                              {clause.control_mappings.map((m) => (
                                <div key={m.mapping_id} className="mapping-row">
                                  <div>
                                    <strong>{m.control_id}</strong> ·{" "}
                                    {m.relationship} ·{" "}
                                    <span className="badge">
                                      Mapping: {m.review_status}
                                    </span>
                                    <small>{m.rationale}</small>
                                  </div>
                                  <div className="action-row">
                                    <button
                                      type="button"
                                      className="quiet"
                                      disabled={busy}
                                      onClick={() =>
                                        handleMappingReview(
                                          activePolicy.policy_id,
                                          clause.clause_id,
                                          m.mapping_id,
                                          "approved",
                                        )
                                      }
                                    >
                                      Approve Mapping
                                    </button>
                                    <button
                                      type="button"
                                      className="quiet"
                                      disabled={busy}
                                      onClick={() =>
                                        handleMappingReview(
                                          activePolicy.policy_id,
                                          clause.clause_id,
                                          m.mapping_id,
                                          "rejected",
                                        )
                                      }
                                    >
                                      Reject Mapping
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="muted">
                              Unmapped enterprise requirement — remains
                              traceable as mapping_incomplete until facets and
                              controls are assigned.
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </section>
        </>
      )}

      {activeTab === "synthetic_demo" && (
        <>
          <aside className="notice">
            <strong>Isolated Synthetic Demonstration (DEMO_BANKING_V1).</strong>{" "}
            This example mode uses 19 synthetic demonstration questions on an
            isolated stateless demo gateway (/api/analysis). It never accesses
            private tenant documents or baselines, and is never used for real
            customer assessments.
          </aside>
          <section className="workspace">
            <div className="panel">
              <div className="section-title">
                <div>
                  <p className="eyebrow">01 / SYNTHETIC DEMO CONTEXT</p>
                  <h2>Your AI use case</h2>
                </div>
                <button
                  className="quiet"
                  onClick={loadExampleProfile}
                  disabled={busy}
                >
                  Load example
                </button>
              </div>
              <fieldset disabled={busy}>
                <label>
                  Use case name
                  <input
                    maxLength={200}
                    value={orgName}
                    onChange={(e) => {
                      setOrgName(e.target.value);
                      setResult(null);
                    }}
                  />
                </label>
                <div className="facts">
                  {Object.entries(factLabels).map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <select
                        aria-label={label}
                        value={
                          facts[key as FactKey] === null
                            ? "unknown"
                            : String(facts[key as FactKey])
                        }
                        onChange={(e) =>
                          updateFact(
                            key as FactKey,
                            parseFact(e.target.value),
                          )
                        }
                      >
                        <option value="unknown">Undetermined</option>
                        <option value="true">Yes — confirmed</option>
                        <option value="false">No — confirmed</option>
                      </select>
                    </label>
                  ))}
                </div>
                <label>
                  Human approval threshold (AUD)
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Unknown"
                    value={threshold}
                    onChange={(e) => {
                      setThreshold(e.target.value);
                      setResult(null);
                    }}
                  />
                </label>
              </fieldset>
            </div>
            <div className="panel">
              <p className="eyebrow">02 / SYNTHETIC DEMO ANALYSIS</p>
              <h2>Choose an analysis</h2>
              <div
                className="tabs"
                role="group"
                aria-label="Assessment type"
              >
                <button
                  disabled={busy}
                  className={demoKind === "coverage" ? "active" : ""}
                  onClick={() => {
                    setDemoKind("coverage");
                    setResult(null);
                  }}
                >
                  Questionnaire coverage
                </button>
                <button
                  disabled={busy}
                  className={demoKind === "policy-gaps" ? "active" : ""}
                  onClick={() => {
                    setDemoKind("policy-gaps");
                    setResult(null);
                  }}
                >
                  Enterprise policy gaps
                </button>
              </div>
              {demoKind === "coverage" ? (
                <p>
                  Evaluate the selected facts against the synthetic
                  DEMO_BANKING_V1 question pack.
                </p>
              ) : (
                <label>
                  Policy excerpt
                  <textarea
                    disabled={busy}
                    rows={9}
                    maxLength={250000}
                    value={demoPolicyExcerpt}
                    onChange={(e) => {
                      setDemoPolicyExcerpt(e.target.value);
                      setResult(null);
                    }}
                  />
                </label>
              )}
              <button
                className="primary"
                disabled={
                  busy ||
                  (demoKind === "policy-gaps" && !demoPolicyExcerpt.trim())
                }
                onClick={runSyntheticDemoAnalysis}
              >
                {busy ? "Assessing…" : "Run assessment →"}
              </button>
            </div>
          </section>
        </>
      )}

      {result && (
        <section className="results" aria-live="polite">
          <div className="section-title">
            <div>
              <p className="eyebrow">04 / FINDINGS & GAP REPORT</p>
              <h2>Traceable assessment results</h2>
            </div>
            <button onClick={download}>Export JSON ↓</button>
          </div>
          <p className="muted">
            Assessment {result.assessment_id} · Mode:{" "}
            {result.assessment_mode || "regulatory_only"} · Regulatory pack{" "}
            {result.regulatory_pack_version} · Questionnaire SHA-256:{" "}
            {result.questionnaire_sha256?.slice(0, 12)}… ·{" "}
            {new Date(result.created_at).toLocaleString()}
          </p>
          {result.enterprise_baseline_id && (
            <p className="notice">
              Enterprise-Enhanced Baseline ID: {result.enterprise_baseline_id}{" "}
              {result.enterprise_baseline_version
                ? `(v${result.enterprise_baseline_version})`
                : ""}
            </p>
          )}
          {result.selection_warning && (
            <p className="notice">{result.selection_warning}</p>
          )}
          {result.warnings?.map((warning, i) => (
            <p className="notice" key={i}>
              {warning}
            </p>
          ))}
          {result.metrics && (
            <div className="metrics">
              {[
                [
                  "Confirmed coverage",
                  `${result.metrics.confirmed_coverage_rate}%`,
                ],
                ["Confirmed missing", result.metrics.confirmed_missing],
                [
                  "Conditional applicability",
                  result.metrics.applicability_conditional,
                ],
                [
                  "Undetermined applicability",
                  result.metrics.applicability_undetermined,
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          )}
          {result.results &&
            ["binding", "enforceable_guidance", "guidance", "voluntary"].map(
              (authority) => {
                const items = result.results!.filter(
                  (item) => item.authority === authority,
                );
                return items.length ? (
                  <div key={authority}>
                    <h3>
                      {authority === "voluntary"
                        ? "Voluntary standards alignment"
                        : authority.replaceAll("_", " ")}
                    </h3>
                    {items.map((item) => (
                      <details key={item.obligation_id}>
                        <summary>
                          <span>
                            <strong>{item.title}</strong>
                            <small>
                              {item.instrument} · {item.provision}
                            </small>
                          </span>
                          <span
                            className={`badge ${item.applicability.status}`}
                          >
                            {item.applicability.status.replaceAll("_", " ")}
                          </span>
                          <span className="badge">
                            {item.confirmed_status.replaceAll("_", " ")}
                          </span>
                        </summary>
                        <div className="detail">
                          <p>{item.applicability.reason}</p>
                          <p>
                            Candidate status: {item.provisional_status}.
                            Approved mappings:{" "}
                            {item.confirmed_question_ids.join(", ") || "none"}.
                            Proposed questions:{" "}
                            {item.candidate_question_ids.join(", ") || "none"}.
                          </p>
                          <p>
                            <strong>Unconfirmed facets:</strong>{" "}
                            {item.confirmed_missing_facets.join(", ") || "none"}
                          </p>
                          {item.suggested_questions.map((question, i) => (
                            <p key={i}>Suggested: {question}</p>
                          ))}
                          <p>
                            <strong>Evidence:</strong>{" "}
                            {item.evidence_requirements.join(" · ")}
                          </p>
                          <a
                            href={item.source_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            Regulatory source ↗
                          </a>
                        </div>
                      </details>
                    ))}
                  </div>
                ) : null;
              },
            )}

          {result.enterprise_clause_coverage &&
            result.enterprise_clause_coverage.length > 0 && (
              <div>
                <h3>
                  Enterprise Baseline Clause Coverage (
                  {result.enterprise_clause_coverage.length})
                </h3>
                {result.enterprise_clause_coverage.map((ec) => (
                  <details key={ec.clause_id}>
                    <summary>
                      <span>
                        <strong>
                          {ec.source_name} ({ec.clause_id})
                        </strong>
                        <small>{ec.rationale}</small>
                      </span>
                      <span className="badge applicable">
                        Clause: {ec.clause_approval_status}
                      </span>
                      <span className="badge">
                        Mapping: {ec.control_mapping_approval_status}
                      </span>
                      <span
                        className={`badge ${
                          ec.coverage_status === "covered"
                            ? "applicable"
                            : ec.coverage_status === "missing"
                              ? "high"
                              : "undetermined"
                        }`}
                      >
                        {ec.coverage_status.replaceAll("_", " ")}
                      </span>
                    </summary>
                    <div className="detail">
                      <p>{ec.rationale}</p>
                      <p>
                        <strong>7 Orthogonal Assurance Dimensions:</strong>{" "}
                        Applicability: {ec.applicability_status} · Clause
                        Approval: {ec.clause_approval_status} · Control Mapping
                        Approval: {ec.control_mapping_approval_status} ·
                        Question-to-Facet Approval:{" "}
                        {ec.questionnaire_to_facet_approval_status} · Coverage:{" "}
                        {ec.coverage_status} · Implementation Evidence:{" "}
                        {ec.implementation_evidence_status} · Operational
                        Effectiveness: {ec.operational_effectiveness_status}
                      </p>
                      <p>
                        <strong>Required facets:</strong>{" "}
                        {ec.required_facets.join(", ") || "none"} ·{" "}
                        <strong>Covered:</strong>{" "}
                        {ec.covered_facets.join(", ") || "none"} ·{" "}
                        <strong>Missing:</strong>{" "}
                        {ec.missing_facets.join(", ") || "none"}
                      </p>
                      <p>
                        <strong>Confirmed questions:</strong>{" "}
                        {ec.confirmed_question_ids.join(", ") || "none"} ·{" "}
                        <strong>Candidate questions (review required):</strong>{" "}
                        {ec.candidate_question_ids.join(", ") || "none"}
                      </p>
                    </div>
                  </details>
                ))}
              </div>
            )}

          <h3>Gaps and remediation ({gaps.length})</h3>
          {gaps.map((gap) => (
            <details key={gap.gap_id}>
              <summary>
                <span>
                  <strong>{gap.title}</strong>
                  <small>
                    {gap.gap_type.replaceAll("_", " ")}{" "}
                    {gap.coverage_status ? `· ${gap.coverage_status}` : ""}
                  </small>
                </span>
                <span className={`badge ${gap.severity}`}>{gap.severity}</span>
              </summary>
              <div className="detail">
                <p>{gap.recommendation}</p>
                <p>
                  <strong>Missing facets:</strong>{" "}
                  {gap.missing_facets.join(", ") || "See recommendation"}
                </p>
                <p>
                  <strong>Evidence:</strong>{" "}
                  {gap.evidence_required.join(" · ") || "Reviewer to determine"}
                </p>
              </div>
            </details>
          ))}
        </section>
      )}
      <footer>
        <span>DeepAuditCrossWalk · Independent project · Apache-2.0</span>
        <a href="http://localhost:8000/docs">Local API documentation ↗</a>
      </footer>
    </main>
  );
}
