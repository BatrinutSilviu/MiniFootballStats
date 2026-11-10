import type { RecordingTip } from "../types";

const ICON: Record<RecordingTip["severity"], string> = { high: "●", medium: "●", low: "●", ok: "✓" };

export default function RecordingTips({ tips }: { tips: RecordingTip[] | undefined }) {
  if (!tips?.length) return null;
  return (
    <div className="card">
      <h3>Filming tips for the next match</h3>
      <p className="hint">Based on what made this video hard to analyze. Better footage = more accurate stats.</p>
      <ul className="tips">
        {tips.map((t) => (
          <li key={t.title} className={`tip tip-${t.severity}`}>
            <span className="tip-icon">{ICON[t.severity]}</span>
            <div>
              <strong>{t.title}</strong>
              <p>{t.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
