import { useEffect, useRef } from "react";

import { INPUT_MODES } from "../utils";

export default function InputPanel({
  mode,
  onModeChange,
  claimText,
  onClaimTextChange,
  selectedPreamble,
  onSelectedPreambleChange,
  preambleSuggestions,
  onSearch,
  onRunPipeline,
  busy,
  workflowState,
}) {
  const textareaRef = useRef(null);
  const datalistId = "preamble-suggestions";

  useEffect(() => {
    if (!textareaRef.current) {
      return;
    }
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.max(textareaRef.current.scrollHeight, 96)}px`;
  }, [claimText]);

  const activeMode = INPUT_MODES.find((item) => item.value === mode) || INPUT_MODES[0];
  const isSearching = workflowState === "searching";
  const isFormalizing = workflowState === "formalizing";

  return (
    <section className="panel flex h-full flex-col gap-4">
      <div>
        <p className="panel-title">Panel A</p>
        <h2 className="mt-2 text-xl font-semibold">Input</h2>
      </div>

      <div className="flex flex-wrap gap-2 rounded-full border border-white/10 bg-black/10 p-1">
        {INPUT_MODES.map((item) => {
          const active = item.value === mode;
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => onModeChange(item.value)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                active ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5"
              }`}
            >
              {item.shortLabel}
            </button>
          );
        })}
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium subtle-text" htmlFor="claim-input">
          Claim
        </label>
        <textarea
          id="claim-input"
          ref={textareaRef}
          className="input-shell min-h-[96px] resize-none"
          placeholder={activeMode.placeholder}
          value={claimText}
          onChange={(event) => onClaimTextChange(event.target.value)}
        />
        <p className="text-xs subtle-text">
          {mode === "lean"
            ? "Raw Lean still goes through review before it is queued for proving."
            : "Verify Full Pipeline runs search and formalization, then pauses in review until you approve the theorem."}
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium subtle-text" htmlFor="preamble-input">
          Preambles (optional)
        </label>
        <input
          id="preamble-input"
          list={datalistId}
          className="input-shell"
          placeholder="crra_utility"
          value={selectedPreamble}
          onChange={(event) => onSelectedPreambleChange(event.target.value)}
        />
        <datalist id={datalistId}>
          {preambleSuggestions.map((suggestion) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>
      </div>

      <div className="mt-auto flex flex-wrap gap-3">
        <button
          type="button"
          className="secondary-button"
          onClick={onSearch}
          disabled={!claimText.trim() || busy}
        >
          {isSearching ? "Searching..." : "Search"}
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={onRunPipeline}
          disabled={!claimText.trim() || busy}
        >
          {isFormalizing ? "Formalizing..." : "Verify Full Pipeline"}
        </button>
      </div>
    </section>
  );
}
