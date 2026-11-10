import { useEffect, useState } from "react";

/** Plays a rendered clip; the server renders it on first request, which takes a few seconds. */
export default function VideoModal({
  src,
  downloads,
  title,
  onClose,
}: {
  src: string;
  downloads: { label: string; href: string }[];
  title: string;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="card-header">
          <h3>{title}</h3>
          <button className="secondary" onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        {loading && !error && <p className="hint">Rendering the clip… (a few seconds the first time)</p>}
        {error && <p className="error">The clip could not be rendered. Is ffmpeg installed on the server?</p>}
        <video
          className="clip-video"
          src={src}
          controls
          autoPlay
          playsInline
          style={{ display: loading || error ? "none" : "block" }}
          onLoadedData={() => setLoading(false)}
          onError={() => setError(true)}
        />
        {!loading && !error && (
          <div className="modal-actions">
            {downloads.map((d, i) => (
              <a key={d.href} className={`button ${i === 0 ? "primary" : "secondary"}`} href={d.href} download>
                {d.label}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
