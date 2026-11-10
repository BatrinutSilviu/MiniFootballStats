import { useEffect, useRef, useState } from "react";
import { calibrateMatch, getMatch, panoramaUrl, suggestCorners } from "../api";
import type { MatchMeta } from "../types";

const CORNER_LABELS = ["Top-left", "Top-right", "Bottom-right", "Bottom-left"];

export default function Calibration({
  matchId,
  onCalibrated,
}: {
  matchId: string;
  onCalibrated: () => void;
}) {
  const [meta, setMeta] = useState<MatchMeta | null>(null);
  const [points, setPoints] = useState<number[][]>([]);
  const [lengthM, setLengthM] = useState(40);
  const [widthM, setWidthM] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [suggested, setSuggested] = useState<"idle" | "busy" | "found" | "none">("idle");
  const drag = useRef<{ index: number; moved: boolean } | null>(null);

  async function autoDetect() {
    setSuggested("busy");
    try {
      const c = await suggestCorners(matchId);
      if (c) setPoints(c);
      setSuggested(c ? "found" : "none");
    } catch {
      setSuggested("none");
    }
  }

  useEffect(() => {
    getMatch(matchId).then((m) => {
      setMeta(m);
      setLengthM(m.pitch_length_m);
      setWidthM(m.pitch_width_m);
      if (m.corners?.length === 4) setPoints(m.corners);
      else autoDetect();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId]);

  function toImage(e: React.PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>): number[] | null {
    if (!natural) return null;
    const rect = e.currentTarget.getBoundingClientRect();
    return [((e.clientX - rect.left) / rect.width) * natural.w, ((e.clientY - rect.top) / rect.height) * natural.h];
  }

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (drag.current?.moved) {
      drag.current = null;
      return;  // the end of a drag, not a new point
    }
    drag.current = null;
    const p = toImage(e);
    if (points.length >= 4 || !p) return;
    setPoints([...points, p]);
  }

  function handlePointerMove(e: React.PointerEvent<SVGSVGElement>) {
    const d = drag.current;
    const p = toImage(e);
    if (!d || !p) return;
    d.moved = true;
    setPoints((pts) => pts.map((q, i) => (i === d.index ? p : q)));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await calibrateMatch(matchId, points, lengthM, widthM);
      onCalibrated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "calibration failed");
      setBusy(false);
    }
  }

  const r = natural ? natural.w / 120 : 10;
  const camera = meta?.camera;

  return (
    <div className="card calibration-card">
      <h2>Mark the pitch corners</h2>
      <p className="hint">
        This is everything the camera saw during the match, stitched into one picture — the camera
        may move, it doesn't need to show the whole pitch at once. Click the 4 corners of the pitch
        in this order: <strong>{CORNER_LABELS[points.length] ?? "done"}</strong>. The goals should be
        on the left and right sides. Drag a point to adjust it.
      </p>
      {suggested === "busy" && <p className="hint">Looking for the pitch lines…</p>}
      {suggested === "found" && (
        <p className="notice">
          The corners were detected automatically — check that each point sits exactly on a pitch corner and drag it if not.
        </p>
      )}
      {suggested === "none" && <p className="hint">The pitch couldn't be found automatically — please click the corners.</p>}
      {camera && camera.registration_rate < 0.8 && (
        <p className="warning">
          The camera movement could only be followed in {Math.round(camera.registration_rate * 100)}%
          of the frames (fast pans, cuts or blur), so parts of the match will be missing from the
          stats.
        </p>
      )}

      <div className="frame-wrap">
        <img
          src={panoramaUrl(matchId, meta?.updated_at)}
          alt="stitched view of the pitch"
          onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
          onError={() => setError("The stitched pitch image could not be loaded — try re-processing the video.")}
        />
        {natural && (
          <svg
            className="frame-overlay"
            viewBox={`0 0 ${natural.w} ${natural.h}`}
            preserveAspectRatio="none"
            onClick={handleClick}
            onPointerMove={handlePointerMove}
            onPointerUp={() => {
              if (drag.current && !drag.current.moved) drag.current = null;
            }}
          >
            {points.length > 1 && (
              <polygon
                points={points.map((p) => p.join(",")).join(" ")}
                fill={points.length === 4 ? "rgba(79,179,255,0.15)" : "none"}
                stroke="#4fb3ff"
                strokeWidth={r / 4}
              />
            )}
            {points.map((p, i) => (
              <g
                key={i}
                className="corner-handle"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId);
                  drag.current = { index: i, moved: false };
                }}
              >
                <circle cx={p[0]} cy={p[1]} r={r} fill="#4fb3ff" />
                <text x={p[0]} y={p[1]} fontSize={r * 1.2} textAnchor="middle" dominantBaseline="central" fill="#06181f" fontWeight={700}>
                  {i + 1}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>

      <div className="calibration-form">
        <label>
          Pitch length (m)
          <input type="number" value={lengthM} onChange={(e) => setLengthM(Number(e.target.value))} />
        </label>
        <label>
          Pitch width (m)
          <input type="number" value={widthM} onChange={(e) => setWidthM(Number(e.target.value))} />
        </label>
        <button onClick={() => setPoints(points.slice(0, -1))} disabled={points.length === 0}>
          Undo point
        </button>
        <button onClick={() => setPoints([])} disabled={points.length === 0}>
          Reset
        </button>
        <button onClick={autoDetect} disabled={suggested === "busy"}>
          Auto-detect
        </button>
        <button className="primary" onClick={submit} disabled={points.length !== 4 || busy}>
          {busy ? "Starting…" : "Compute stats"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
