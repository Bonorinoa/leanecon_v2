import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import Header from "./components/Header";
import HistoryBar from "./components/HistoryBar";
import InputPanel from "./components/InputPanel";
import ProgressPanel from "./components/ProgressPanel";
import SettingsModal from "./components/SettingsModal";
import TheoremPanel from "./components/TheoremPanel";
import EvalDashboard from "./pages/EvalDashboard";
import { useVerification } from "./hooks/useVerification";
import { DEFAULT_API_URL, DEFAULT_TIMEOUT, ensureTrailingSlash } from "./utils";

const SETTINGS_STORAGE_KEY = "leanecon-demo-settings";

function historyReducer(state, action) {
  if (action.type === "upsert") {
    const merged = [action.entry, ...state.filter((entry) => entry.id !== action.entry.id)];
    merged.sort((left, right) => {
      const leftTs = new Date(left.updatedAt || 0).getTime();
      const rightTs = new Date(right.updatedAt || 0).getTime();
      return rightTs - leftTs;
    });
    return merged.slice(0, 8);
  }

  return state;
}

function readInitialSettings() {
  if (typeof window === "undefined") {
    return { apiUrl: DEFAULT_API_URL, timeout: DEFAULT_TIMEOUT };
  }

  try {
    const saved = window.sessionStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!saved) {
      return { apiUrl: DEFAULT_API_URL, timeout: DEFAULT_TIMEOUT };
    }

    const parsed = JSON.parse(saved);
    return {
      apiUrl: parsed.apiUrl || DEFAULT_API_URL,
      timeout: Number(parsed.timeout) || DEFAULT_TIMEOUT,
    };
  } catch {
    return { apiUrl: DEFAULT_API_URL, timeout: DEFAULT_TIMEOUT };
  }
}

async function fetchHealth(apiUrl) {
  const response = await fetch(new URL("/health", ensureTrailingSlash(apiUrl)).toString());
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { detail: await response.text() };

  if (!response.ok) {
    throw new Error(payload?.detail || "Unable to reach the API health endpoint.");
  }

  return payload;
}

export default function App() {
  const [activeTab, setActiveTab] = useState("demo");
  const [settings, setSettings] = useState(readInitialSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [historyEntries, dispatchHistory] = useReducer(historyReducer, []);
  const [activeHistoryId, setActiveHistoryId] = useState(null);

  const handleAttemptChange = useCallback((entry) => {
    dispatchHistory({ type: "upsert", entry });
    setActiveHistoryId(entry.id);
  }, []);

  const verification = useVerification({
    apiUrl: settings.apiUrl,
    timeout: settings.timeout,
    onAttemptChange: handleAttemptChange,
  });

  useEffect(() => {
    window.sessionStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    let cancelled = false;

    fetchHealth(settings.apiUrl)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setHealth(payload);
        setHealthError("");
      })
      .catch((errorValue) => {
        if (cancelled) {
          return;
        }
        const message =
          errorValue instanceof Error ? errorValue.message : "Unable to check API health.";
        setHealth(null);
        setHealthError(message);
      });

    return () => {
      cancelled = true;
    };
  }, [settings.apiUrl]);

  const preambleSuggestions = useMemo(() => {
    const matches = verification.searchContext?.preambleMatches || [];
    return [...new Set(matches.map((match) => match.name).filter(Boolean))];
  }, [verification.searchContext]);

  const handleSaveSettings = useCallback((nextSettings) => {
    setSettings(nextSettings);
    setSettingsOpen(false);
    setTestResult(null);
  }, []);

  const handleTestConnection = useCallback(async (draftSettings) => {
    setTestingConnection(true);
    try {
      const payload = await fetchHealth(draftSettings.apiUrl);
      setTestResult({
        ok: true,
        message: `Connected to ${draftSettings.apiUrl} with provider ${payload.driver}.`,
      });
    } catch (errorValue) {
      const message =
        errorValue instanceof Error ? errorValue.message : "Connection test failed.";
      setTestResult({
        ok: false,
        message,
      });
    } finally {
      setTestingConnection(false);
    }
  }, []);

  const handleSelectHistory = useCallback(
    (entry) => {
      setActiveHistoryId(entry.id);
      verification.restoreSnapshot(entry);
    },
    [verification],
  );

  const globalError = verification.error || healthError;

  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 px-4 py-6 md:px-6">
      <Header
        connected={Boolean(health) && !healthError}
        provider={health?.driver}
        version={health?.version}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {globalError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-800 shadow-sm">
          {globalError}
        </div>
      ) : null}

      {activeTab === "demo" ? (
        <>
          <main className="grid flex-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,0.9fr)]">
            <InputPanel
              mode={verification.mode}
              onModeChange={verification.setMode}
              claimText={verification.claimText}
              onClaimTextChange={verification.setClaimText}
              selectedPreamble={verification.selectedPreamble}
              onSelectedPreambleChange={verification.setSelectedPreamble}
              preambleSuggestions={preambleSuggestions}
              onSearch={verification.searchClaim}
              onRunPipeline={verification.runPipeline}
              busy={verification.isBusy}
              workflowState={verification.workflowState}
            />

            <TheoremPanel
              theoremText={verification.theoremText}
              onTheoremTextChange={verification.setTheoremText}
              displayScope={verification.displayScope}
              integrityWarnings={verification.integrityWarnings}
              searchContext={verification.searchContext}
              formalizeResponse={verification.formalizeResponse}
              onApprove={verification.approveAndVerify}
              busy={verification.isBusy}
            />

            <ProgressPanel
              workflowState={verification.workflowState}
              timelineSteps={verification.timelineSteps}
              streamConnected={verification.streamConnected}
              streamError={verification.streamError}
              job={verification.job}
              toolCallCount={verification.toolCallCount}
              explanation={verification.explanation}
              explanationOpen={verification.explanationOpen}
              onToggleExplanation={verification.setExplanationOpen}
              onExplain={verification.requestExplanation}
              onRetry={verification.retryVerification}
              busy={verification.isBusy}
            />
          </main>

          <HistoryBar entries={historyEntries} activeId={activeHistoryId} onSelect={handleSelectHistory} />
        </>
      ) : (
        <main className="flex-1 w-full bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
          <EvalDashboard />
        </main>
      )}

      <SettingsModal
        isOpen={settingsOpen}
        settings={settings}
        provider={health?.driver}
        health={health}
        onClose={() => {
          setSettingsOpen(false);
          setTestResult(null);
        }}
        onSave={handleSaveSettings}
        onTestConnection={handleTestConnection}
        testingConnection={testingConnection}
        testResult={testResult}
      />
    </div>
  );
}
