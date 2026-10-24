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
        Best results with a single fixed camera showing the whole pitch (sideline or elevated
        corner).
      </p>
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
