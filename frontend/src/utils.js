export const DEFAULT_API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const DEFAULT_TIMEOUT = 300;

export const INPUT_MODES = [
  {
    value: "nl",
    label: "Natural Language",
    shortLabel: "NL",
    placeholder: "Under CRRA utility, relative risk aversion equals gamma",
  },
  {
    value: "latex",
    label: "LaTeX",
    shortLabel: "LaTeX",
    placeholder: String.raw`-c \cdot u''(c) / u'(c) = \gamma`,
  },
  {
    value: "lean",
    label: "Raw Lean",
    shortLabel: "Lean",
    placeholder: "theorem demo : 1 + 1 = 2 := by\n  sorry",
  },
];

const TERMINAL_STATUSES = new Set(["completed", "failed"]);
const ECON_TOKENS = new Set([
  "utility",
  "demand",
  "supply",
  "equilibrium",
  "budget",
  "consumer",
  "producer",
  "crra",
  "cara",
  "cobb",
  "douglas",
  "ces",
  "pareto",
  "nash",
  "slutsky",
  "phillips",
  "solow",
  "bellman",
  "walrasian",
  "marshallian",
  "hicksian",
  "risk",
  "aversion",
  "elasticity",
  "profit",
  "cost",
  "revenue",
  "production",
  "inflation",
  "discount",
  "gamma",
  "interest",
  "consumption",
  "saving",
]);
const STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "under",
  "into",
  "from",
  "that",
  "this",
  "then",
  "than",
  "when",
  "where",
  "over",
  "true",
  "prop",
  "claim",
  "theorem",
  "lemma",
  "proof",
  "sorry",
  "raw",
  "lean",
  "show",
  "shows",
  "equal",
  "equals",
  "holds",
  "every",
  "some",
  "their",
  "there",
  "which",
  "what",
  "have",
  "has",
  "does",
  "will",
  "must",
]);

const VACUOUS_PATTERNS = [
  /\(\s*\w+\s*:\s*Prop\s*\)\s*:\s*\w+\s*:=/i,
  /\(\s*claim\s*:\s*Prop\s*\)\s*:\s*claim/i,
  /:\s*True\s*:=/i,
  /\btheorem\s+\w+\s*\(\s*claim\s*:\s*Prop\s*\)\s*:\s*claim/i,
];

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status);
}

export function truncateClaim(text, maxLength = 25) {
  const normalized = String(text || "").trim().replace(/\s+/g, " ");
  if (!normalized) {
    return "Untitled attempt";
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}…`;
}

export function getApiUrl(baseUrl, path) {
  return new URL(path, ensureTrailingSlash(baseUrl)).toString();
}

export function ensureTrailingSlash(url) {
  return url.endsWith("/") ? url : `${url}/`;
}

export function normalizeSearchContext(searchResponse, formalizeResponse) {
  const context = formalizeResponse?.search_context || searchResponse;
  if (!context) {
    return null;
  }

  return {
    domain: context.domain || "economics",
    preambleMatches: context.preamble_matches || [],
    curatedHints: context.curated_hints || [],
    candidateImports: context.candidate_imports || [],
    candidateIdentifiers: context.candidate_identifiers || [],
    notes: context.notes || [],
    preambleNames: context.preamble_names || [],
    explicitPreambles: context.explicit_preambles || [],
    autoPreambles: context.auto_preambles || [],
  };
}

export function theoremLooksVacuous(theoremText) {
  const text = String(theoremText || "");
  return VACUOUS_PATTERNS.some((pattern) => pattern.test(text));
}

function normalizeText(text) {
  return String(text || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractSignalTokens(text) {
  return normalizeText(text)
    .split(" ")
    .filter(Boolean)
    .filter((token) => token.length > 3 || ECON_TOKENS.has(token))
    .filter((token) => !STOPWORDS.has(token));
}

export function getDisplayScope({ theoremText, formalizeResponse, mode }) {
  if (mode !== "lean" && theoremLooksVacuous(theoremText)) {
    return "VACUOUS";
  }
  return formalizeResponse?.scope || (mode === "lean" ? "RAW_LEAN" : null);
}

export function deriveIntegrityWarnings({ mode, claimText, theoremText, formalizeResponse }) {
  const warnings = [];
  const backendWarning = formalizeResponse?.faithfulness_warning;
  const backendScope = formalizeResponse?.scope;

  if (backendWarning) {
    warnings.push({
      id: "backend-faithfulness",
      level: "warning",
      text: backendWarning,
    });
  }

  if (backendScope === "VACUOUS" || (mode !== "lean" && theoremLooksVacuous(theoremText))) {
    warnings.push({
      id: "vacuous",
      level: "danger",
      text: "This formalization looks vacuous. It may be proving a tautology rather than the economics claim you entered.",
    });
  }

  if (mode === "lean") {
    return warnings;
  }

  const claimTokens = extractSignalTokens(claimText).filter((token) => ECON_TOKENS.has(token));
  const theoremTokens = new Set(extractSignalTokens(theoremText));
  const missingConcepts = [...new Set(claimTokens)].filter((token) => !theoremTokens.has(token));

  if (missingConcepts.length >= 2) {
    warnings.push({
      id: "dropped-concepts",
      level: "warning",
      text: `The theorem may have dropped important claim concepts: ${missingConcepts.slice(0, 5).join(", ")}.`,
    });
  }

  const theoremTextNormalized = normalizeText(theoremText);
  if (
    theoremTextNormalized.includes(" claim ") ||
    theoremTextNormalized.startsWith("claim ") ||
    theoremTextNormalized.includes(" prop ")
  ) {
    warnings.push({
      id: "genericized-symbols",
      level: "warning",
      text: "The theorem still looks unusually generic. Review whether named economic objects were replaced by generic variables.",
    });
  }

  return dedupeWarnings(warnings);
}

function dedupeWarnings(warnings) {
  const seen = new Set();
  return warnings.filter((warning) => {
    if (seen.has(warning.text)) {
      return false;
    }
    seen.add(warning.text);
    return true;
  });
}

export function getResultKind(job) {
  if (!job) {
    return null;
  }
  if (job.status === "completed") {
    return "verified";
  }
  if (job.status === "failed" && job.result?.partial && job.result?.stop_reason === "timeout") {
    return "timeout";
  }
  if (job.status === "failed") {
    return "failed";
  }
  return "running";
}

export function getHistoryIcon(job) {
  const kind = getResultKind(job);
  if (kind === "verified") {
    return "✅";
  }
  if (kind === "timeout") {
    return "⏱";
  }
  if (kind === "failed") {
    return "❌";
  }
  return "◉";
}

export function getToolCallCount(events, job, storedCount = 0) {
  const liveCount = events.filter(
    (event) => event.stage === "provider" && event.payload?.event_type === "tool_call",
  ).length;
  const historicalCount = Array.isArray(job?.result?.tool_history)
    ? job.result.tool_history.length
    : 0;
  return Math.max(liveCount, historicalCount, storedCount);
}

export function getLatestProgress(events, job) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.stage) {
      return {
        stage: event.stage,
        ...(event.payload || {}),
      };
    }
  }

  if (job?.result?.progress) {
    return job.result.progress;
  }

  return null;
}

export function buildTimelineSteps({ workflowState, job, progress, toolCallCount }) {
  const currentStage = progress?.stage;
  const resultKind = getResultKind(job);
  const activeIndex = getActiveIndex(workflowState, currentStage, job);

  const steps = [
    {
      id: "search",
      index: 1,
      label: "Searching retrieval context",
      detail: "Deterministic preamble and hint lookup",
    },
    {
      id: "formalize",
      index: 2,
      label: "Formalizing theorem",
      detail: "Shaping a Lean theorem stub",
    },
    {
      id: "review",
      index: 3,
      label: "Human review",
      detail: "Approve the theorem before proving",
    },
    {
      id: "prep",
      index: 4,
      label: "Preparing theorem",
      detail: "Initial compile and theorem setup",
    },
    {
      id: "fast-path",
      index: 5,
      label: "Trying quick tactics",
      detail:
        progress?.tactic && progress?.step
          ? `Step ${progress.step}: ${progress.tactic}`
          : "Local fast-path proving",
    },
    {
      id: "dispatch",
      index: 6,
      label: "Starting proof search",
      detail: "Dispatching the provider-backed agentic harness",
    },
    {
      id: "provider",
      index: 7,
      label: toolCallCount > 0 ? `AI proving (${toolCallCount} tool calls)` : "AI proving",
      detail: progress?.payload?.content || "Streaming provider tool calls and attempts",
    },
    {
      id: "kernel",
      index: 8,
      label: "Kernel verification",
      detail: "Final Lean 4 kernel verdict",
    },
  ];

  return steps.map((step) => ({
    ...step,
    status: getStepStatus(step.index, activeIndex, resultKind),
  }));
}

function getActiveIndex(workflowState, currentStage, job) {
  if (isTerminalStatus(job?.status)) {
    return 8;
  }
  if (currentStage === "provider") {
    return 7;
  }
  if (currentStage === "provider_dispatch" || currentStage === "provider_finalize") {
    return 6;
  }
  if (currentStage === "fast_path" || currentStage === "fast_path_compile") {
    return 5;
  }
  if (currentStage === "initialize" || currentStage === "initial_compile") {
    return 4;
  }
  if (workflowState === "reviewing") {
    return 3;
  }
  if (workflowState === "formalizing") {
    return 2;
  }
  if (workflowState === "searching") {
    return 1;
  }
  if (workflowState === "verifying" || workflowState === "streaming") {
    return 4;
  }
  return 0;
}

function getStepStatus(stepIndex, activeIndex, resultKind) {
  if (stepIndex < activeIndex) {
    return "complete";
  }
  if (stepIndex === activeIndex) {
    if (stepIndex === 8 && resultKind === "failed") {
      return "error";
    }
    if (stepIndex === 8 && resultKind === "timeout") {
      return "warning";
    }
    if (resultKind === "verified" && stepIndex === 8) {
      return "complete";
    }
    return "active";
  }
  return "pending";
}
