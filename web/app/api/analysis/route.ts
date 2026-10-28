import { NextResponse } from "next/server";

const MAX_PUBLIC_BYTES = 1_000_000;

export async function POST(request: Request) {
  let input: Record<string, unknown>;
  try {
    const reader = request.body?.getReader();
    if (!reader)
      return NextResponse.json(
        { error: "A JSON body is required." },
        { status: 400 },
      );
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_PUBLIC_BYTES) {
        await reader.cancel();
        return NextResponse.json(
          { error: "Public demo request exceeds 1 MB." },
          { status: 413 },
        );
      }
      chunks.push(value);
    }
    input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (
      !input ||
      Array.isArray(input) ||
      typeof input !== "object" ||
      !input.use_case ||
      Array.isArray(input.use_case) ||
      typeof input.use_case !== "object"
    ) {
      return NextResponse.json(
        { error: "An inline use_case object is required." },
        { status: 400 },
      );
    }
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON request." },
      { status: 400 },
    );
  }
  const kind = input.kind;
  if (kind !== "coverage" && kind !== "policy-gaps") {
    return NextResponse.json(
      { error: "Choose coverage or policy-gaps." },
      { status: 400 },
    );
  }
  const payload: Record<string, unknown> = {
    use_case: input.use_case,
    questionnaire_pack: "DEMO_BANKING_V1",
    persist: false,
  };
  if (kind === "policy-gaps") {
    if (
      typeof input.policy_text !== "string" ||
      !input.policy_text.trim() ||
      input.policy_text.length > 250_000
    ) {
      return NextResponse.json(
        { error: "Provide a policy excerpt of 1–250,000 characters." },
        { status: 400 },
      );
    }
    payload.policy_text = input.policy_text;
    payload.policy_name = "User-supplied policy excerpt";
  }
  try {
    const response = await fetch(
      `${process.env.CROSSWALK_API_URL || "http://127.0.0.1:8000"}/v1/assessments/${kind}`,
      {
        method: "POST",
        cache: "no-store",
        signal: AbortSignal.timeout(20_000),
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-ID":
            process.env.BANKING_CROSSWALK_TENANT_ID || "public-demo",
          ...(process.env.CROSSWALK_API_KEY
            ? { "X-API-Key": process.env.CROSSWALK_API_KEY }
            : {}),
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) {
      const error =
        response.status === 422
          ? "The API rejected the use-case fields or policy text."
          : response.status === 401 || response.status === 403
            ? "The API gateway authentication is not configured correctly."
            : "The analysis API is temporarily unavailable.";
      return NextResponse.json({ error }, { status: response.status });
    }
    return NextResponse.json(await response.json(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        error:
          "Could not reach the analysis API. Start the backend or check server configuration.",
      },
      { status: 502 },
    );
  }
}
