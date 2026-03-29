import ResultCard from "./ResultCard";
import Timeline from "./Timeline";

export default function ProgressPanel({
  workflowState,
  timelineSteps,
  streamConnected,
  streamError,
  job,
  toolCallCount,
  explanation,
  explanationOpen,
  onToggleExplanation,
  onExplain,
  onRetry,
  busy,
}) {
  return (
    <section className="panel flex h-full flex-col gap-4">
      <div>
        <p className="panel-title">Panel C</p>
        <h2 className="mt-2 text-xl font-semibold">Progress</h2>
        <p className="mt-1 text-sm subtle-text">
          State: {workflowState.replace(/_/g, " ")}
        </p>
      </div>

      <Timeline steps={timelineSteps} connected={streamConnected} error={streamError} />

      <ResultCard
        job={job}
        toolCallCount={toolCallCount}
        explanation={explanation}
        explanationOpen={explanationOpen}
        onToggleExplanation={onToggleExplanation}
        onExplain={onExplain}
        onRetry={onRetry}
        busy={busy}
      />
    </section>
  );
}
