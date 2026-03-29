export default function Header({ connected, provider, version, activeTab, onTabChange, onOpenSettings }) {
  return (
    <header className="panel flex flex-col gap-4">
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
        <div className="space-y-2">
          <p className="panel-title">LeanEcon v2 Analytics</p>
          <div>
            <h1 className="text-2xl font-semibold md:text-3xl tracking-tight text-slate-800">
              Formal Verification for Economics
            </h1>
            <p className="mt-1 text-sm subtle-text md:text-base">
              Experience the stochastic-to-deterministic workflow with human review in the loop.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 bg-slate-50 p-1.5 rounded-2xl border border-slate-200">
          <button
            type="button"
            onClick={() => onTabChange("demo")}
            className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-200 ${
              activeTab === "demo"
                ? "bg-white text-blue-600 shadow-sm ring-1 ring-slate-200/50"
                : "text-slate-500 hover:text-slate-700 hover:bg-slate-100/50"
            }`}
          >
            Live Demo
          </button>
          <button
            type="button"
            onClick={() => onTabChange("benchmarks")}
            className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-200 ${
              activeTab === "benchmarks"
                ? "bg-white text-blue-600 shadow-sm ring-1 ring-slate-200/50"
                : "text-slate-500 hover:text-slate-700 hover:bg-slate-100/50"
            }`}
          >
            Benchmarks
          </button>
        </div>
      </div>

      <div className="h-px w-full bg-slate-100 my-2"></div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-3">
          <div className="badge bg-slate-50 text-slate-600 border-slate-200">
            <span
              className={`status-dot mr-2 ${
                connected ? "status-dot-success" : "status-dot-error"
              }`}
            />
            {connected ? "API Connected" : "API Disconnected"}
          </div>

          <div className="badge bg-slate-50 text-slate-600 border-slate-200">
            Provider: {provider || "unknown"}
          </div>

          <div className="badge bg-slate-50 text-slate-600 border-slate-200">
            Version: {version || "unknown"}
          </div>
        </div>

        <button type="button" className="secondary-button !py-1.5 !text-xs" onClick={onOpenSettings}>
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinelinejoin="round" className="mr-2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg>
          Settings
        </button>
      </div>
    </header>
  );
}
