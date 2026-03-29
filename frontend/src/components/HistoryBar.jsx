import { getHistoryIcon, truncateClaim } from "../utils";

export default function HistoryBar({ entries, activeId, onSelect }) {
  return (
    <section className="panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="panel-title">History</p>
          <p className="mt-1 text-sm subtle-text">Recent verification attempts</p>
        </div>

        {entries.length === 0 ? (
          <p className="text-sm subtle-text">No verification attempts yet.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {entries.map((entry) => {
              const active = entry.id === activeId;
              return (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => onSelect(entry)}
                  className={`rounded-full border px-4 py-2 text-sm transition ${
                    active
                      ? "border-blue-400/40 bg-blue-500/10 text-white"
                      : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                  }`}
                >
                  {truncateClaim(entry.claimText)} {getHistoryIcon(entry.job)}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
