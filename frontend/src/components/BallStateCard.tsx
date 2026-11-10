import { useMemo } from "react";
import { reviewFrameUrl } from "../api";
import { STATE_META, type StateKey } from "../ballStates";
import type { BallSample, MatchResults } from "../types";

const ORDER: StateKey[] = ["keeper", "ground", "air", "out", "unknown"];

function stateAt(track: (BallSample | null)[], i: number): StateKey {
  return track[i]?.state ?? "unknown";
}

function clock(t: number): string {
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
}

export default function BallStateCard({
  matchId,
  results,
  version,
  index,
  onIndex,
}: {
  matchId: string;
  results: MatchResults;
  version?: string;
  index: number | null;
  onIndex: (i: number) => void;
}) {
  const track = results.ball_track;
  const s = results.ball_summary;

  const runs = useMemo(() => {
    const out: { state: StateKey; start: number; len: number }[] = [];
    track.forEach((_, i) => {
      const st = stateAt(track, i);
      const last = out[out.length - 1];
      if (last && last.state === st) last.len += 1;
      else out.push({ state: st, start: i, len: 1 });
    });
    return out;
  }, [track]);

  function jumpChange(dir: 1 | -1) {
    if (index === null) return;
    const here = stateAt(track, index);
    let i = index + dir;
    while (i >= 0 && i < track.length && stateAt(track, i) === here) i += dir;
    if (i >= 0 && i < track.length) onIndex(i);
  }

  const pct: Record<StateKey, number> = {
    keeper: s.keeper_pct,
    ground: s.ground_pct,
    air: s.air_pct,
    out: s.out_pct,
    unknown: s.unknown_pct,
  };
  const current = index !== null ? track[index] : null;
  const total = track.length || 1;

  return (
    <div className="card">
      <h3>Ball state</h3>
      <div className="state-legend">
        {ORDER.map((k) => (
          <span key={k} className="state-chip">
            <span className="swatch" style={{ background: STATE_META[k].color }} />
            {STATE_META[k].label} <strong>{pct[k]}%</strong>
          </span>
        ))}
      </div>
      <p className="hint">
        Ball in play {s.in_play_pct}% of the time · went out {s.outs} times ({s.restarts.kick_in} kick-ins,{" "}
        {s.restarts.corner} corners, {s.restarts.goal_clearance} goal clearances) · keeper held it{" "}
        {s.keeper_holds} times. Click the strip to check any moment against the video.
      </p>

      <div
        className="state-strip"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          onIndex(Math.min(track.length - 1, Math.max(0, Math.floor(((e.clientX - rect.left) / rect.width) * track.length))));
        }}
      >
        {runs.map((r) => (
          <div
            key={r.start}
            className="state-run"
            style={{
              left: `${(r.start / total) * 100}%`,
              width: `${(r.len / total) * 100}%`,
              background: STATE_META[r.state].color,
            }}
            title={`${clock(results.possession_timeline[r.start]?.t ?? 0)} ${STATE_META[r.state].label}`}
          />
        ))}
        {index !== null && <div className="state-cursor" style={{ left: `${((index + 0.5) / total) * 100}%` }} />}
      </div>

      {index !== null && (
        <div className="review">
          <div className="review-controls">
            <button className="secondary" onClick={() => jumpChange(-1)} title="previous change of state">
              ⇤
            </button>
            <button className="secondary" onClick={() => onIndex(Math.max(0, index - 1))} title="previous frame">
              ←
            </button>
            <span className="review-label">
              {clock(results.possession_timeline[index]?.t ?? 0)} ·{" "}
              <strong style={{ color: STATE_META[stateAt(track, index)].color }}>
                {STATE_META[stateAt(track, index)].label}
              </strong>
              {current?.src === "inferred" && <span className="hint"> (ball hidden — inferred)</span>}
            </span>
            <button className="secondary" onClick={() => onIndex(Math.min(track.length - 1, index + 1))} title="next frame">
              →
            </button>
            <button className="secondary" onClick={() => jumpChange(1)} title="next change of state">
              ⇥
            </button>
          </div>
          <img className="review-frame" src={reviewFrameUrl(matchId, index, version)} alt="video frame with detections" />
          <p className="hint">
            Boxes: players in their team color (GK = goalkeeper, grey = referee/other); faint boxes are
            every ball candidate the detector proposed; the circle is the ball the tracker chose.
          </p>
        </div>
      )}
    </div>
  );
}
