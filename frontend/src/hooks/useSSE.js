import { startTransition, useEffect, useRef, useState } from "react";

import { isTerminalStatus } from "../utils";

function normalizeEvent(data) {
  if (!data || typeof data !== "object") {
    return null;
  }

  if (data.type === "snapshot" && data.job) {
    return {
      type: "snapshot",
      status: data.job.status,
      stage: data.job.result?.progress?.stage || null,
      payload: data.job.result?.progress || {},
      job: data.job,
      jobId: data.job.id,
      terminal: isTerminalStatus(data.job.status),
      receivedAt: new Date().toISOString(),
    };
  }

  return {
    type: data.type || "message",
    status: data.status || null,
    stage: data.stage || null,
    payload: data.payload || {},
    job: data.job || null,
    jobId: data.job_id || data.jobId || null,
    result: data.result || null,
    error: data.error || null,
    terminal: isTerminalStatus(data.status),
    receivedAt: new Date().toISOString(),
  };
}

export function useSSE(streamUrl, { enabled = true } = {}) {
  const sourceRef = useRef(null);
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setEvents([]);
    setConnected(false);
    setError(null);

    if (!enabled || !streamUrl) {
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      return undefined;
    }

    let cancelled = false;
    let reconnectTimer = null;
    let reconnectAttempt = 0;
    let terminalClosed = false;

    const connect = () => {
      if (cancelled || terminalClosed) {
        return;
      }

      const source = new EventSource(streamUrl);
      sourceRef.current = source;

      source.onopen = () => {
        setConnected(true);
        setError(null);
        reconnectAttempt = 0;
      };

      source.onmessage = (message) => {
        try {
          const normalized = normalizeEvent(JSON.parse(message.data));
          if (!normalized) {
            return;
          }

          startTransition(() => {
            setEvents((previous) => [...previous, normalized]);
          });

          if (normalized.terminal) {
            terminalClosed = true;
            setConnected(false);
            source.close();
          }
        } catch {
          setError("Received an invalid SSE payload.");
        }
      };

      source.addEventListener("ping", () => {
        setConnected(true);
      });

      source.onerror = () => {
        setConnected(false);
        source.close();

        if (cancelled || terminalClosed) {
          return;
        }

        const delay = Math.min(1000 * 2 ** reconnectAttempt, 5000);
        reconnectAttempt += 1;
        setError("Progress stream disconnected. Reconnecting...");
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [enabled, streamUrl]);

  return {
    events,
    connected,
    error,
  };
}
