import { useEffect, useState } from "react";
import { createCoachReport, getFeatures } from "../api";
import type { CoachReport, MatchResults } from "../types";
import TeamName from "./TeamName";

export default function CoachReportCard({ matchId, results }: { matchId: string; results: MatchResults }) {
  const [enabled, setEnabled] = useState(false);
  const [report, setReport] = useState<CoachReport | undefined>(results.coach_report);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFeatures()
      .then((f) => setEnabled(f.coach_report))
      .catch(() => setEnabled(false));
  }, []);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setReport(await createCoachReport(matchId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not create the report");
    } finally {
      setBusy(false);
    }
  }

  if (!enabled && !report) return null;

  return (
    <div className="card">
      <div className="card-header">
        <h3>Coach's report</h3>
        {enabled && (
          <button className="primary" onClick={generate} disabled={busy}>
            {busy ? "Writing…" : report ? "Rewrite" : "Write with Claude"}
          </button>
        )}
      </div>
      {!report && !busy && (
        <p className="hint">
          Turns the stats above into a written report with strengths, lessons and drills for each
          team. Sends the computed stats (no video) to the Claude API.
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {report?.stale && (
        <p className="warning">Written before the stats were last recomputed (corrections or new pitch corners) — rewrite to update it.</p>
      )}
      {report && (
        <div className="coach-report">
          <p>{report.summary}</p>
          {report.teams.map((t) => (
            <div key={t.team}>
              <h4>
                <TeamName team={t.team} colors={results.team_colors} /> — {t.headline}
              </h4>
              <ul>
                {t.strengths.map((s) => (
                  <li key={s.title}>
                    <strong className="strength-label">✓ {s.title}.</strong> {s.explanation}
                  </li>
                ))}
                {t.lessons.map((l) => (
                  <li key={l.title}>
                    <strong className="lesson-label">↗ {l.title}.</strong> {l.explanation}
                    <p className="drill">
                      <span>Drill</span> {l.drill}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {report.caveats.length > 0 && <p className="hint">{report.caveats.join(" ")}</p>}
          <p className="hint">Written by {report.model}.</p>
        </div>
      )}
    </div>
  );
}
