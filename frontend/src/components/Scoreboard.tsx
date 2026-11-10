import { useState } from "react";
import type { Labels, MatchResults } from "../types";
import { teamLabel } from "../labels";

function EditableText({
  value,
  placeholder,
  className,
  onSave,
}: {
  value: string;
  placeholder: string;
  className?: string;
  onSave: (v: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (!editing) {
    return (
      <button
        className={`editable ${className ?? ""}`}
        title="click to rename"
        onClick={() => {
          setDraft(value);
          setEditing(true);
        }}
      >
        {value || placeholder}
      </button>
    );
  }
  const commit = () => {
    setEditing(false);
    if (draft.trim() !== value) onSave(draft.trim());
  };
  return (
    <input
      className={`editable-input ${className ?? ""}`}
      autoFocus
      value={draft}
      maxLength={40}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setEditing(false);
      }}
    />
  );
}

export default function Scoreboard({
  results,
  labels,
  onRename,
}: {
  results: MatchResults;
  labels: Labels;
  onRename: (change: { title?: string; team_names?: Record<string, string> }) => void;
}) {
  const a = results.teams.team_a?.goals ?? 0;
  const b = results.teams.team_b?.goals ?? 0;
  const renameTeam = (team: string, name: string) => onRename({ team_names: { ...labels.team_names, [team]: name } });
  return (
    <div className="card scoreboard">
      <EditableText
        className="match-title"
        value={labels.title ?? ""}
        placeholder="Name this match (e.g. Tuesday league, week 4)"
        onSave={(v) => onRename({ title: v })}
      />
      <div className="score-row">
        {(["team_a", "score", "team_b"] as const).map((team) =>
          team === "score" ? (
            <div key="score" className="score">
              {a} <span>–</span> {b}
            </div>
          ) : (
            <div key={team} className={`score-team ${team === "team_b" ? "right" : ""}`}>
              <span className="swatch big" style={{ background: results.team_colors[team] ?? "#888" }} />
              <EditableText
                value={labels.team_names[team] ?? ""}
                placeholder={teamLabel(labels, team)}
                onSave={(v) => renameTeam(team, v)}
              />
            </div>
          ),
        )}
      </div>
      <p className="hint center">
        Likely score from detected goals — fix any wrong or missed goal under Key moments. Click a name to rename.
      </p>
    </div>
  );
}
