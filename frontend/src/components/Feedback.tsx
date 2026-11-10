import type { Insight, MatchResults } from "../types";
import TeamName from "./TeamName";

function InsightItem({ item, kind }: { item: Insight; kind: "strength" | "lesson" }) {
  return (
    <li className={`insight insight-${kind}`}>
      <div className="insight-head">
        <strong>{item.title}</strong>
        <span className={`confidence confidence-${item.confidence}`} title="How sure we are, given the data">
          {item.confidence} confidence
        </span>
      </div>
      <p>{item.detail}</p>
      <p className="evidence">{item.evidence}</p>
      {item.drill && (
        <p className="drill">
          <span>Drill</span> {item.drill}
        </p>
      )}
    </li>
  );
}

export default function Feedback({ results }: { results: MatchResults }) {
  const { insights, team_colors } = results;
  return (
    <div className="card">
      <h3>Coaching feedback</h3>
      {insights.notes.length > 0 && (
        <ul className="notes">
          {insights.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <div className="feedback-grid">
        {(["team_a", "team_b"] as const).map((team) => {
          const t = insights[team];
          return (
            <div key={team}>
              <h4>
                <TeamName team={team} colors={team_colors} />
              </h4>
              <h5 className="strength-label">Strengths</h5>
              {t.strengths.length ? (
                <ul className="insights">
                  {t.strengths.map((i) => (
                    <InsightItem key={i.title} item={i} kind="strength" />
                  ))}
                </ul>
              ) : (
                <p className="hint">Nothing stood out clearly from the data.</p>
              )}
              <h5 className="lesson-label">Lessons to learn</h5>
              {t.lessons.length ? (
                <ul className="insights">
                  {t.lessons.map((i) => (
                    <InsightItem key={i.title} item={i} kind="lesson" />
                  ))}
                </ul>
              ) : (
                <p className="hint">No clear weak spots found in the data.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
