import { useState } from "react";
import { playerLabel, useLabels } from "../labels";
import type { Corrections, MatchResults, PlayerLabel, PlayerStats } from "../types";
import TeamName from "./TeamName";

function NameCell({ label, onSave }: { label: PlayerLabel | undefined; onSave: (l: PlayerLabel) => void }) {
  const [name, setName] = useState(label?.name ?? "");
  const [number, setNumber] = useState(label?.number?.toString() ?? "");

  const commit = () => {
    const n = number.trim() === "" ? null : Number(number);
    const clean = { name: name.trim(), number: n !== null && Number.isFinite(n) ? Math.round(n) : null };
    if (clean.name !== (label?.name ?? "") || clean.number !== (label?.number ?? null)) onSave(clean);
  };
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => e.key === "Enter" && e.currentTarget.blur();
  return (
    <span className="name-cell">
      <input className="name-input" placeholder="Who is this?" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} onBlur={commit} onKeyDown={onKey} />
      <input className="number-input" placeholder="No." value={number} inputMode="numeric" maxLength={3} onChange={(e) => setNumber(e.target.value.replace(/\D/g, ""))} onBlur={commit} onKeyDown={onKey} />
    </span>
  );
}

export default function PlayersTable({
  results,
  busy,
  onRenamePlayer,
  onCorrect,
  onOpenProfile,
}: {
  results: MatchResults;
  busy: boolean;
  onRenamePlayer: (tid: number, label: PlayerLabel) => void;
  onCorrect: (next: Corrections) => void;
  onOpenProfile: (name: string) => void;
}) {
  const labels = useLabels();
  const merges = Object.entries(results.corrections.track_merges);

  function merge(p: PlayerStats, into: number) {
    onCorrect({ ...results.corrections, track_merges: { ...results.corrections.track_merges, [String(p.track_id)]: into } });
  }
  function unmerge(src: string) {
    const next = { ...results.corrections.track_merges };
    delete next[src];
    onCorrect({ ...results.corrections, track_merges: next });
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Players</h3>
        {busy && <span className="hint">Updating stats…</span>}
      </div>
      <p className="hint">
        Numbers are tracking IDs, not shirt numbers. <strong>Name yourself</strong> (use the ball-state review above to see
        who is who) to build your profile across matches. A player who left the view and came back gets a new ID — use
        "same player as" to join them. Compare running by m/min: players are only measured while in view.
      </p>
      <div className="table-scroll">
        <table className="player-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name / no.</th>
              <th>Team</th>
              <th>In view</th>
              <th>m/min</th>
              <th>Top speed</th>
              <th>Passes</th>
              <th>Shots · goals</th>
              <th>Same player as</th>
            </tr>
          </thead>
          <tbody>
            {results.players.map((p) => {
              const label = labels.player_names[String(p.track_id)];
              const sameTeam = results.players.filter((o) => o.track_id !== p.track_id && o.team === p.team);
              return (
                <tr key={p.track_id}>
                  <td>
                    {p.track_id}
                    {p.role === "goalkeeper" && <span className="tag">GK</span>}
                  </td>
                  <td>
                    <NameCell key={`${label?.name ?? ""}|${label?.number ?? ""}`} label={label} onSave={(l) => onRenamePlayer(p.track_id, l)} />
                    {label?.name && (
                      <button className="link-inline" onClick={() => onOpenProfile(label.name)} title="open player card">
                        card ›
                      </button>
                    )}
                  </td>
                  <td>
                    <TeamName team={p.team} colors={results.team_colors} />
                  </td>
                  <td>{Math.round(p.observed_s)} s</td>
                  <td>{p.m_per_min}</td>
                  <td>{p.max_speed_kmh} km/h</td>
                  <td>{p.role === "goalkeeper" ? `${p.saves} saves` : p.passes}</td>
                  <td>
                    {p.shots} · {p.goals}
                  </td>
                  <td>
                    <select
                      value=""
                      disabled={busy || sameTeam.length === 0}
                      onChange={(e) => e.target.value && merge(p, Number(e.target.value))}
                      title="this track is the same person as another one"
                    >
                      <option value="">—</option>
                      {sameTeam.map((o) => (
                        <option key={o.track_id} value={o.track_id}>
                          {playerLabel(labels, o.track_id)}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {merges.length > 0 && (
        <div className="removed">
          <span className="hint">Joined tracks:</span>
          {merges.map(([src, dst]) => (
            <button key={src} className="chip" disabled={busy} onClick={() => unmerge(src)} title="split again">
              #{src} → {playerLabel(labels, dst)} ↺
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
