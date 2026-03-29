export default function Header({ connected, provider, version, onOpenSettings }) {
  return (
    <header className="panel flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
      <div className="space-y-2">
        <p className="panel-title">LeanEcon v2 Demo</p>
        <div>
          <h1 className="text-2xl font-semibold md:text-3xl">
            Formal Verification for Economics
          </h1>
          <p className="mt-1 text-sm subtle-text md:text-base">
            Experience the stochastic-to-deterministic workflow with human review in the loop.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="badge border border-white/10 bg-white/5">
          <span
            className={`status-dot mr-2 ${
              connected ? "status-dot-success" : "status-dot-error"
            }`}
          />
          {connected ? "API Connected" : "API Disconnected"}
        </div>

        <div className="badge border border-white/10 bg-white/5">
          Provider: {provider || "unknown"}
        </div>

        <div className="badge border border-white/10 bg-white/5">
          Version: {version || "unknown"}
        </div>

        <button type="button" className="secondary-button" onClick={onOpenSettings}>
          Settings
        </button>
      </div>
    </header>
  );
}
