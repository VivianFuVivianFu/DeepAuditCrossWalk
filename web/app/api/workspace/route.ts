import { NextResponse } from "next/server";
import {
  ACTION_PERMISSIONS,
  type SecurityContext,
  hasPermission,
  primaryRole,
  resolveSecurityContext,
  signBackendWorkspaceContext,
  verifyCsrfProtection,
} from "../../security";

const MAX_WORKSPACE_UPLOAD_BYTES = 28_000_000;
const MAX_WORKSPACE_JSON_BYTES = 1_000_000;

const UPLOAD_ACTIONS = new Set([
  "import_questionnaire",
  "import_policy_file",
  "import_policy_text",
  "import_policy",
]);

const SAFE_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const XLSX_FILENAME_PATTERN = /^[^/\\\x00]+\.xlsx$/i;
const POLICY_FILENAME_PATTERN = /^[^/\\\x00]+\.(pdf|docx|txt|md)$/i;

function backendHeaders(ctx: SecurityContext): Record<string, string> {
  const role = primaryRole(ctx.roles);
  const signedContext = signBackendWorkspaceContext(ctx);
  return {
    "Content-Type": "application/json",
    "X-Tenant-ID": ctx.tenant_id,
    "X-Actor": ctx.user_id,
    "X-Role": role,
    ...(signedContext ? { "X-Workspace-Context": signedContext } : {}),
    ...(process.env.CROSSWALK_API_KEY
      ? { "X-API-Key": process.env.CROSSWALK_API_KEY }
      : {}),
  };
}

function assertSafeId(value: unknown, label: string): string {
  if (typeof value !== "string" || !SAFE_ID_PATTERN.test(value.trim())) {
    throw new Error(`Invalid or missing ${label}.`);
  }
  return value.trim();
}

export async function GET(request: Request) {
  const resolved = resolveSecurityContext(request);
  if (!resolved.ok) {
    return NextResponse.json(
      { error: resolved.error, detail: resolved.error },
      { status: resolved.status }
    );
  }
  const ctx = resolved.context;

  return NextResponse.json(
    {
      workspace_mode:
        ctx.deployment_mode === "local_dev_bypass"
          ? "local_private_single_tenant"
          : "authenticated_single_tenant",
      deployment_mode: ctx.deployment_mode,
      authenticated: ctx.authenticated,
      user_id: ctx.user_id,
      display_name: ctx.display_name,
      tenant_scope: ctx.tenant_id,
      roles: ctx.roles,
      permissions: ctx.permissions,
      csrf_token: ctx.csrf_token,
      public_demo_isolated: true,
      supported_targets: {
        questionnaire: {
          status: "available",
          formats: [".xlsx"],
        },
        strategy: {
          status: "planned_unavailable",
          planned_formats: [".docx", ".pdf", ".txt"],
          reason:
            "AI Governance Strategy Assessment requires an independent commitment-extraction and validation pipeline (planned for PR 4) and is not simulated via Questionnaire Coverage.",
        },
      },
    },
    { headers: { "Cache-Control": "no-store" } }
  );
}

export async function POST(request: Request) {
  const initialResolved = resolveSecurityContext(request);
  if (!initialResolved.ok) {
    return NextResponse.json(
      { error: initialResolved.error, detail: initialResolved.error },
      { status: initialResolved.status }
    );
  }

  const csrfCheck = verifyCsrfProtection(request, initialResolved.context);
  if (!csrfCheck.ok) {
    return NextResponse.json(
      { error: csrfCheck.error, detail: csrfCheck.error },
      { status: csrfCheck.status }
    );
  }

  let input: Record<string, unknown>;
  let rawByteCount = 0;
  try {
    const reader = request.body?.getReader();
    if (!reader) {
      return NextResponse.json(
        { error: "A JSON request body is required." },
        { status: 400 }
      );
    }
    const chunks: Uint8Array[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      rawByteCount += value.byteLength;
      if (rawByteCount > MAX_WORKSPACE_UPLOAD_BYTES) {
        await reader.cancel();
        return NextResponse.json(
          { error: "Workspace upload request exceeds the 28 MB limit." },
          { status: 413 }
        );
      }
      chunks.push(value);
    }
    input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (!input || Array.isArray(input) || typeof input !== "object") {
      return NextResponse.json(
        { error: "A JSON object body is required." },
        { status: 400 }
      );
    }
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON request." },
      { status: 400 }
    );
  }

  let ctx = initialResolved.context;
  if (typeof input.tenant_id === "string" && input.tenant_id.trim()) {
    const tenantResolved = resolveSecurityContext(
      request,
      input.tenant_id.trim()
    );
    if (!tenantResolved.ok) {
      return NextResponse.json(
        { error: tenantResolved.error, detail: tenantResolved.error },
        { status: tenantResolved.status }
      );
    }
    ctx = tenantResolved.context;
  }

  const action = typeof input.action === "string" ? input.action : "";
  if (!UPLOAD_ACTIONS.has(action) && rawByteCount > MAX_WORKSPACE_JSON_BYTES) {
    return NextResponse.json(
      { error: "Workspace request exceeds the 1 MB JSON payload limit." },
      { status: 413 }
    );
  }

  const requiredPermission = ACTION_PERMISSIONS[action];
  if (!requiredPermission) {
    return NextResponse.json(
      { error: "Unsupported workspace action.", detail: "Unsupported workspace action." },
      { status: 400 }
    );
  }

  if (!hasPermission(ctx, requiredPermission)) {
    const msg = `Permission denied: role '${primaryRole(
      ctx.roles
    )}' lacks '${requiredPermission}' required for '${action}'.`;
    return NextResponse.json({ error: msg, detail: msg }, { status: 403 });
  }

  const baseUrl = process.env.CROSSWALK_API_URL || "http://127.0.0.1:8000";
  let targetPath = "";
  let method: "GET" | "POST" | "PUT" | "DELETE" = "POST";
  let bodyPayload: Record<string, unknown> | undefined;

  try {
    switch (action) {
      case "import_questionnaire": {
        const filename =
          typeof input.filename === "string" ? input.filename.trim() : "";
        const workbookBase64 =
          typeof input.workbook_base64 === "string"
            ? input.workbook_base64.trim()
            : "";
        if (!XLSX_FILENAME_PATTERN.test(filename)) {
          return NextResponse.json(
            { error: "Questionnaire upload requires a valid .xlsx filename." },
            { status: 400 }
          );
        }
        if (!workbookBase64) {
          return NextResponse.json(
            { error: "Questionnaire workbook content is required." },
            { status: 400 }
          );
        }
        targetPath = "/v1/questionnaires/import";
        method = "POST";
        bodyPayload = {
          filename,
          workbook_base64: workbookBase64,
          ...(Array.isArray(input.sheet_names)
            ? { sheet_names: input.sheet_names }
            : {}),
          ...(input.column_mapping &&
          typeof input.column_mapping === "object" &&
          !Array.isArray(input.column_mapping)
            ? { column_mapping: input.column_mapping }
            : {}),
        };
        break;
      }

      case "list_questionnaires": {
        targetPath = "/v1/questionnaires";
        method = "GET";
        break;
      }

      case "get_questionnaire": {
        const qid = assertSafeId(input.questionnaire_id, "questionnaire_id");
        if (qid === "DEMO_BANKING_V1") {
          return NextResponse.json(
            {
              error:
                "DEMO_BANKING_V1 is reserved for the synthetic demo and cannot be loaded as a customer questionnaire.",
            },
            { status: 400 }
          );
        }
        targetPath = `/v1/questionnaires/${encodeURIComponent(qid)}`;
        method = "GET";
        break;
      }

      case "assess_coverage":
      case "run_coverage_assessment": {
        const targetType =
          typeof input.assessment_target_type === "string"
            ? input.assessment_target_type
            : "questionnaire";
        if (targetType === "strategy") {
          return NextResponse.json(
            {
              error:
                "AI Governance Strategy Assessment is planned for PR 4 and is not available in this release. Select AI Assurance / Governance Questionnaire (.xlsx).",
            },
            { status: 501 }
          );
        }
        if (input.questionnaire_pack) {
          return NextResponse.json(
            {
              error:
                "Customer document assessments must use an uploaded questionnaire_id and cannot use DEMO_BANKING_V1.",
            },
            { status: 400 }
          );
        }
        const qid = assertSafeId(input.questionnaire_id, "questionnaire_id");
        if (qid === "DEMO_BANKING_V1") {
          return NextResponse.json(
            {
              error:
                "DEMO_BANKING_V1 is reserved for the synthetic demo and cannot be used for customer questionnaire assessment.",
            },
            { status: 400 }
          );
        }
        const mode =
          input.assessment_mode === "enterprise_enhanced"
            ? "enterprise_enhanced"
            : input.assessment_mode === "regulatory_only" ||
              input.assessment_mode === undefined
            ? "regulatory_only"
            : "";
        if (!mode) {
          return NextResponse.json(
            {
              error:
                "assessment_mode must be 'regulatory_only' or 'enterprise_enhanced'.",
            },
            { status: 400 }
          );
        }
        if (mode === "regulatory_only" && input.enterprise_baseline_id) {
          return NextResponse.json(
            {
              error:
                "enterprise_baseline_id cannot be supplied when assessment_mode is 'regulatory_only'.",
            },
            { status: 400 }
          );
        }
        let baselineId: string | undefined;
        if (mode === "enterprise_enhanced") {
          baselineId = assertSafeId(
            input.enterprise_baseline_id,
            "enterprise_baseline_id"
          );
        }
        const useCase =
          input.use_case &&
          typeof input.use_case === "object" &&
          !Array.isArray(input.use_case)
            ? input.use_case
            : undefined;

        targetPath = "/v1/assessments/coverage";
        method = "POST";
        bodyPayload = {
          questionnaire_id: qid,
          assessment_mode: mode,
          assessment_target_type: "questionnaire",
          selection_mode: "full_questionnaire",
          persist: true,
          ...(useCase ? { use_case: useCase } : {}),
          ...(baselineId ? { enterprise_baseline_id: baselineId } : {}),
          ...(mode === "enterprise_enhanced" &&
          typeof input.enterprise_baseline_version === "string" &&
          input.enterprise_baseline_version.trim()
            ? {
                enterprise_baseline_version:
                  input.enterprise_baseline_version.trim(),
              }
            : {}),
        };
        break;
      }

      case "import_policy_file": {
        const name = typeof input.name === "string" ? input.name.trim() : "";
        const filename =
          typeof input.filename === "string" ? input.filename.trim() : "";
        const fileBase64 =
          typeof input.file_base64 === "string" ? input.file_base64.trim() : "";
        if (!name) {
          return NextResponse.json(
            { error: "Policy name is required." },
            { status: 400 }
          );
        }
        if (!POLICY_FILENAME_PATTERN.test(filename)) {
          return NextResponse.json(
            {
              error:
                "Enterprise policy file upload requires a .pdf, .docx, .txt, or .md filename.",
            },
            { status: 400 }
          );
        }
        if (!fileBase64) {
          return NextResponse.json(
            { error: "Policy file content is required." },
            { status: 400 }
          );
        }
        targetPath = "/v1/enterprise/policies/import-file";
        method = "POST";
        bodyPayload = {
          name,
          filename,
          file_base64: fileBase64,
          version:
            typeof input.version === "string" && input.version.trim()
              ? input.version.trim()
              : "1.0.0",
          category:
            typeof input.category === "string" && input.category.trim()
              ? input.category.trim()
              : "ai_governance",
          authority_level:
            typeof input.authority_level === "string" &&
            input.authority_level.trim()
              ? input.authority_level.trim()
              : "enterprise_policy",
        };
        break;
      }

      case "import_policy_text":
      case "import_policy": {
        const name = typeof input.name === "string" ? input.name.trim() : "";
        const text = typeof input.text === "string" ? input.text.trim() : "";
        if (!name || !text) {
          return NextResponse.json(
            { error: "Policy name and policy text are required." },
            { status: 400 }
          );
        }
        targetPath = "/v1/enterprise/policies/import";
        method = "POST";
        bodyPayload = {
          name,
          text,
          version:
            typeof input.version === "string" && input.version.trim()
              ? input.version.trim()
              : "1.0.0",
          category:
            typeof input.category === "string" && input.category.trim()
              ? input.category.trim()
              : "ai_governance",
          authority_level:
            typeof input.authority_level === "string" &&
            input.authority_level.trim()
              ? input.authority_level.trim()
              : "enterprise_policy",
        };
        break;
      }

      case "list_policies": {
        targetPath = "/v1/enterprise/policies";
        method = "GET";
        break;
      }

      case "get_policy": {
        const policyId = assertSafeId(input.policy_id, "policy_id");
        targetPath = `/v1/enterprise/policies/${encodeURIComponent(policyId)}`;
        method = "GET";
        break;
      }

      case "get_policy_clauses":
      case "list_clauses": {
        const policyId = assertSafeId(input.policy_id, "policy_id");
        targetPath = `/v1/enterprise/policies/${encodeURIComponent(policyId)}/clauses`;
        method = "GET";
        break;
      }

      case "delete_policy": {
        const policyId = assertSafeId(input.policy_id, "policy_id");
        targetPath = `/v1/enterprise/policies/${encodeURIComponent(policyId)}`;
        method = "DELETE";
        break;
      }

      case "review_clause": {
        const clauseId = assertSafeId(input.clause_id, "clause_id");
        const status =
          typeof input.status === "string" ? input.status.trim() : "";
        if (!["approved", "confirmed", "rejected", "proposed"].includes(status)) {
          return NextResponse.json(
            { error: "Invalid clause review status." },
            { status: 400 }
          );
        }
        targetPath = `/v1/enterprise/clauses/${encodeURIComponent(clauseId)}/review`;
        method = "PUT";
        bodyPayload = {
          status,
          actor: ctx.user_id,
          role: primaryRole(ctx.roles),
          ...(typeof input.review_comment === "string" &&
          input.review_comment.trim()
            ? { review_comment: input.review_comment.trim() }
            : {}),
        };
        break;
      }

      case "review_clause_mapping": {
        const clauseId = assertSafeId(input.clause_id, "clause_id");
        const mappingId = assertSafeId(input.mapping_id, "mapping_id");
        const status =
          typeof input.status === "string" ? input.status.trim() : "";
        if (!["approved", "confirmed", "rejected", "proposed"].includes(status)) {
          return NextResponse.json(
            { error: "Invalid control mapping review status." },
            { status: 400 }
          );
        }
        targetPath = `/v1/enterprise/clauses/${encodeURIComponent(clauseId)}/mappings/${encodeURIComponent(mappingId)}/review`;
        method = "PUT";
        bodyPayload = {
          status,
          actor: ctx.user_id,
          role: primaryRole(ctx.roles),
          ...(typeof input.relationship === "string" &&
          input.relationship.trim()
            ? { relationship: input.relationship.trim() }
            : {}),
          ...(Array.isArray(input.mapped_facets)
            ? { mapped_facets: input.mapped_facets }
            : {}),
          ...(typeof input.review_comment === "string" &&
          input.review_comment.trim()
            ? { review_comment: input.review_comment.trim() }
            : {}),
        };
        break;
      }

      case "create_baseline": {
        const name = typeof input.name === "string" ? input.name.trim() : "";
        const policyIds = Array.isArray(input.policy_ids)
          ? input.policy_ids.map((id) => assertSafeId(id, "policy_id"))
          : [];
        if (!name || policyIds.length === 0) {
          return NextResponse.json(
            {
              error:
                "Baseline name and at least one reviewed policy_id are required.",
            },
            { status: 400 }
          );
        }
        targetPath = "/v1/enterprise/baselines";
        method = "POST";
        bodyPayload = {
          name,
          description:
            typeof input.description === "string" && input.description.trim()
              ? input.description.trim()
              : undefined,
          policy_ids: policyIds,
          version:
            typeof input.version === "string" && input.version.trim()
              ? input.version.trim()
              : "1.0.0",
          status: "active",
        };
        break;
      }

      case "list_baselines": {
        targetPath = "/v1/enterprise/baselines";
        method = "GET";
        break;
      }

      case "get_baseline": {
        const baselineId = assertSafeId(input.baseline_id, "baseline_id");
        targetPath = `/v1/enterprise/baselines/${encodeURIComponent(baselineId)}`;
        method = "GET";
        break;
      }

      case "get_report": {
        const assessmentId = assertSafeId(
          input.assessment_id,
          "assessment_id"
        );
        targetPath = `/v1/assessments/${encodeURIComponent(assessmentId)}/report`;
        method = "GET";
        break;
      }

      case "get_gaps": {
        const assessmentId = assertSafeId(
          input.assessment_id,
          "assessment_id"
        );
        targetPath = `/v1/assessments/${encodeURIComponent(assessmentId)}/gaps`;
        method = "GET";
        break;
      }

      default:
        return NextResponse.json(
          { error: "Unsupported workspace action." },
          { status: 400 }
        );
    }
  } catch (err) {
    return NextResponse.json(
      {
        error:
          err instanceof Error ? err.message : "Invalid workspace parameters.",
      },
      { status: 400 }
    );
  }

  try {
    const response = await fetch(`${baseUrl}${targetPath}`, {
      method,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
      headers: backendHeaders(ctx),
      ...(bodyPayload !== undefined
        ? { body: JSON.stringify(bodyPayload) }
        : {}),
    });

    if (!response.ok) {
      let detail = "The workspace operation was rejected by the backend API.";
      try {
        const errBody = await response.json();
        if (typeof errBody?.detail === "string" && errBody.detail.length < 300) {
          detail = errBody.detail;
        }
      } catch {
        // Ignore non-JSON upstream bodies so internal stack traces never leak
      }
      if (response.status >= 500 && response.status !== 501) {
        detail = "The backend analysis service is temporarily unavailable.";
      }
      return NextResponse.json(
        { error: detail, detail },
        { status: response.status }
      );
    }

    return NextResponse.json(await response.json(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        error:
          "Could not reach the backend API. Start the backend server or verify configuration.",
      },
      { status: 502 }
    );
  }
}
