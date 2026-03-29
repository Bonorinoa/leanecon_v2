import { useState } from "react";

function PillList({ items }) {
  if (!items?.length) {
    return <p className="text-sm subtle-text">None</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span key={item} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs">
          {item}
        </span>
      ))}
    </div>
  );
}

export default function SearchContext({ context }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!context) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 px-4 py-3 text-sm subtle-text">
        Search context will appear here after retrieval or formalization.
      </div>
    );
  }

  const summary = [
    `${context.preambleMatches.length} preambles`,
    `${context.curatedHints.length} hint bundles`,
    `${context.candidateImports.length} candidate imports`,
  ].join(" • ");

  return (
    <div className="rounded-2xl border border-white/10 bg-black/10">
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div>
          <p className="text-sm font-semibold">Search Context</p>
          <p className="text-xs subtle-text">{summary}</p>
        </div>
        <span className="text-xs subtle-text">{isOpen ? "Hide" : "Show"}</span>
      </button>

      {isOpen ? (
        <div className="space-y-4 border-t border-white/10 px-4 py-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold">Preamble Matches</p>
            {context.preambleMatches.length ? (
              <div className="space-y-2">
                {context.preambleMatches.map((match) => (
                  <div
                    key={`${match.name}-${match.path || "none"}`}
                    className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium">{match.name}</span>
                      <span className="text-xs subtle-text">score {match.score}</span>
                    </div>
                    <p className="mt-1 text-xs subtle-text">{match.reason}</p>
                    {match.path ? <p className="mt-1 text-xs subtle-text">{match.path}</p> : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm subtle-text">No matched preambles yet.</p>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Curated Hints</p>
            {context.curatedHints.length ? (
              <div className="space-y-2">
                {context.curatedHints.map((hint) => (
                  <div key={hint.name} className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                    <p className="font-medium">{hint.name}</p>
                    <p className="mt-1 text-xs subtle-text">{hint.description}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm subtle-text">No curated hints available.</p>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Candidate Imports</p>
            <PillList items={context.candidateImports} />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Candidate Identifiers</p>
            <PillList items={context.candidateIdentifiers} />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Retrieval Notes</p>
            <PillList items={context.notes} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
