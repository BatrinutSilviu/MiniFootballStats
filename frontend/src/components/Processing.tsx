import { useEffect, useState } from "react";
import { getMatch } from "../api";
import type { MatchMeta } from "../types";

export default function Processing({
  matchId,
  onDone,
}: {
  matchId: string;
  onDone: () => void;
}) {
  const [meta, setMeta] = useState<MatchMeta | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const m = await getMatch(matchId);
      if (cancelled) return;
      setMeta(m);
      if (m.status === "done") {
        onDone();
        return;
      }
      if (m.status !== "error") {
        setTimeout(tick, 1500);
      }
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [matchId, onDone]);

  const pct = Math.round((meta?.progress ?? 0) * 100);

  return (
    <div className="card">
      <h2>Analyzing match…</h2>
      <p className="hint">
        Running detection + tracking on a laptop CPU can take a while for longer clips — this
        runs in the background, feel free to leave the tab open.
      </p>
      {meta?.status === "error" ? (
        <p className="error">Processing failed: {meta.error}</p>
      ) : (
        <>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="hint">{pct}% · status: {meta?.status ?? "…"}</p>
        </>
      )}
    </div>
  );
}
