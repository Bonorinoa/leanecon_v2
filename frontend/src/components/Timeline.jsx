function dotClass(status) {
  if (status === "complete") {
    return "status-dot status-dot-success";
  }
  if (status === "active") {
    return "status-dot status-dot-active";
  }
  if (status === "warning") {
    return "status-dot status-dot-warning";
  }
  if (status === "error") {
    return "status-dot status-dot-error";
  }
  return "status-dot status-dot-pending";
}

export default function Timeline({ steps, connected, error }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm">
        <span className="font-medium">Progress Timeline</span>
        <span className={connected ? "text-emerald-300" : "subtle-text"}>
          {connected ? "Live stream connected" : error || "Waiting for stream"}
        </span>
      </div>

      <div className="space-y-4">
        {steps.map((step) => (
          <div key={step.id} className="flex gap-4">
            <div className="flex flex-col items-center">
              <span className={dotClass(step.status)} />
              {step.id !== steps[steps.length - 1].id ? (
                <span className="mt-2 h-full w-px bg-white/10" />
              ) : null}
            </div>

            <div className="pb-4">
              <p className="text-sm font-semibold">{step.label}</p>
              <p className="mt-1 text-xs subtle-text">{step.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
