import { useEffect, useState } from "react";
import { listMatches } from "../api";
import type { MatchMeta } from "../types";

export default function History({
  onSelect,
  refreshKey,
}: {
  onSelect: (matchId: string) => void;
  refreshKey: number;
}) {
  const [matches, setMatches] = useState<MatchMeta[]>([]);

  useEffect(() => {
    listMatches().then(setMatches).catch(() => {});
  }, [refreshKey]);

  if (matches.length === 0) return null;

  return (
    <div className="history">
      <h3>Past matches</h3>
      <ul>
        {matches.map((m) => (
          <li key={m.id}>
            <button onClick={() => onSelect(m.id)}>
              {m.video_filename} <span className={`status status-${m.status}`}>{m.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
