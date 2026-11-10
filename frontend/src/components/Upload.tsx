import { useRef, useState } from "react";
import { uploadVideo } from "../api";

export default function Upload({ onUploaded }: { onUploaded: (matchId: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const { match_id } = await uploadVideo(file);
      onUploaded(match_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card upload-card">
      <h2>Upload a match video</h2>
      <p className="hint">
        Best results with a phone on a tripod, filming from a long side of the pitch, as high as you can.
      </p>
      <details className="filming-tips">
        <summary>How to film for the best stats</summary>
        <ul>
          <li><strong>High and central:</strong> stand, balcony or a 2–3 m tripod near the halfway line.</li>
          <li><strong>Whole pitch in view</strong>, or pan slowly — no zoom jumps or cuts.</li>
          <li><strong>1080p, 30 or 60 fps</strong>, landscape. Lock the exposure and avoid filming into the sun or floodlights.</li>
          <li><strong>Different shirt colors</strong> for the two teams (bibs work), and a bright ball.</li>
          <li><strong>Ask first:</strong> let everyone on the pitch know they are being filmed.</li>
        </ul>
      </details>
      <div
        className="dropzone"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) handleFile(f);
        }}
      >
        {busy ? "Uploading…" : "Click or drop a video file here"}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
        }}
      />
      {error && <p className="error">{error}</p>}
    </div>
  );
}
