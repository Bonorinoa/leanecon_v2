import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useApi } from "./useApi";
import { useSSE } from "./useSSE";
import {
  buildTimelineSteps,
  deriveIntegrityWarnings,
  getApiUrl,
  getDisplayScope,
  getLatestProgress,
  getResultKind,
  getToolCallCount,
  isTerminalStatus,
  normalizeSearchContext,
} from "../utils";

function buildQueuedJob(jobId) {
  const timestamp = new Date().toISOString();
  return {
    id: jobId,
    status: "queued",
    created_at: timestamp,
    updated_at: timestamp,
    result: null,
    error: null,
  };
}

function mergeProgress(job, event) {
  const baseline = job || buildQueuedJob(event.jobId || "pending-job");
  const progress = {
    ...(baseline.result?.progress || {}),
    ...(event.payload || {}),
    ...(event.stage ? { stage: event.stage } : {}),
    ...(event.status ? { status: event.status } : {}),
  };

  return {
    ...baseline,
    status: event.status || baseline.status,
    updated_at: new Date().toISOString(),
    result: {
      ...(baseline.result || {}),
      progress,
    },
    error: event.error || baseline.error,
  };
}

export function useVerification({ apiUrl, timeout, onAttemptChange }) {
  const api = useApi(apiUrl);
  const [workflowState, setWorkflowState] = useState("idle");
  const [mode, setMode] = useState("nl");
  const [claimText, setClaimText] = useState("");
  const [selectedPreamble, setSelectedPreamble] = useState("");
  const [searchResponse, setSearchResponse] = useState(null);
  const [formalizeResponse, setFormalizeResponse] = useState(null);
  const [theoremText, setTheoremText] = useState("");
  const [job, setJob] = useState(null);
  const [explanation, setExplanation] = useState("");
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [storedToolCallCount, setStoredToolCallCount] = useState(0);
  const [localError, setLocalError] = useState("");

  const streamUrl = useMemo(() => {
    if (!job?.id || isTerminalStatus(job.status)) {
      return null;
    }
    return getApiUrl(apiUrl, `/api/v2/jobs/${job.id}/stream`);
  }, [apiUrl, job?.id, job?.status]);

  const { events, connected: streamConnected, error: streamError } = useSSE(streamUrl, {
    enabled: Boolean(streamUrl) && (workflowState === "verifying" || workflowState === "streaming"),
  });

  const terminalHydrationRef = useRef(new Set());
  const lastProcessedEventRef = useRef(0);
  const attemptSnapshotRef = useRef(null);

  const searchContext = useMemo(
    () => normalizeSearchContext(searchResponse, formalizeResponse),
    [formalizeResponse, searchResponse],
  );

  const toolCallCount = useMemo(
    () => getToolCallCount(events, job, storedToolCallCount),
    [events, job, storedToolCallCount],
  );
  const progress = useMemo(() => getLatestProgress(events, job), [events, job]);
  const displayScope = useMemo(
    () => getDisplayScope({ theoremText, formalizeResponse, mode }),
    [formalizeResponse, mode, theoremText],
  );
  const integrityWarnings = useMemo(
    () =>
      deriveIntegrityWarnings({
        mode,
        claimText,
        theoremText,
        formalizeResponse,
      }),
    [claimText, formalizeResponse, mode, theoremText],
  );
  const timelineSteps = useMemo(
    () =>
      buildTimelineSteps({
        workflowState,
        job,
        progress,
        toolCallCount,
      }),
    [job, progress, toolCallCount, workflowState],
  );

  const publishHistory = useCallback(
    (jobSnapshot, explanationText = explanation, toolCalls = toolCallCount) => {
      if (!onAttemptChange || !jobSnapshot?.id) {
        return;
      }

      const snapshot = attemptSnapshotRef.current || {
        mode,
        claimText,
        selectedPreamble,
        searchResponse,
        formalizeResponse,
        theoremText,
      };

      onAttemptChange({
        id: jobSnapshot.id,
        mode: snapshot.mode,
        claimText: snapshot.claimText,
        selectedPreamble: snapshot.selectedPreamble,
        searchResponse: snapshot.searchResponse,
        formalizeResponse: snapshot.formalizeResponse,
        theoremText: snapshot.theoremText,
        job: jobSnapshot,
        explanation: explanationText,
        toolCallCount: toolCalls,
        updatedAt: new Date().toISOString(),
      });
    },
    [
      claimText,
      explanation,
      formalizeResponse,
      mode,
      onAttemptChange,
      searchResponse,
      selectedPreamble,
      theoremText,
      toolCallCount,
    ],
  );

  const clearRunState = useCallback(() => {
    attemptSnapshotRef.current = null;
    setSearchResponse(null);
    setFormalizeResponse(null);
    setTheoremText("");
    setJob(null);
    setExplanation("");
    setExplanationOpen(false);
    setStoredToolCallCount(0);
    setLocalError("");
    terminalHydrationRef.current = new Set();
    lastProcessedEventRef.current = 0;
  }, []);

  const hydrateTerminalJob = useCallback(
    async (jobId) => {
      if (!jobId || terminalHydrationRef.current.has(jobId)) {
        return;
      }
      terminalHydrationRef.current.add(jobId);

      try {
        const terminalJob = await api.call(`/api/v2/jobs/${jobId}`);
        setJob(terminalJob);
        setWorkflowState("done");
        const terminalToolCalls = getToolCallCount(events, terminalJob, storedToolCallCount);
        setStoredToolCallCount(terminalToolCalls);
        publishHistory(terminalJob, explanation, terminalToolCalls);
      } catch (errorValue) {
        const message =
          errorValue instanceof Error ? errorValue.message : "Unable to hydrate final job state.";
        setLocalError(message);
        setWorkflowState("error");
      }
    },
    [api, events, explanation, publishHistory, storedToolCallCount],
  );

  useEffect(() => {
    if (events.length === 0) {
      lastProcessedEventRef.current = 0;
      return;
    }
    if (events.length < lastProcessedEventRef.current) {
      lastProcessedEventRef.current = 0;
    }

    const pendingEvents = events.slice(lastProcessedEventRef.current);
    lastProcessedEventRef.current = events.length;

    pendingEvents.forEach((event) => {
      if (event.type === "snapshot" && event.job) {
        setJob(event.job);
        const snapshotToolCalls = Array.isArray(event.job.result?.tool_history)
          ? event.job.result.tool_history.length
          : 0;
        setStoredToolCallCount((previous) => Math.max(previous, snapshotToolCalls));
        setWorkflowState(isTerminalStatus(event.job.status) ? "done" : "streaming");
        if (isTerminalStatus(event.job.status)) {
          publishHistory(event.job, explanation, snapshotToolCalls);
        }
        return;
      }

      if (event.type === "start" || event.type === "progress") {
        setWorkflowState("streaming");
        setJob((previous) => mergeProgress(previous, event));
        return;
      }

      if (event.type === "complete") {
        setWorkflowState("streaming");
        hydrateTerminalJob(event.jobId || job?.id);
      }
    });
  }, [events, explanation, hydrateTerminalJob, job?.id, publishHistory]);

  const searchClaim = useCallback(async () => {
    const rawClaim = claimText.trim();
    if (!rawClaim) {
      setLocalError("Enter a claim before running search.");
      return null;
    }

    clearRunState();
    setWorkflowState("searching");

    try {
      const response = await api.call("/api/v2/search", {
        method: "POST",
        body: { raw_claim: rawClaim },
      });
      setSearchResponse(response);
      setWorkflowState("idle");
      return response;
    } catch (errorValue) {
      const message =
        errorValue instanceof Error ? errorValue.message : "Search request failed.";
      setLocalError(message);
      setWorkflowState("error");
      return null;
    }
  }, [api, claimText, clearRunState]);

  const runPipeline = useCallback(async () => {
    const rawClaim = claimText.trim();
    if (!rawClaim) {
      setLocalError("Enter a claim before running the verification pipeline.");
      return null;
    }

    clearRunState();
    setWorkflowState("searching");

    try {
      const searchPayload = await api.call("/api/v2/search", {
        method: "POST",
        body: { raw_claim: rawClaim },
      });
      setSearchResponse(searchPayload);

      setWorkflowState("formalizing");
      const formalizePayload = await api.call("/api/v2/formalize", {
        method: "POST",
        body: {
          raw_claim: rawClaim,
          ...(selectedPreamble.trim()
            ? { preamble_names: [selectedPreamble.trim()] }
            : {}),
        },
      });

      setFormalizeResponse(formalizePayload);
      setTheoremText(formalizePayload.theorem_code || "");

      if (formalizePayload.theorem_code) {
        setWorkflowState("reviewing");
      } else {
        setWorkflowState("error");
        setLocalError(
          formalizePayload.message ||
            formalizePayload.errors?.[0] ||
            "Formalization did not produce a theorem for review.",
        );
      }

      return formalizePayload;
    } catch (errorValue) {
      const message =
        errorValue instanceof Error ? errorValue.message : "Pipeline request failed.";
      setLocalError(message);
      setWorkflowState("error");
      return null;
    }
  }, [api, claimText, clearRunState, selectedPreamble]);

  const approveAndVerify = useCallback(async () => {
    const theoremWithSorry = theoremText.trim();
    if (!theoremWithSorry) {
      setLocalError("No theorem is available to verify.");
      return null;
    }
    if (!theoremWithSorry.includes("sorry")) {
      setLocalError("Verification requires a theorem stub that still contains `sorry`.");
      return null;
    }

    setLocalError("");
    setExplanation("");
    setExplanationOpen(false);
    setStoredToolCallCount(0);
    setWorkflowState("verifying");
    attemptSnapshotRef.current = {
      mode,
      claimText,
      selectedPreamble,
      searchResponse,
      formalizeResponse,
      theoremText: theoremWithSorry,
    };

    try {
      const response = await api.call("/api/v2/verify", {
        method: "POST",
        body: {
          theorem_with_sorry: theoremWithSorry,
          timeout,
        },
      });

      const queuedJob = buildQueuedJob(response.job_id);
      setJob(queuedJob);
      publishHistory(queuedJob, "", 0);
      return response;
    } catch (errorValue) {
      const message =
        errorValue instanceof Error ? errorValue.message : "Unable to queue verification.";
      setLocalError(message);
      setWorkflowState("error");
      return null;
    }
  }, [
    api,
    claimText,
    formalizeResponse,
    mode,
    publishHistory,
    searchResponse,
    selectedPreamble,
    theoremText,
    timeout,
  ]);

  const retryVerification = useCallback(async () => approveAndVerify(), [approveAndVerify]);

  const requestExplanation = useCallback(async () => {
    if (!job?.result) {
      setLocalError("A finished verification result is required before generating an explanation.");
      return null;
    }

    try {
      const response = await api.call("/api/v2/explain", {
        method: "POST",
        body: { verification_result: job.result },
      });
      setExplanation(response.explanation);
      setExplanationOpen(true);
      publishHistory(job, response.explanation, toolCallCount);
      return response.explanation;
    } catch (errorValue) {
      const message =
        errorValue instanceof Error ? errorValue.message : "Unable to explain this verification.";
      setLocalError(message);
      return null;
    }
  }, [api, job, publishHistory, toolCallCount]);

  const reset = useCallback(() => {
    setSearchResponse(null);
    clearRunState();
    setWorkflowState("idle");
  }, [clearRunState]);

  const restoreSnapshot = useCallback((entry) => {
    attemptSnapshotRef.current = {
      mode: entry.mode || "nl",
      claimText: entry.claimText || "",
      selectedPreamble: entry.selectedPreamble || "",
      searchResponse: entry.searchResponse || null,
      formalizeResponse: entry.formalizeResponse || null,
      theoremText: entry.theoremText || "",
    };
    setMode(entry.mode || "nl");
    setClaimText(entry.claimText || "");
    setSelectedPreamble(entry.selectedPreamble || "");
    setSearchResponse(entry.searchResponse || null);
    setFormalizeResponse(entry.formalizeResponse || null);
    setTheoremText(entry.theoremText || "");
    setJob(entry.job || null);
    setExplanation(entry.explanation || "");
    setExplanationOpen(Boolean(entry.explanation));
    setStoredToolCallCount(entry.toolCallCount || 0);
    setLocalError("");
    terminalHydrationRef.current = new Set();
    lastProcessedEventRef.current = 0;

    if (entry.job && !isTerminalStatus(entry.job.status)) {
      setWorkflowState("streaming");
      return;
    }

    if (entry.job && isTerminalStatus(entry.job.status)) {
      setWorkflowState("done");
      return;
    }

    if (entry.theoremText) {
      setWorkflowState("reviewing");
      return;
    }

    setWorkflowState("idle");
  }, []);

  return {
    mode,
    setMode,
    claimText,
    setClaimText,
    selectedPreamble,
    setSelectedPreamble,
    workflowState,
    searchResponse,
    formalizeResponse,
    theoremText,
    setTheoremText,
    displayScope,
    integrityWarnings,
    searchContext,
    timelineSteps,
    progress,
    job,
    toolCallCount,
    explanation,
    explanationOpen,
    setExplanationOpen,
    streamConnected,
    streamError,
    error: localError || api.error || "",
    isBusy: api.loading,
    resultKind: getResultKind(job),
    searchClaim,
    runPipeline,
    approveAndVerify,
    submitVerification: approveAndVerify,
    retryVerification,
    requestExplanation,
    reset,
    restoreSnapshot,
  };
}
