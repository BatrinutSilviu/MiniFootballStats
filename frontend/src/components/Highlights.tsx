import { useEffect, useState } from "react";
import { getMatch, highlightsUrl, startHighlights } from "../api";
import type { ClipFormat, HighlightsStatus } from "../types";

export default function Highlights({ matchId, watermark }: { matchId: string; watermark: boolean }) {
  const [status, setStatus] = useState<HighlightsStatus | null>(null);
  const [format, setFormat] = useState<ClipFormat>("vertical");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMatch(matchId)
      .then((m) => {
        setStatus(m.highlights ?? null);
        if (m.highlights?.format) setFormat(m.highlights.format);
      })
      .catch(() => {});
  }, [matchId]);

  useEffect(() => {
    if (status?.status !== "rendering") return;
    const id = setInterval(() => {
      getMatch(matchId)
        .then((m) => setStatus(m.highlights ?? null))
        .catch(() => {});
    }, 1500);
    return () => clearInterval(id);
  }, [matchId, status?.status]);

  async function make() {
    setError(null);
    try {
      setStatus(await startHighlights(matchId, format));
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not start rendering");
    }
  }

  const rendering = status?.status === "rendering";
  const ready = status?.status === "done" && status.format === format;
  return (
    <div className="card">
      <div className="card-header">
        <h3>Highlight reel</h3>
        <div className="inline-controls">
          <select value={format} onChange={(e) => setFormat(e.target.value as ClipFormat)} disabled={rendering}>
            <option value="vertical">Vertical 9:16 (stories, TikTok)</option>
            <option value="wide">Wide 16:9</option>
          </select>
          <button className="primary" onClick={make} disabled={rendering}>
            {rendering ? `Rendering… ${Math.round((status?.progress ?? 0) * 100)}%` : ready ? "Render again" : "Make highlight reel"}
          </button>
        </div>
      </div>
      <p className="hint">
        Goals, saves and shots on target, up to 2 minutes, with the score on screen. Vertical clips follow the ball.
        {watermark && " Clips carry a small watermark."} Rename teams and players first so the banners show their names.
      </p>
      {status?.status === "error" && <p className="error">{status.error}</p>}
      {error && <p className="error">{error}</p>}
      {ready && (
        <div className={`reel ${format}`}>
          <video src={highlightsUrl(matchId, format, false, status.version)} controls playsInline className="clip-video" />
          <a className="button primary" href={highlightsUrl(matchId, format, true, status.version)} download>
            Download ({status.moments} moment{status.moments === 1 ? "" : "s"})
          </a>
        </div>
      )}
    </div>
  );
}
