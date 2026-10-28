"use client";

import { useState } from "react";
import {
  Assessment,
  Fact,
  FactKey,
  buildPayload,
  emptyFacts,
  factLabels,
  gapsFor,
  parseFact,
} from "./analysis";

export default function Home() {
  const [name, setName] = useState("Dispute and Refund Agent");
  const [facts, setFacts] = useState({ ...emptyFacts });
  const [threshold, setThreshold] = useState("");
  const [kind, setKind] = useState<"coverage" | "policy-gaps">("coverage");
  const [policy, setPolicy] = useState(
    "All refunds above AUD 500 require human approval before payment execution. Approval logs must be retained.",
  );
  const [result, setResult] = useState<Assessment | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function updateFact(key: FactKey, value: Fact) {
    setFacts((current) => ({ ...current, [key]: value }));
    setResult(null);
  }
  function loadExample() {
    setFacts({
      ...emptyFacts,
      apra_regulated: true,
      handles_personal_information: true,
      handles_regulated_complaints: true,
      makes_or_assists_significant_decisions: true,
      third_party_ai_service: true,
      nist_ai_rmf_adopted: true,
    });
    setName("Example Australian bank refund agent");
    setThreshold("500");
    setResult(null);
  }
  async function analyze() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const payload = buildPayload(name, facts, threshold);
      const response = await fetch("/api/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payload,
          kind,
          ...(kind === "policy-gaps" ? { policy_text: policy } : {}),
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

  const gaps = result ? gapsFor(result) : [];
  return (
    <main>
      <nav>
        <a className="brand" href="/">
          DeepAudit<span>CrossWalk</span>
        </a>
        <a
          href="https://github.com/VivianFuVivianFu/DeepAuditCrossWalk"
          target="_blank"
          rel="noreferrer"
        >
          GitHub ↗
        </a>
      </nav>
      <header>
        <p className="eyebrow">AUSTRALIAN BANKING · OPEN SOURCE MVP</p>
        <h1>
          Find the requirements
          <br />
          your assessment misses.
        </h1>
        <p className="lead">
          Connect applicable obligations, enterprise policies, assessment
          questions and evidence. Make every gap reviewable.
        </p>
      </header>
      <aside className="notice">
        <strong>Demonstration workspace.</strong> This release uses 19 original
        synthetic questions and proposed regulatory interpretations. Import an
        authorised AIAF workbook through the API for its full question bank.
        Assessment coverage and legal compliance are separate conclusions.
      </aside>
      <section className="workspace">
        <div className="panel">
          <div className="section-title">
            <div>
              <p className="eyebrow">01 / CONTEXT</p>
              <h2>Your AI use case</h2>
            </div>
            <button className="quiet" onClick={loadExample} disabled={busy}>
              Load example
            </button>
          </div>
          <fieldset disabled={busy}>
            <label>
              Use case name
              <input
                maxLength={200}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
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
                      updateFact(key as FactKey, parseFact(e.target.value))
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
          <p className="muted">
            Unknown facts remain undetermined. The presence of a supplier does
            not establish its materiality or an IDR duty.
          </p>
        </div>
        <div className="panel">
          <p className="eyebrow">02 / ASSESSMENT</p>
          <h2>Choose an analysis</h2>
          <div className="tabs" role="group" aria-label="Assessment type">
            <button
              disabled={busy}
              className={kind === "coverage" ? "active" : ""}
              onClick={() => {
                setKind("coverage");
                setResult(null);
              }}
            >
              Questionnaire coverage
            </button>
            <button
              disabled={busy}
              className={kind === "policy-gaps" ? "active" : ""}
              onClick={() => {
                setKind("policy-gaps");
                setResult(null);
              }}
            >
              Enterprise policy gaps
            </button>
          </div>
          {kind === "coverage" ? (
            <p>
              Evaluate the selected facts against the shared obligation library.
              Candidate mappings remain provisional until an authorised reviewer
              approves them.
            </p>
          ) : (
            <label>
              Policy excerpt
              <textarea
                disabled={busy}
                rows={9}
                maxLength={250000}
                value={policy}
                onChange={(e) => {
                  setPolicy(e.target.value);
                  setResult(null);
                }}
              />
              <small>
                Use synthetic or authorised excerpts. This web demo does not
                persist assessments; the configured server still processes
                submitted text.
              </small>
            </label>
          )}
          <button
            className="primary"
            disabled={busy || (kind === "policy-gaps" && !policy.trim())}
            onClick={analyze}
          >
            {busy ? "Assessing…" : "Run assessment →"}
          </button>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="chain">
            Obligation → Control → Question → Evidence → Review
          </div>
        </div>
      </section>
      {result && (
        <section className="results" aria-live="polite">
          <div className="section-title">
            <div>
              <p className="eyebrow">03 / FINDINGS</p>
              <h2>Traceable assessment results</h2>
            </div>
            <button onClick={download}>Export JSON ↓</button>
          </div>
          <p className="muted">
            Assessment {result.assessment_id} · Regulatory pack{" "}
            {result.regulatory_pack_version} ·{" "}
            {new Date(result.created_at).toLocaleString()}
          </p>
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
          <h3>Gaps and remediation ({gaps.length})</h3>
          {gaps.map((gap) => (
            <details key={gap.gap_id}>
              <summary>
                <span>
                  <strong>{gap.title}</strong>
                  <small>{gap.gap_type.replaceAll("_", " ")}</small>
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
