import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  RadialBar,
  RadialBarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const RUNNER_LABELS = {
  formalizer_only: "Formalizer",
  prover_only: "Prover",
  e2e: "End-to-End",
}

const PASS_BANDS = {
  strong: {
    badge: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    card: "border-emerald-300 bg-emerald-50/70",
    fill: "#059669",
  },
  medium: {
    badge: "bg-amber-100 text-amber-800 ring-amber-200",
    card: "border-amber-300 bg-amber-50/70",
    fill: "#d97706",
  },
  weak: {
    badge: "bg-rose-100 text-rose-800 ring-rose-200",
    card: "border-rose-300 bg-rose-50/70",
    fill: "#dc2626",
  },
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function toNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return null
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function passBand(passAt1) {
  if (passAt1 >= 0.8) {
    return PASS_BANDS.strong
  }
  if (passAt1 >= 0.5) {
    return PASS_BANDS.medium
  }
  return PASS_BANDS.weak
}

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A"
  }
  return `${(value * 100).toFixed(1)}%`
}

function formatSeconds(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A"
  }
  if (value >= 60) {
    return `${value.toFixed(1)}s`
  }
  if (value >= 1) {
    return `${value.toFixed(2)}s`
  }
  return `${value.toFixed(3)}s`
}

function formatCount(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A"
  }
  return `${value}`
}

function formatTimestamp(value) {
  if (!value) {
    return "Unknown time"
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }
  return date.toLocaleString()
}

function formatDelta(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A"
  }
  const prefix = value > 0 ? "+" : ""
  return `${prefix}${(value * 100).toFixed(1)} pts`
}

function splitJsonDocuments(text) {
  const documents = []
  let start = -1
  let depth = 0
  let inString = false
  let escapeNext = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]

    if (inString) {
      if (escapeNext) {
        escapeNext = false
      } else if (char === "\\") {
        escapeNext = true
      } else if (char === "\"") {
        inString = false
      }
      continue
    }

    if (char === "\"") {
      inString = true
      continue
    }

    if (depth === 0) {
      if (/\s/.test(char)) {
        continue
      }
      if (char !== "{" && char !== "[") {
        throw new Error(
          `Unexpected character "${char}" outside a JSON document at offset ${index}.`
        )
      }
      start = index
      depth = 1
      continue
    }

    if (char === "{" || char === "[") {
      depth += 1
      continue
    }

    if (char === "}" || char === "]") {
      depth -= 1
      if (depth < 0) {
        throw new Error("Encountered an unexpected closing brace while parsing input.")
      }
      if (depth === 0 && start !== -1) {
        documents.push(text.slice(start, index + 1))
        start = -1
      }
    }
  }

  if (inString || depth !== 0) {
    throw new Error("The pasted JSON appears to be incomplete.")
  }

  return documents
}

function flattenArtifacts(value) {
  if (Array.isArray(value)) {
    return value.flatMap(flattenArtifacts)
  }
  if (isObject(value)) {
    return [value]
  }
  throw new Error("Each parsed JSON document must be an object or an array of objects.")
}

function parseArtifactsText(text) {
  if (!text.trim()) {
    return []
  }

  try {
    return flattenArtifacts(JSON.parse(text))
  } catch (_error) {
    const documents = splitJsonDocuments(text)
    return documents.flatMap((documentText) => flattenArtifacts(JSON.parse(documentText)))
  }
}

function normalizeDistribution(distribution) {
  if (!isObject(distribution)) {
    return []
  }

  return Object.entries(distribution)
    .map(([toolName, count]) => ({
      toolName,
      count: toNumber(count) ?? 0,
    }))
    .sort((left, right) => right.count - left.count || left.toolName.localeCompare(right.toolName))
}

function inferErrorType(status, caseData) {
  if (caseData.error_type) {
    return String(caseData.error_type)
  }
  if (status === "skipped") {
    return "skipped"
  }
  if (status !== "failed") {
    return null
  }
  return "verification_failed"
}

function normalizeCase(caseData, runner, index) {
  const rawStatus =
    caseData.status ??
    (typeof caseData.success === "boolean"
      ? caseData.success
        ? "completed"
        : "failed"
      : "unknown")
  const status = String(rawStatus)
  const isSuccess =
    typeof caseData.success === "boolean" ? caseData.success : status === "completed"
  const latencySeconds = toNumber(caseData.latency_seconds)
  const toolCallsMade = toNumber(caseData.tool_calls_made) ?? toNumber(caseData.tool_calls)
  const maxToolCalls = toNumber(caseData.max_tool_calls)
  const maxSearchToolCalls = toNumber(caseData.max_search_tool_calls)

  return {
    id: String(caseData.id ?? `${runner}_case_${index + 1}`),
    status,
    isSuccess,
    latencySeconds,
    attemptCount: toNumber(caseData.attempt_count) ?? toNumber(caseData.attempts),
    formalizeAttempts: toNumber(caseData.formalize_attempts),
    formalizeSuccess:
      typeof caseData.formalize_success === "boolean" ? caseData.formalize_success : null,
    toolCalls: toNumber(caseData.tool_calls),
    toolCallsMade,
    maxToolCalls,
    maxSearchToolCalls,
    lastStage: caseData.last_stage ? String(caseData.last_stage) : null,
    errorType: inferErrorType(status, caseData),
    errorMessage: caseData.error_message ? String(caseData.error_message) : null,
    stopReason: caseData.stop_reason ? String(caseData.stop_reason) : null,
  }
}

function deriveCounts(artifact, runner, cases) {
  const totalClaims = toNumber(artifact.total_claims) ?? cases.length
  const attemptedClaims =
    runner === "prover_only" ? toNumber(artifact.attempted_claims) ?? cases.length : null
  const skippedClaims =
    runner === "prover_only" ? toNumber(artifact.skipped_claims) ?? 0 : null

  if (runner === "e2e") {
    const successes =
      toNumber(artifact.end_to_end_successes) ??
      cases.filter((item) => item.isSuccess).length
    const failures =
      toNumber(artifact.end_to_end_failures) ??
      Math.max(totalClaims - successes, 0)
    return { totalClaims, successes, failures, attemptedClaims, skippedClaims }
  }

  const successes =
    toNumber(artifact.successes) ?? cases.filter((item) => item.isSuccess).length
  const failures =
    toNumber(artifact.failures) ?? Math.max((attemptedClaims ?? totalClaims) - successes, 0)

  return { totalClaims, successes, failures, attemptedClaims, skippedClaims }
}

function normalizeToolBudget(artifact, cases) {
  const runBudget = isObject(artifact.tool_budget) ? artifact.tool_budget : {}
  const toolCallsMade = cases
    .map((item) => item.toolCallsMade)
    .filter((value) => typeof value === "number")
  const maxTotalToolCalls =
    toNumber(runBudget.max_total_tool_calls) ??
    cases.find((item) => typeof item.maxToolCalls === "number")?.maxToolCalls ??
    null
  const maxSearchToolCalls =
    toNumber(runBudget.max_search_tool_calls) ??
    cases.find((item) => typeof item.maxSearchToolCalls === "number")?.maxSearchToolCalls ??
    null
  const meanToolCallsMade =
    toNumber(runBudget.mean_tool_calls_made) ??
    (toolCallsMade.length
      ? toolCallsMade.reduce((total, value) => total + value, 0) / toolCallsMade.length
      : null)
  const maxToolCallsMade =
    toNumber(runBudget.max_tool_calls_made) ??
    (toolCallsMade.length ? Math.max(...toolCallsMade) : null)

  if (
    maxTotalToolCalls === null &&
    maxSearchToolCalls === null &&
    meanToolCallsMade === null &&
    maxToolCallsMade === null
  ) {
    return null
  }

  return {
    maxTotalToolCalls,
    maxSearchToolCalls,
    meanToolCallsMade,
    maxToolCallsMade,
    utilization:
      typeof meanToolCallsMade === "number" && typeof maxTotalToolCalls === "number"
        ? clamp(meanToolCallsMade / maxTotalToolCalls, 0, 1)
        : null,
  }
}

function normalizeArtifact(artifact, index) {
  if (!isObject(artifact)) {
    throw new Error(`Artifact ${index + 1} is not a JSON object.`)
  }

  const runner = String(artifact.runner ?? `artifact_${index + 1}`)
  const claimSet = String(artifact.claim_set ?? artifact.claimSet ?? `unknown_${index + 1}`)
  const generatedAt = String(artifact.generated_at ?? artifact.generatedAt ?? `artifact_${index + 1}`)
  const cases = Array.isArray(artifact.cases)
    ? artifact.cases.map((caseData, caseIndex) => normalizeCase(caseData, runner, caseIndex))
    : []
  const counts = deriveCounts(artifact, runner, cases)
  const latency = isObject(artifact.latency_seconds) ? artifact.latency_seconds : {}
  const toolDistribution = normalizeDistribution(artifact.tool_call_distribution)
  const toolBudget = normalizeToolBudget(artifact, cases)
  const passAt1 =
    toNumber(artifact.pass_at_1) ??
    (counts.totalClaims > 0 ? counts.successes / counts.totalClaims : 0)

  return {
    runId: `${runner}__${claimSet}__${generatedAt}__${index}`,
    runner,
    runnerLabel: RUNNER_LABELS[runner] ?? runner,
    claimSet,
    generatedAt,
    passAt1,
    counts,
    latency: {
      count: toNumber(latency.count),
      mean: toNumber(latency.mean),
      p50: toNumber(latency.p50),
      p95: toNumber(latency.p95),
    },
    attempts: isObject(artifact.attempts) ? artifact.attempts : null,
    formalizeAttempts: isObject(artifact.formalize_attempts) ? artifact.formalize_attempts : null,
    terminalStatusDistribution: isObject(artifact.terminal_status_distribution)
      ? artifact.terminal_status_distribution
      : null,
    toolDistribution,
    toolBudget,
    rawArtifact: artifact,
    cases,
  }
}

function dedupeRuns(runs) {
  const seen = new Map()
  runs.forEach((run) => {
    seen.set(run.runId, run)
  })
  return Array.from(seen.values()).sort((left, right) => {
    const leftTime = Date.parse(left.generatedAt)
    const rightTime = Date.parse(right.generatedAt)
    if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) {
      return right.runId.localeCompare(left.runId)
    }
    return rightTime - leftTime
  })
}

function mergeRuns(existingRuns, incomingRuns) {
  return dedupeRuns([...existingRuns, ...incomingRuns])
}

function buildLatencyRows(run) {
  return run.cases.map((item) => ({
    id: item.id,
    latencySeconds: item.latencySeconds ?? 0,
    fill:
      item.status === "completed"
        ? "#0f766e"
        : item.status === "skipped"
          ? "#6b7280"
          : "#b91c1c",
  }))
}

function buildFailureRows(run, sortKey, sortDirection) {
  const multiplier = sortDirection === "asc" ? 1 : -1
  return run.cases
    .filter((item) => !item.isSuccess)
    .slice()
    .sort((left, right) => {
      if (sortKey === "errorType") {
        return multiplier * String(left.errorType ?? "").localeCompare(String(right.errorType ?? ""))
      }
      if (sortKey === "latencySeconds") {
        return multiplier * ((left.latencySeconds ?? -1) - (right.latencySeconds ?? -1))
      }
      return multiplier * left.id.localeCompare(right.id)
    })
}

function buildComparisonRows(leftRun, rightRun) {
  const leftCases = new Map(leftRun.cases.map((item) => [item.id, item]))
  const rightCases = new Map(rightRun.cases.map((item) => [item.id, item]))
  const allIds = Array.from(new Set([...leftCases.keys(), ...rightCases.keys()])).sort()

  return allIds.map((id) => {
    const leftCase = leftCases.get(id) ?? null
    const rightCase = rightCases.get(id) ?? null
    let tone = "neutral"
    let deltaLabel = "unchanged"

    if (!leftCase && rightCase) {
      deltaLabel = "right-only"
    } else if (leftCase && !rightCase) {
      deltaLabel = "left-only"
    } else if (leftCase && rightCase && !leftCase.isSuccess && rightCase.isSuccess) {
      tone = "improved"
      deltaLabel = "improved"
    } else if (leftCase && rightCase && leftCase.isSuccess && !rightCase.isSuccess) {
      tone = "regressed"
      deltaLabel = "regressed"
    }

    return {
      id,
      leftCase,
      rightCase,
      tone,
      deltaLabel,
      latencyDeltaSeconds:
        leftCase && rightCase && leftCase.latencySeconds !== null && rightCase.latencySeconds !== null
          ? rightCase.latencySeconds - leftCase.latencySeconds
          : null,
    }
  })
}

function applyStateTransition(updater) {
  if (typeof ReactRuntime.startTransition === "function") {
    ReactRuntime.startTransition(updater)
    return
  }
  updater()
}

function SectionCard({ title, subtitle, children, actions }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white/90 shadow-sm shadow-slate-200/60 backdrop-blur">
      <div className="flex flex-col gap-4 border-b border-slate-200 px-6 py-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          {subtitle ? <p className="text-sm text-slate-500">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
      <div className="px-6 py-5">{children}</div>
    </section>
  )
}

function MetricTile({ label, value, hint }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-slate-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}

function SortButton({ active, direction, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 transition ${
        active
          ? "bg-slate-900 text-white ring-slate-900"
          : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50"
      }`}
    >
      <span>{children}</span>
      {active ? <span>{direction === "asc" ? "↑" : "↓"}</span> : null}
    </button>
  )
}

function EvalDashboard() {
  const [inputText, setInputText] = useState("")
  const [runs, setRuns] = useState([])
  const [parseError, setParseError] = useState("")
  const [selectedRunId, setSelectedRunId] = useState("")
  const [leftRunId, setLeftRunId] = useState("")
  const [rightRunId, setRightRunId] = useState("")
  const [failureSortKey, setFailureSortKey] = useState("latencySeconds")
  const [failureSortDirection, setFailureSortDirection] = useState("desc")

  useEffect(() => {
    if (!runs.length) {
      setSelectedRunId("")
      setLeftRunId("")
      setRightRunId("")
      return
    }

    if (!runs.some((run) => run.runId === selectedRunId)) {
      setSelectedRunId(runs[0].runId)
    }

    if (!runs.some((run) => run.runId === leftRunId)) {
      setLeftRunId(runs[0].runId)
    }

    if (!runs.some((run) => run.runId === rightRunId)) {
      setRightRunId(runs[1]?.runId ?? runs[0].runId)
    }
  }, [runs, selectedRunId, leftRunId, rightRunId])

  const selectedRun = runs.find((run) => run.runId === selectedRunId) ?? runs[0] ?? null
  const leftRun = runs.find((run) => run.runId === leftRunId) ?? null
  const rightRun = runs.find((run) => run.runId === rightRunId) ?? null
  const failureRows = selectedRun
    ? buildFailureRows(selectedRun, failureSortKey, failureSortDirection)
    : []
  const comparisonRows =
    leftRun && rightRun ? buildComparisonRows(leftRun, rightRun) : []
  const latencyRows = selectedRun ? buildLatencyRows(selectedRun) : []

  function handleParseInput() {
    try {
      const parsed = parseArtifactsText(inputText)
      const normalized = parsed.map((artifact, index) => normalizeArtifact(artifact, index))
      applyStateTransition(() => setRuns(dedupeRuns(normalized)))
      setParseError("")
    } catch (error) {
      setParseError(error instanceof Error ? error.message : "Unable to parse pasted JSON.")
    }
  }

  async function handleFileImport(event) {
    const files = Array.from(event.target.files ?? [])
    if (!files.length) {
      return
    }

    try {
      const fileTexts = await Promise.all(files.map((file) => file.text()))
      const parsedArtifacts = fileTexts.flatMap((text) => parseArtifactsText(text))
      const normalized = parsedArtifacts.map((artifact, index) =>
        normalizeArtifact(artifact, runs.length + index)
      )
      applyStateTransition(() => setRuns((currentRuns) => mergeRuns(currentRuns, normalized)))
      setParseError("")
      event.target.value = ""
    } catch (error) {
      setParseError(error instanceof Error ? error.message : "Unable to import JSON files.")
    }
  }

  function handleReset() {
    setInputText("")
    setParseError("")
    setRuns([])
  }

  function toggleFailureSort(nextKey) {
    if (failureSortKey === nextKey) {
      setFailureSortDirection((current) => (current === "asc" ? "desc" : "asc"))
      return
    }
    setFailureSortKey(nextKey)
    setFailureSortDirection(nextKey === "errorType" ? "asc" : "desc")
  }

  const comparisonDelta =
    leftRun && rightRun ? rightRun.passAt1 - leftRun.passAt1 : null

  return (
    <div className="w-full text-slate-900 transition-all duration-200">
      <div className="flex flex-col gap-6 w-full">
        <header className="panel overflow-hidden relative">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-teal-700">
                LeanEcon Observability
              </p>
              <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
                Eval dashboard for artifact-first benchmarking
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">
                Paste or import one or more eval artifacts from <code>.cache/evals/</code> to
                inspect pass@1, latency, tool usage, and before-versus-after comparison at a
                glance.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricTile label="Runs" value={formatCount(runs.length)} />
              <MetricTile
                label="Selected"
                value={selectedRun ? selectedRun.runnerLabel : "None"}
              />
              <MetricTile
                label="Comparison"
                value={leftRun && rightRun ? "Ready" : "Need 2 runs"}
              />
              <MetricTile
                label="Parser"
                value={parseError ? "Error" : "Healthy"}
                hint={parseError ? "See the input panel below." : "JSON import ready."}
              />
            </div>
          </div>
        </header>

        <SectionCard
          title="Data Input"
          subtitle="Use pasted JSON for quick iteration, file import for local artifacts, and reset when you want a clean comparison slate."
          actions={
            <>
              <button
                type="button"
                onClick={handleParseInput}
                className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                Parse pasted JSON
              </button>
              <label className="cursor-pointer rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50">
                Import JSON files
                <input
                  type="file"
                  accept=".json,application/json"
                  multiple
                  onChange={handleFileImport}
                  className="hidden"
                />
              </label>
              <button
                type="button"
                onClick={handleReset}
                className="rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50"
              >
                Reset
              </button>
            </>
          }
        >
          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
            <div className="space-y-3">
              <textarea
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
                rows={18}
                placeholder={`Paste one JSON object, one JSON array, or multiple pretty-printed JSON objects here.\n\nExample:\n{\n  "runner": "prover_only",\n  "claim_set": "tier0_smoke",\n  "generated_at": "2026-03-28T05:21:00.691321+00:00",\n  "pass_at_1": 1.0\n}`}
                className="w-full rounded-3xl border border-slate-300 bg-slate-950 px-4 py-4 font-mono text-sm leading-6 text-emerald-100 shadow-inner shadow-slate-950/40 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-200"
              />
              {parseError ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  <span className="font-semibold">Parse error:</span> {parseError}
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-900">Accepted input shapes</h3>
                <ul className="mt-3 space-y-2 text-sm text-slate-600">
                  <li>One eval JSON object copied directly from `.cache/evals/*.json`</li>
                  <li>An array of eval objects for batch comparison</li>
                  <li>Multiple pretty-printed JSON objects pasted one after another</li>
                </ul>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-900">Dashboard expectations</h3>
                <ul className="mt-3 space-y-2 text-sm text-slate-600">
                  <li>Older artifacts still load even if newer budget metadata is missing</li>
                  <li>Comparison mode matches cases by `id` and flags regressions clearly</li>
                  <li>Failure analysis prefers explicit `error_type`, `last_stage`, and budget fields</li>
                </ul>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Eval Runs"
          subtitle="Each card summarizes one imported artifact. Click a card to drive the detail panels below."
        >
          {runs.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {runs.map((run) => {
                const band = passBand(run.passAt1)
                const isSelected = run.runId === selectedRun?.runId

                return (
                  <button
                    key={run.runId}
                    type="button"
                    onClick={() => setSelectedRunId(run.runId)}
                    className={`rounded-[1.75rem] border px-5 py-5 text-left transition ${
                      isSelected
                        ? `${band.card} ring-2 ring-offset-2 ring-teal-300`
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-500">
                          {run.runnerLabel}
                        </p>
                        <h3 className="mt-2 text-xl font-semibold text-slate-950">
                          {run.claimSet}
                        </h3>
                        <p className="mt-1 text-sm text-slate-500">
                          {formatTimestamp(run.generatedAt)}
                        </p>
                      </div>
                      <span
                        className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ${band.badge}`}
                      >
                        pass@1
                      </span>
                    </div>
                    <div className="mt-6 flex items-end justify-between gap-4">
                      <div>
                        <p className="text-4xl font-semibold tracking-tight text-slate-950">
                          {formatPercent(run.passAt1)}
                        </p>
                        <p className="mt-2 text-sm text-slate-500">
                          {run.counts.successes} successes, {run.counts.failures} failures
                        </p>
                      </div>
                      <div className="text-right text-sm text-slate-500">
                        <p>Total claims: {formatCount(run.counts.totalClaims)}</p>
                        {run.counts.attemptedClaims !== null ? (
                          <p>Attempted: {formatCount(run.counts.attemptedClaims)}</p>
                        ) : null}
                        {run.counts.skippedClaims !== null ? (
                          <p>Skipped: {formatCount(run.counts.skippedClaims)}</p>
                        ) : null}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
              No runs loaded yet. Paste JSON or import one or more files to populate the dashboard.
            </div>
          )}
        </SectionCard>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.9fr)]">
          <SectionCard
            title="Latency"
            subtitle={
              selectedRun
                ? `${selectedRun.runnerLabel} on ${selectedRun.claimSet}`
                : "Select a run to inspect per-claim latency."
            }
          >
            {selectedRun && latencyRows.length ? (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  <MetricTile
                    label="Mean"
                    value={formatSeconds(selectedRun.latency.mean)}
                  />
                  <MetricTile label="p50" value={formatSeconds(selectedRun.latency.p50)} />
                  <MetricTile label="p95" value={formatSeconds(selectedRun.latency.p95)} />
                </div>
                <div className="h-[320px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={latencyRows} margin={{ top: 8, right: 24, left: 8, bottom: 24 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                      <XAxis
                        dataKey="id"
                        tick={{ fill: "#475569", fontSize: 12 }}
                        angle={-25}
                        textAnchor="end"
                        height={90}
                        interval={0}
                      />
                      <YAxis tick={{ fill: "#475569", fontSize: 12 }} />
                      <Tooltip
                        formatter={(value) => formatSeconds(Number(value))}
                        contentStyle={{
                          borderRadius: "1rem",
                          borderColor: "#cbd5e1",
                          boxShadow: "0 12px 30px rgba(15, 23, 42, 0.12)",
                        }}
                      />
                      {typeof selectedRun.latency.p50 === "number" ? (
                        <ReferenceLine
                          y={selectedRun.latency.p50}
                          stroke="#0f766e"
                          strokeDasharray="6 4"
                          label={{ value: "p50", fill: "#0f766e", position: "top" }}
                        />
                      ) : null}
                      {typeof selectedRun.latency.p95 === "number" ? (
                        <ReferenceLine
                          y={selectedRun.latency.p95}
                          stroke="#c2410c"
                          strokeDasharray="6 4"
                          label={{ value: "p95", fill: "#c2410c", position: "top" }}
                        />
                      ) : null}
                      <Bar dataKey="latencySeconds" radius={[10, 10, 0, 0]}>
                        {latencyRows.map((entry) => (
                          <Cell key={entry.id} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : (
              <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                Load a run with case-level latency data to render the chart.
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Tooling"
            subtitle="Tool-call distribution and budget utilization are most informative for prover-heavy runs."
          >
            {selectedRun ? (
              <div className="space-y-6">
                <div className="grid gap-3 sm:grid-cols-2">
                  <MetricTile
                    label="Mean tool calls"
                    value={
                      selectedRun.toolBudget?.meanToolCallsMade !== null &&
                      selectedRun.toolBudget?.meanToolCallsMade !== undefined
                        ? selectedRun.toolBudget.meanToolCallsMade.toFixed(2)
                        : "N/A"
                    }
                  />
                  <MetricTile
                    label="Max tool calls"
                    value={formatCount(selectedRun.toolBudget?.maxToolCallsMade)}
                    hint={
                      selectedRun.toolBudget?.maxTotalToolCalls !== null &&
                      selectedRun.toolBudget?.maxTotalToolCalls !== undefined
                        ? `Budget ceiling ${selectedRun.toolBudget.maxTotalToolCalls}`
                        : "No max budget in artifact"
                    }
                  />
                </div>

                {selectedRun.toolBudget ? (
                  <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">Budget utilization</h3>
                        <p className="text-sm text-slate-500">
                          Mean tool calls made divided by max total tool calls.
                        </p>
                      </div>
                      <div className="text-right text-sm text-slate-500">
                        <p>Search cap: {formatCount(selectedRun.toolBudget.maxSearchToolCalls)}</p>
                        <p>Total cap: {formatCount(selectedRun.toolBudget.maxTotalToolCalls)}</p>
                      </div>
                    </div>
                    <div className="relative mt-4 flex h-56 items-center justify-center">
                      <ResponsiveContainer width="100%" height="100%">
                        <RadialBarChart
                          innerRadius="62%"
                          outerRadius="100%"
                          barSize={24}
                          startAngle={210}
                          endAngle={-30}
                          data={[
                            {
                              name: "Utilization",
                              value:
                                typeof selectedRun.toolBudget.utilization === "number"
                                  ? selectedRun.toolBudget.utilization * 100
                                  : 0,
                              fill:
                                typeof selectedRun.toolBudget.utilization === "number" &&
                                selectedRun.toolBudget.utilization >= 0.8
                                  ? "#dc2626"
                                  : typeof selectedRun.toolBudget.utilization === "number" &&
                                      selectedRun.toolBudget.utilization >= 0.5
                                    ? "#d97706"
                                    : "#059669",
                            },
                          ]}
                        >
                          <RadialBar background clockWise dataKey="value" cornerRadius={18} />
                          <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
                        </RadialBarChart>
                      </ResponsiveContainer>
                      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <p className="text-xs uppercase tracking-[0.25em] text-slate-500">
                          Mean budget use
                        </p>
                        <p className="mt-2 text-3xl font-semibold text-slate-950">
                          {selectedRun.toolBudget.utilization !== null
                            ? `${(selectedRun.toolBudget.utilization * 100).toFixed(1)}%`
                            : "N/A"}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                    This artifact does not include tool-budget metadata.
                  </div>
                )}

                {selectedRun.toolDistribution.length ? (
                  <div className="h-[320px] w-full rounded-3xl border border-slate-200 bg-slate-50 p-4">
                    <h3 className="mb-3 text-sm font-semibold text-slate-900">
                      Tool call distribution
                    </h3>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={selectedRun.toolDistribution}
                        layout="vertical"
                        margin={{ top: 8, right: 24, left: 24, bottom: 8 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                        <XAxis type="number" tick={{ fill: "#475569", fontSize: 12 }} />
                        <YAxis
                          type="category"
                          dataKey="toolName"
                          tick={{ fill: "#475569", fontSize: 12 }}
                          width={120}
                        />
                        <Tooltip
                          formatter={(value) => formatCount(Number(value))}
                          contentStyle={{
                            borderRadius: "1rem",
                            borderColor: "#cbd5e1",
                            boxShadow: "0 12px 30px rgba(15, 23, 42, 0.12)",
                          }}
                        />
                        <Bar dataKey="count" radius={[0, 10, 10, 0]} fill="#0f766e" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                    No tool-call distribution is available for this run.
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                Select a run to inspect tool usage.
              </div>
            )}
          </SectionCard>
        </div>

        <SectionCard
          title="Failure Breakdown"
          subtitle="Sortable failure table for the selected run, tuned for quick triage during benchmark ratchets."
          actions={
            <>
              <SortButton
                active={failureSortKey === "latencySeconds"}
                direction={failureSortDirection}
                onClick={() => toggleFailureSort("latencySeconds")}
              >
                Sort by latency
              </SortButton>
              <SortButton
                active={failureSortKey === "errorType"}
                direction={failureSortDirection}
                onClick={() => toggleFailureSort("errorType")}
              >
                Sort by error type
              </SortButton>
              <SortButton
                active={failureSortKey === "id"}
                direction={failureSortDirection}
                onClick={() => toggleFailureSort("id")}
              >
                Sort by ID
              </SortButton>
            </>
          }
        >
          {selectedRun && failureRows.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-[0.2em] text-slate-500">
                    <th className="pb-3 pr-4">ID</th>
                    <th className="pb-3 pr-4">Error Type</th>
                    <th className="pb-3 pr-4">Last Stage</th>
                    <th className="pb-3 pr-4">Tool Calls</th>
                    <th className="pb-3 pr-4">Latency</th>
                    <th className="pb-3">Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {failureRows.map((row) => (
                    <tr key={row.id} className="align-top">
                      <td className="py-3 pr-4 font-medium text-slate-900">{row.id}</td>
                      <td className="py-3 pr-4 text-slate-600">{row.errorType ?? "N/A"}</td>
                      <td className="py-3 pr-4 text-slate-600">{row.lastStage ?? "N/A"}</td>
                      <td className="py-3 pr-4 text-slate-600">
                        {formatCount(row.toolCallsMade)}
                      </td>
                      <td className="py-3 pr-4 text-slate-600">
                        {formatSeconds(row.latencySeconds)}
                      </td>
                      <td className="py-3 text-slate-600">
                        {row.errorMessage ?? row.stopReason ?? "No explicit error message"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
              {selectedRun
                ? "No failing claims are present in the selected artifact."
                : "Select a run to inspect failures."}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Comparison Mode"
          subtitle="Side-by-side artifact comparison for before-versus-after benchmark ratchets."
          actions={
            <div className="flex flex-col gap-2 sm:flex-row">
              <select
                value={leftRunId}
                onChange={(event) => setLeftRunId(event.target.value)}
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-200"
              >
                {runs.map((run) => (
                  <option key={`left_${run.runId}`} value={run.runId}>
                    {run.runnerLabel} · {run.claimSet} · {formatTimestamp(run.generatedAt)}
                  </option>
                ))}
              </select>
              <select
                value={rightRunId}
                onChange={(event) => setRightRunId(event.target.value)}
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-200"
              >
                {runs.map((run) => (
                  <option key={`right_${run.runId}`} value={run.runId}>
                    {run.runnerLabel} · {run.claimSet} · {formatTimestamp(run.generatedAt)}
                  </option>
                ))}
              </select>
            </div>
          }
        >
          {leftRun && rightRun ? (
            <div className="space-y-6">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px_minmax(0,1fr)]">
                <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Baseline</p>
                  <h3 className="mt-2 text-lg font-semibold text-slate-950">
                    {leftRun.runnerLabel} · {leftRun.claimSet}
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">{formatTimestamp(leftRun.generatedAt)}</p>
                  <p className="mt-4 text-3xl font-semibold text-slate-950">
                    {formatPercent(leftRun.passAt1)}
                  </p>
                </div>
                <div className="flex flex-col items-center justify-center rounded-3xl border border-slate-200 bg-white px-5 py-4 text-center">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Delta</p>
                  <p
                    className={`mt-3 text-3xl font-semibold ${
                      typeof comparisonDelta === "number" && comparisonDelta > 0
                        ? "text-emerald-700"
                        : typeof comparisonDelta === "number" && comparisonDelta < 0
                          ? "text-rose-700"
                          : "text-slate-900"
                    }`}
                  >
                    {formatDelta(comparisonDelta)}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">
                    {typeof comparisonDelta === "number" && comparisonDelta > 0
                      ? "Improved pass@1"
                      : typeof comparisonDelta === "number" && comparisonDelta < 0
                        ? "Regressed pass@1"
                        : "No pass@1 change"}
                  </p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Candidate</p>
                  <h3 className="mt-2 text-lg font-semibold text-slate-950">
                    {rightRun.runnerLabel} · {rightRun.claimSet}
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    {formatTimestamp(rightRun.generatedAt)}
                  </p>
                  <p className="mt-4 text-3xl font-semibold text-slate-950">
                    {formatPercent(rightRun.passAt1)}
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-[0.2em] text-slate-500">
                      <th className="pb-3 pr-4">Claim ID</th>
                      <th className="pb-3 pr-4">{leftRun.claimSet}</th>
                      <th className="pb-3 pr-4">{rightRun.claimSet}</th>
                      <th className="pb-3 pr-4">Delta</th>
                      <th className="pb-3">Latency Δ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {comparisonRows.map((row) => (
                      <tr
                        key={row.id}
                        className={
                          row.tone === "improved"
                            ? "bg-emerald-50/60"
                            : row.tone === "regressed"
                              ? "bg-rose-50/60"
                              : ""
                        }
                      >
                        <td className="py-3 pr-4 font-medium text-slate-900">{row.id}</td>
                        <td className="py-3 pr-4 text-slate-600">
                          {row.leftCase
                            ? `${row.leftCase.status}${row.leftCase.errorType ? ` · ${row.leftCase.errorType}` : ""}`
                            : "missing"}
                        </td>
                        <td className="py-3 pr-4 text-slate-600">
                          {row.rightCase
                            ? `${row.rightCase.status}${row.rightCase.errorType ? ` · ${row.rightCase.errorType}` : ""}`
                            : "missing"}
                        </td>
                        <td
                          className={`py-3 pr-4 font-medium ${
                            row.tone === "improved"
                              ? "text-emerald-700"
                              : row.tone === "regressed"
                                ? "text-rose-700"
                                : "text-slate-600"
                          }`}
                        >
                          {row.deltaLabel}
                        </td>
                        <td className="py-3 text-slate-600">
                          {row.latencyDeltaSeconds !== null
                            ? `${row.latencyDeltaSeconds > 0 ? "+" : ""}${row.latencyDeltaSeconds.toFixed(2)}s`
                            : "N/A"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
              Import at least two runs to unlock comparison mode.
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}

export default EvalDashboard;
