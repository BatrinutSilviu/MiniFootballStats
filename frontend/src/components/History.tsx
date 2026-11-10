import { useEffect, useState } from "react";
import { deleteMatch, listMatches } from "../api";
import type { MatchMeta, MatchStatus } from "../types";

const STATUS_LABELS: Record<MatchStatus, string> = {
  queued: "queued",
  analyzing: "analyzing",
  awaiting_calibration: "mark pitch",
  computing: "computing",
  done: "done",
  error: "error",
};

export default function History({
  onSelect,
  onDeleted,
  refreshKey,
}: {
  onSelect: (matchId: string) => void;
  onDeleted: (matchId: string) => void;
  refreshKey: number;
}) {
  const [matches, setMatches] = useState<MatchMeta[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMatches().then(setMatches).catch(() => {});
  }, [refreshKey]);

  async function remove(m: MatchMeta) {
    if (!window.confirm(`Delete "${m.title || m.video_filename}"? The video and all its stats are removed for good.`)) return;
    setError(null);
    try {
      await deleteMatch(m.id);
      setMatches((ms) => ms.filter((x) => x.id !== m.id));
      onDeleted(m.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not delete");
    }
  }

  if (matches.length === 0) return null;

  return (
    <div className="history">
      <h3>Past matches</h3>
      <ul>
        {matches.map((m) => (
          <li key={m.id} className="history-item">
            <button onClick={() => onSelect(m.id)}>
              <span className="history-name">{m.title || m.video_filename}</span>
              <span className={`status status-${m.status}`}>{STATUS_LABELS[m.status] ?? m.status}</span>
            </button>
            <button className="history-delete" title="delete this match" onClick={() => remove(m)}>
              ✕
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
