import { getResultKind } from "../utils";

function cardClass(kind) {
  if (kind === "verified") {
    return "border-emerald-400/30 bg-emerald-500/10 text-emerald-50";
  }
  if (kind === "timeout") {
    return "border-amber-300/30 bg-amber-500/10 text-amber-50";
  }
  if (kind === "failed") {
    return "border-red-400/30 bg-red-500/10 text-red-50";
  }
  return "border-white/10 bg-white/5 text-white";
}

function buildHeadline(kind) {
  if (kind === "verified") {
    return "✅ Verified";
  }
  if (kind === "timeout") {
    return "⏱ Timed out";
  }
  if (kind === "failed") {
    return "❌ Verification failed";
  }
  return "Awaiting verification";
}

function buildBody(job, kind, toolCallCount) {
  if (kind === "verified") {
    return "The Lean 4 kernel has accepted this proof from axioms. This is mathematical certainty, not LLM confidence.";
  }
  if (kind === "timeout") {
    return `Partial proof available. ${toolCallCount} tool calls were used before the run timed out at ${job?.result?.last_stage || "an unknown stage"}.`;
  }
  if (kind === "failed") {
    return job?.error || job?.result?.compile?.errors?.[0] || "The prover did not close the theorem.";
  }
  return "Queue a theorem review to see the final Lean verdict here.";
}

export default function ResultCard({
  job,
  toolCallCount,
  explanation,
  explanationOpen,
  onToggleExplanation,
  onExplain,
  onRetry,
  busy,
}) {
  const kind = getResultKind(job);
  const terminal = kind === "verified" || kind === "timeout" || kind === "failed";

  return (
    <div className={`fade-in rounded-3xl border p-4 ${cardClass(kind)}`}>
      <div className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-[0.12em]">Result</p>
        <h3 className="text-xl font-semibold">{buildHeadline(kind)}</h3>
        <p className="text-sm leading-6">{buildBody(job, kind, toolCallCount)}</p>
      </div>

      {terminal ? (
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              if (explanation) {
                onToggleExplanation(!explanationOpen);
                return;
              }
              onExplain();
            }}
            disabled={busy}
          >
            {explanation ? (explanationOpen ? "Hide Explanation" : "Explain") : busy ? "Loading..." : "Explain"}
          </button>
          <button type="button" className="secondary-button" onClick={onRetry} disabled={busy}>
            Retry
          </button>
        </div>
      ) : null}

      {explanationOpen && explanation ? (
        <div className="mt-4 rounded-2xl border border-white/10 bg-black/15 px-4 py-4 text-sm leading-6 text-white">
          {explanation}
        </div>
      ) : null}
    </div>
  );
}
