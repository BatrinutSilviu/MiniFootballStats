import { useEffect, useState } from "react";
import { getMatch, retryMatch } from "../api";
import type { MatchMeta, MatchStatus } from "../types";

const STATUS_TEXT: Partial<Record<MatchStatus, string>> = {
  queued: "Waiting for another video to finish…",
  analyzing: "Detecting players and ball, following the camera…",
  computing: "Computing stats, events and feedback…",
};

export default function Processing({
  matchId,
  onFinished,
}: {
  matchId: string;
  onFinished: (status: MatchStatus) => void;
}) {
  const [meta, setMeta] = useState<MatchMeta | null>(null);
  const [pollKey, setPollKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const m = await getMatch(matchId);
        if (cancelled) return;
        setMeta(m);
        if (m.status === "awaiting_calibration" || m.status === "done") {
          onFinished(m.status);
          return;
        }
        if (m.status === "error") return;
      } catch {
        // backend briefly unreachable: keep polling
      }
      if (!cancelled) timer = window.setTimeout(tick, 1500);
    };
    tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [matchId, onFinished, pollKey]);

  async function retry() {
    await retryMatch(matchId);
    setMeta(null);
    setPollKey((k) => k + 1);
  }

  const pct = Math.round((meta?.progress ?? 0) * 100);
  const computing = meta?.status === "computing";

  return (
    <div className="card">
      <h2>Analyzing match…</h2>
      <p className="hint">
        The video is processed on this computer; on a laptop CPU this can take a while for longer
        clips. You can leave this page and come back from “Past matches”.
      </p>
      {meta?.status === "error" ? (
        <>
          <p className="error">Processing failed: {meta.error}</p>
          <button className="primary" onClick={retry}>
            Retry
          </button>
        </>
      ) : (
        <>
          {!computing && (
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
          )}
          <p className="hint">
            {meta ? STATUS_TEXT[meta.status] ?? meta.status : "…"}
            {meta?.status === "analyzing" && ` ${pct}%`}
          </p>
        </>
      )}
    </div>
  );
}
