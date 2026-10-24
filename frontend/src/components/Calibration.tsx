import { useState } from "react";
import { calibrateMatch, firstFrameUrl } from "../api";

const CORNER_LABELS = ["Top-left", "Top-right", "Bottom-right", "Bottom-left"];

export default function Calibration({
  matchId,
  onCalibrated,
}: {
  matchId: string;
  onCalibrated: () => void;
}) {
  const [points, setPoints] = useState<number[][]>([]);
  const [lengthM, setLengthM] = useState(40);
  const [widthM, setWidthM] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [naturalSize, setNaturalSize] = useState({ w: 1, h: 1 });
  const [displaySize, setDisplaySize] = useState({ w: 1, h: 1 });

  function handleClick(e: React.MouseEvent<HTMLImageElement>) {
    if (points.length >= 4) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = naturalSize.w / rect.width;
    const scaleY = naturalSize.h / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    setPoints([...points, [x, y]]);
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

  return (
    <div className="card calibration-card">
      <h2>Calibrate the pitch</h2>
      <p className="hint">
        Click the 4 corners of the pitch in this order:{" "}
        <strong>{CORNER_LABELS[points.length] ?? "done"}</strong>. This lets us convert player
        positions from pixels into real-world meters (distance, speed, heatmaps).
      </p>

      <div className="frame-wrap">
        <img
          src={firstFrameUrl(matchId)}
          alt="first frame"
          onLoad={(e) => {
            const img = e.currentTarget;
            setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
            setDisplaySize({ w: img.clientWidth, h: img.clientHeight });
          }}
          onClick={handleClick}
        />
        {points.map((p, i) => (
          <div
            key={i}
            className="corner-marker"
            style={{
              left: (p[0] / naturalSize.w) * displaySize.w - 6,
              top: (p[1] / naturalSize.h) * displaySize.h - 6,
            }}
          >
            {i + 1}
          </div>
        ))}
      </div>

      <div className="calibration-form">
        <label>
          Pitch length (m)
          <input
            type="number"
            value={lengthM}
            onChange={(e) => setLengthM(Number(e.target.value))}
          />
        </label>
        <label>
          Pitch width (m)
          <input type="number" value={widthM} onChange={(e) => setWidthM(Number(e.target.value))} />
        </label>
        <button onClick={() => setPoints([])} disabled={points.length === 0}>
          Reset points
        </button>
        <button onClick={submit} disabled={points.length !== 4 || busy}>
          {busy ? "Starting…" : "Start analysis"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
