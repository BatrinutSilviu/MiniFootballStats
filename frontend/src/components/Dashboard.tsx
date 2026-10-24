import { useEffect, useMemo, useState } from "react";
import { getResults } from "../api";
import type { MatchResults } from "../types";
import PitchHeatmap from "./PitchHeatmap";
import PossessionChart from "./PossessionChart";

const TEAM_LABELS: Record<string, string> = { team_a: "Team A", team_b: "Team B" };

export default function Dashboard({ matchId }: { matchId: string }) {
  const [results, setResults] = useState<MatchResults | null>(null);
  const [selection, setSelection] = useState<string>("team_a");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getResults(matchId)
      .then(setResults)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load results"));
  }, [matchId]);

  const heatmapGrid = useMemo(() => {
    if (!results) return null;
    if (selection === "team_a" || selection === "team_b") {
      const players = results.players.filter((p) => p.team === selection);
      if (players.length === 0) return null;
      const rows = players[0].heatmap.length;
      const cols = players[0].heatmap[0].length;
      const grid = Array.from({ length: rows }, () => Array(cols).fill(0));
      for (const p of players) {
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) grid[r][c] += p.heatmap[r][c];
        }
      }
      const max = Math.max(...grid.flat(), 1);
      return grid.map((row) => row.map((v) => v / max));
    }
    const player = results.players.find((p) => String(p.track_id) === selection);
    return player?.heatmap ?? null;
  }, [results, selection]);

  if (error) return <p className="error">{error}</p>;
  if (!results) return <p className="hint">Loading results…</p>;

  return (
    <div className="dashboard">
      <p className="hint">
        {results.frame_sample_count} sampled frames over {Math.round(results.duration_s)}s ·
        stats are estimates from a single fixed camera, treat as directional rather than exact.
      </p>

      <div className="team-cards">
        {(["team_a", "team_b"] as const).map((team) => {
          const t = results.teams[team];
          if (!t) return null;
          return (
            <div key={team} className="card team-card">
              <h3>{TEAM_LABELS[team]}</h3>
              <div className="stat-row">
                <span>Possession</span>
                <strong>{t.possession_pct}%</strong>
              </div>
              <div className="stat-row">
                <span>Distance covered</span>
                <strong>{Math.round(t.distance_m)} m</strong>
              </div>
              <div className="stat-row">
                <span>Passes (est.)</span>
                <strong>{t.passes}</strong>
              </div>
              <div className="stat-row">
                <span>Turnovers (est.)</span>
                <strong>{t.turnovers}</strong>
              </div>
            </div>
          );
        })}
      </div>

      <div className="card">
        <h3>Possession over time</h3>
        <PossessionChart timeline={results.possession_timeline} />
      </div>

      <div className="card heatmap-card">
        <div className="heatmap-header">
          <h3>Positional heatmap</h3>
          <select value={selection} onChange={(e) => setSelection(e.target.value)}>
            <option value="team_a">Team A (all)</option>
            <option value="team_b">Team B (all)</option>
            {results.players.map((p) => (
              <option key={p.track_id} value={String(p.track_id)}>
                Player #{p.track_id} ({TEAM_LABELS[p.team] ?? p.team})
              </option>
            ))}
          </select>
        </div>
        {heatmapGrid ? (
          <PitchHeatmap grid={heatmapGrid} lengthM={results.pitch.length_m} widthM={results.pitch.width_m} />
        ) : (
          <p className="hint">No position data for this selection.</p>
        )}
      </div>

      <div className="card">
        <h3>Players</h3>
        <table className="player-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Team</th>
              <th>Distance</th>
              <th>Avg speed</th>
              <th>Top speed</th>
            </tr>
          </thead>
          <tbody>
            {results.players.map((p) => (
              <tr key={p.track_id}>
                <td>{p.track_id}</td>
                <td>{TEAM_LABELS[p.team] ?? p.team}</td>
                <td>{Math.round(p.distance_m)} m</td>
                <td>{p.avg_speed_kmh} km/h</td>
                <td>{p.max_speed_kmh} km/h</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
