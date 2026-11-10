import { useEffect, useState } from "react";
import { listPlayers } from "../api";
import { clock } from "../labels";
import type { PlayerProfile } from "../types";
import PlayerCard from "./PlayerCard";

export default function PlayersPage({ focus, onOpenMatch }: { focus: string | null; onOpenMatch: (id: string) => void }) {
  const [profiles, setProfiles] = useState<PlayerProfile[] | null>(null);
  const [selected, setSelected] = useState<string | null>(focus);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPlayers()
      .then(setProfiles)
      .catch((e) => setError(e instanceof Error ? e.message : "could not load players"));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!profiles) return <p className="hint">Loading players…</p>;
  if (profiles.length === 0) {
    return (
      <div className="card">
        <h2>Players</h2>
        <p className="hint">
          No named players yet. Open a match and type names into the Players table — the same name in several matches
          builds one profile with a season record and a player card.
        </p>
      </div>
    );
  }

  const p = profiles.find((x) => x.name.toLowerCase() === selected?.toLowerCase()) ?? profiles[0];
  return (
    <div className="players-page">
      <div className="card">
        <h2>Players</h2>
        <div className="profile-list">
          {profiles.map((x) => (
            <button key={x.name} className={`chip ${x === p ? "active" : ""}`} onClick={() => setSelected(x.name)}>
              <strong>{x.rating.overall}</strong> {x.name}
            </button>
          ))}
        </div>
      </div>

      <div className="card profile">
        <PlayerCard profile={p} />
        <div className="profile-stats">
          <h3>
            {p.name}
            {p.number !== null && <span className="tag">#{p.number}</span>}
          </h3>
          {[
            ["Matches", `${p.matches} (${p.record.W}W ${p.record.D}D ${p.record.L}L)`],
            ["Goals · shots", `${p.goals} · ${p.shots} (${p.shots_on_target} on target)`],
            ["Passes · turnovers", `${p.passes} · ${p.turnovers}`],
            ...(p.role === "goalkeeper" || p.saves ? [["Saves", String(p.saves)]] : []),
            ["Running", `${p.m_per_min} m/min · ${Math.round(p.distance_m)} m measured`],
            ["Top speed", `${p.top_speed_kmh} km/h`],
            ["Time in view", clock(p.observed_s)],
          ].map(([k, v]) => (
            <div key={k} className="stat-row">
              <span>{k}</span>
              <strong>{v}</strong>
            </div>
          ))}
          <p className="hint small">
            The card rating is a fun summary of the estimated stats (pace from top speed, work from m/min, passing from
            passes kept, shooting from shots and goals per 10 minutes) — not a scouting grade.
          </p>
        </div>
      </div>

      <div className="card">
        <h3>Match history</h3>
        <div className="table-scroll">
          <table className="player-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Match</th>
                <th>Result</th>
                <th>Goals</th>
                <th>Shots</th>
                <th>{p.role === "goalkeeper" ? "Saves" : "Passes"}</th>
                <th>m/min</th>
                <th>Top speed</th>
              </tr>
            </thead>
            <tbody>
              {p.history.map((h) => (
                <tr key={h.match_id} className="clickable" onClick={() => onOpenMatch(h.match_id)}>
                  <td>{h.date ? new Date(h.date).toLocaleDateString() : "–"}</td>
                  <td>
                    {h.title}
                    <div className="hint small">
                      {h.team} vs {h.opponent}
                    </div>
                  </td>
                  <td>{h.result ? <span className={`result result-${h.result}`}>{h.result} {h.score}</span> : "–"}</td>
                  <td>{h.goals}</td>
                  <td>{h.shots}</td>
                  <td>{p.role === "goalkeeper" ? h.saves : h.passes}</td>
                  <td>{h.m_per_min}</td>
                  <td>{h.max_speed_kmh} km/h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
