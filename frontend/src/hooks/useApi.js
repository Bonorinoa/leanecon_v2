import { useCallback, useRef, useState } from "react";

import { ensureTrailingSlash } from "../utils";

function resolveUrl(baseUrl, path) {
  return new URL(path, ensureTrailingSlash(baseUrl)).toString();
}

export function useApi(baseUrl) {
  const pendingRequestsRef = useRef(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const call = useCallback(
    async (path, options = {}) => {
      pendingRequestsRef.current += 1;
      setLoading(true);
      setError(null);

      try {
        const headers = new Headers(options.headers || {});
        const body =
          options.body &&
          typeof options.body !== "string" &&
          !(options.body instanceof FormData)
            ? JSON.stringify(options.body)
            : options.body;

        if (body && !headers.has("Content-Type") && !(body instanceof FormData)) {
          headers.set("Content-Type", "application/json");
        }

        const response = await fetch(resolveUrl(baseUrl, path), {
          ...options,
          headers,
          body,
        });

        const contentType = response.headers.get("content-type") || "";
        const payload = contentType.includes("application/json")
          ? await response.json()
          : await response.text();

        if (!response.ok) {
          const detail =
            typeof payload === "string"
              ? payload
              : payload?.detail || payload?.message || `Request failed with status ${response.status}.`;
          throw new Error(detail);
        }

        return payload;
      } catch (errorValue) {
        const message =
          errorValue instanceof Error ? errorValue.message : "Unexpected API request failure.";
        setError(message);
        throw errorValue instanceof Error ? errorValue : new Error(message);
      } finally {
        pendingRequestsRef.current -= 1;
        if (pendingRequestsRef.current <= 0) {
          pendingRequestsRef.current = 0;
          setLoading(false);
        }
      }
    },
    [baseUrl],
  );

  return {
    loading,
    error,
    call,
    setError,
  };
}
