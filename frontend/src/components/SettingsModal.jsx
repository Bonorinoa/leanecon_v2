import { useEffect, useState } from "react";

export default function SettingsModal({
  isOpen,
  settings,
  provider,
  health,
  onClose,
  onSave,
  onTestConnection,
  testingConnection,
  testResult,
}) {
  const [draftApiUrl, setDraftApiUrl] = useState(settings.apiUrl);
  const [draftTimeout, setDraftTimeout] = useState(settings.timeout);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setDraftApiUrl(settings.apiUrl);
    setDraftTimeout(settings.timeout);
  }, [isOpen, settings.apiUrl, settings.timeout]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
      <div className="panel w-full max-w-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="panel-title">Settings</p>
            <h2 className="mt-2 text-xl font-semibold">Connection and runtime</h2>
          </div>
          <button type="button" className="secondary-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="mt-6 space-y-5">
          <div className="space-y-2">
            <label className="text-sm font-medium subtle-text" htmlFor="api-url">
              API URL
            </label>
            <input
              id="api-url"
              className="input-shell"
              value={draftApiUrl}
              onChange={(event) => setDraftApiUrl(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium subtle-text" htmlFor="timeout-slider">
                Max timeout
              </label>
              <span className="text-sm font-semibold">{draftTimeout}s</span>
            </div>
            <input
              id="timeout-slider"
              type="range"
              min="60"
              max="600"
              step="30"
              value={draftTimeout}
              onChange={(event) => setDraftTimeout(Number(event.target.value))}
              className="w-full"
            />
          </div>

          <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm subtle-text md:grid-cols-2">
            <p>Provider: {provider || "unknown"}</p>
            <p>Lean available: {health?.lean_available ? "yes" : "no"}</p>
            <p>Status: {health?.status || "unknown"}</p>
            <p>Version: {health?.version || "unknown"}</p>
          </div>

          {testResult ? (
            <div
              className={`rounded-2xl border px-4 py-3 text-sm ${
                testResult.ok
                  ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
                  : "border-red-400/30 bg-red-500/10 text-red-100"
              }`}
            >
              {testResult.message}
            </div>
          ) : null}
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              onTestConnection({
                apiUrl: draftApiUrl,
                timeout: draftTimeout,
              })
            }
            disabled={testingConnection}
          >
            {testingConnection ? "Testing..." : "Test Connection"}
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() =>
              onSave({
                apiUrl: draftApiUrl.trim() || settings.apiUrl,
                timeout: draftTimeout,
              })
            }
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
}
