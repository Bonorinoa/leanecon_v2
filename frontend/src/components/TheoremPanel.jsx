import { useMemo, useState } from "react";

import SearchContext from "./SearchContext";

function scopeBadgeClass(scope) {
  if (scope === "IN_SCOPE") {
    return "badge badge-success";
  }
  if (scope === "NEEDS_DEFINITIONS") {
    return "badge badge-warning";
  }
  if (scope === "VACUOUS") {
    return "badge badge-danger";
  }
  return "badge badge-info";
}

function renderHighlightedLine(line, keyPrefix) {
  const commentIndex = line.indexOf("--");
  const mainText = commentIndex >= 0 ? line.slice(0, commentIndex) : line;
  const commentText = commentIndex >= 0 ? line.slice(commentIndex) : "";
  const tokens = [];

  if (mainText.trimStart().startsWith("import ")) {
    tokens.push(
      <span key={`${keyPrefix}-import`} className="code-token-import">
        {mainText}
      </span>,
    );
  } else {
    const parts = mainText.split(/(\b(?:theorem|lemma|sorry)\b)/g);
    parts.forEach((part, index) => {
      if (!part) {
        return;
      }

      let className = "";
      if (part === "theorem" || part === "lemma") {
        className = "code-token-keyword";
      }
      if (part === "sorry") {
        className = "code-token-sorry";
      }

      tokens.push(
        <span key={`${keyPrefix}-${index}`} className={className}>
          {part}
        </span>,
      );
    });
  }

  if (commentText) {
    tokens.push(
      <span key={`${keyPrefix}-comment`} className="code-token-comment">
        {commentText}
      </span>,
    );
  }

  return tokens;
}

function HighlightedCode({ code }) {
  const lines = useMemo(() => String(code || "").split("\n"), [code]);

  return (
    <pre className="code-surface overflow-x-auto whitespace-pre-wrap break-words">
      {lines.map((line, index) => (
        <span key={`line-${index}`}>
          {renderHighlightedLine(line, `line-${index}`)}
          {index < lines.length - 1 ? "\n" : null}
        </span>
      ))}
    </pre>
  );
}

export default function TheoremPanel({
  theoremText,
  onTheoremTextChange,
  displayScope,
  integrityWarnings,
  searchContext,
  formalizeResponse,
  onApprove,
  busy,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const canApprove = Boolean(theoremText.trim()) && theoremText.includes("sorry") && !busy;

  return (
    <section className="panel flex h-full flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="panel-title">Panel B</p>
          <h2 className="mt-2 text-xl font-semibold">Theorem Review</h2>
        </div>

        <div className="flex items-center gap-2">
          {displayScope ? <span className={scopeBadgeClass(displayScope)}>{displayScope}</span> : null}
          <button type="button" className="secondary-button" onClick={() => setIsEditing((value) => !value)}>
            {isEditing ? "Read Only" : "Edit"}
          </button>
        </div>
      </div>

      {formalizeResponse?.message ? (
        <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm subtle-text">
          {formalizeResponse.message}
        </div>
      ) : null}

      {integrityWarnings.map((warning) => (
        <div
          key={warning.id}
          className={`rounded-2xl border px-4 py-3 text-sm ${
            warning.level === "danger"
              ? "border-red-400/30 bg-red-500/10 text-red-100"
              : "border-amber-300/30 bg-amber-500/10 text-amber-100"
          }`}
        >
          {warning.text}
        </div>
      ))}

      {theoremText && !theoremText.includes("sorry") ? (
        <div className="rounded-2xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          The displayed theorem no longer contains <code>sorry</code>. The current backend
          contract only accepts theorem stubs for <code>/verify</code>.
        </div>
      ) : null}

      <div className="flex-1">
        {theoremText ? (
          isEditing ? (
            <textarea
              className="code-surface w-full resize-none bg-transparent text-sm outline-none"
              value={theoremText}
              onChange={(event) => onTheoremTextChange(event.target.value)}
              spellCheck={false}
            />
          ) : (
            <HighlightedCode code={theoremText} />
          )
        ) : (
          <div className="code-surface flex items-center justify-center text-center subtle-text">
            Formalized Lean code will appear here after the pipeline reaches review.
          </div>
        )}
      </div>

      <SearchContext context={searchContext} />

      <div className="mt-auto flex justify-end">
        <button type="button" className="primary-button" onClick={onApprove} disabled={!canApprove}>
          {busy ? "Queueing..." : "Approve & Verify"}
        </button>
      </div>
    </section>
  );
}
