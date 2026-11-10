import { useEffect, useMemo, useState } from "react";
import { getFeatures, getResults, updateCorrections, updateLabels } from "../api";
import { LabelsContext, playerLabel, teamLabel } from "../labels";
import type { Corrections, Features, Labels, MatchResults, PlayerLabel, TeamStats } from "../types";
import BallStateCard from "./BallStateCard";
import CoachReportCard from "./CoachReportCard";
import Feedback from "./Feedback";
import Highlights from "./Highlights";
import KeyMoments from "./KeyMoments";
import PitchHeatmap from "./PitchHeatmap";
import PlayersTable from "./PlayersTable";
import PossessionChart from "./PossessionChart";
import RecordingTips from "./RecordingTips";
import Scoreboard from "./Scoreboard";
import TeamName from "./TeamName";

const pct = (v: number | null) => (v === null ? "–" : `${v}%`);
const num = (v: number | null, unit = "") => (v === null ? "–" : `${v}${unit}`);

function teamRows(t: TeamStats): [string, string][] {
  return [
    ["Possession", pct(t.possession_pct)],
    ["Passes (est.)", `${t.passes} · ${pct(t.pass_accuracy_pct)} kept`],
    ["Turnovers (est.)", `${t.turnovers}${t.turnovers_own_third ? ` · ${t.turnovers_own_third} in own third` : ""}`],
    ["Shots", `${t.shots} · ${t.shots_on_target} on target`],
    ["Goals (likely)", String(t.goals)],
    ["Ball out of play (last touch)", String(t.balls_out)],
    ["Time to win the ball back", num(t.avg_recovery_s, " s")],
    ["Running", t.m_per_min === null ? "–" : `${t.m_per_min} m/min per player`],
    ["Width with the ball", num(t.width_in_possession_m, " m")],
    ["Length without the ball", num(t.depth_out_of_possession_m, " m")],
    [
      "Ball in own / middle / attacking third",
      t.territory_pct ? `${t.territory_pct.defensive} / ${t.territory_pct.middle} / ${t.territory_pct.attacking}%` : "–",
    ],
  ];
}

function keeperRows(t: TeamStats): [string, string][] {
  const k = t.keeper;
  return [
    ["Ball held in the hands", `${k.handlings}${k.handlings ? ` · ${k.hold_s} s in total` : ""}`],
    ["Saves", `${k.saves}${k.save_pct !== null ? ` · ${k.save_pct}% of shots on target` : ""}`],
    ["Goals conceded (likely)", String(t.goals_conceded)],
    ["Distribution", k.distributions ? `${pct(k.distribution_success_pct)} to a teammate (${k.distributions})` : "–"],
    ["Played outside the area", String(k.touches_outside_area)],
  ];
}

export default function Dashboard({
  matchId,
  onRecalibrate,
  onOpenProfile,
  onRenamed,
}: {
  matchId: string;
  onRecalibrate: () => void;
  onOpenProfile: (name: string) => void;
  onRenamed: () => void;
}) {
  const [results, setResults] = useState<MatchResults | null>(null);
  const [labels, setLabels] = useState<Labels | null>(null);
  const [features, setFeatures] = useState<Features | null>(null);
  const [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState<string>("team_a");
  const [error, setError] = useState<string | null>(null);
  const [reviewIndex, setReviewIndex] = useState<number | null>(null);
  const [version, setVersion] = useState<string>();

  useEffect(() => {
    getResults(matchId)
      .then((r) => {
        setResults(r);
        setLabels(r.labels);
        setVersion(String(Date.now()));  // results may have been recomputed: don't reuse cached review frames
      })
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load results"));
    getFeatures()
      .then(setFeatures)
      .catch(() => setFeatures(null));
  }, [matchId]);

  async function rename(change: { title?: string; team_names?: Record<string, string>; player_names?: Record<string, PlayerLabel> }) {
    setError(null);
    try {
      setLabels(await updateLabels(matchId, change));
      setVersion(String(Date.now()));  // clip banners show the names
      onRenamed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not save the name");
    }
  }

  function renamePlayer(tid: number, label: PlayerLabel) {
    if (!labels) return;
    const next = { ...labels.player_names };
    if (label.name || label.number !== null) next[String(tid)] = label;
    else delete next[String(tid)];
    rename({ player_names: next });
  }

  async function correct(next: Corrections) {
    setBusy(true);
    setError(null);
    try {
      const r = await updateCorrections(matchId, next);
      setResults(r);
      setLabels(r.labels);
      setVersion(String(Date.now()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not apply the correction");
    } finally {
      setBusy(false);
    }
  }

  const heatmapGrid = useMemo(() => {
    if (!results) return null;
    if (selection in results.team_heatmaps) return results.team_heatmaps[selection];
    return results.players.find((p) => String(p.track_id) === selection)?.heatmap ?? null;
  }, [results, selection]);

  if (!results || !labels) return error ? <p className="error">{error}</p> : <p className="hint">Loading results…</p>;

  const q = results.quality;
  return (
    <LabelsContext.Provider value={labels}>
    <div className="dashboard">
      {error && <p className="error">{error}</p>}
      <Scoreboard results={results} labels={labels} onRename={rename} />
      <div className="dashboard-header">
        <p className="hint">
          {Math.round(results.duration_s / 60)} min analyzed · camera followed in{" "}
          {Math.round(q.camera_registration_rate * 100)}% of frames · ball seen in{" "}
          {Math.round(q.ball_detected_rate * 100)}% · {q.goalkeepers_found} goalkeeper
          {q.goalkeepers_found === 1 ? "" : "s"} found. All numbers are estimates from video.
        </p>
        <button className="secondary" onClick={onRecalibrate}>
          Re-mark pitch corners
        </button>
      </div>

      <BallStateCard
        matchId={matchId}
        results={results}
        version={version}
        index={reviewIndex}
        onIndex={setReviewIndex}
      />
      <Feedback results={results} />
      <CoachReportCard matchId={matchId} results={results} />

      <div className="team-cards">
        {(["team_a", "team_b"] as const).map((team) => {
          const t = results.teams[team];
          if (!t) return null;
          return (
            <div key={team} className="card team-card">
              <h3>
                <TeamName team={team} colors={results.team_colors} />
              </h3>
              {teamRows(t).map(([k, v]) => (
                <div key={k} className="stat-row">
                  <span>{k}</span>
                  <strong>{v}</strong>
                </div>
              ))}
              <h4 className="subhead">Goalkeeper</h4>
              {keeperRows(t).map(([k, v]) => (
                <div key={k} className="stat-row">
                  <span>{k}</span>
                  <strong>{v}</strong>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="card">
        <h3>Possession over time</h3>
        <p className="hint">Share of each moment's ball possession; gaps are loose balls or moments the ball wasn't seen.</p>
        <PossessionChart timeline={results.possession_timeline} colors={results.team_colors} />
      </div>

      <KeyMoments
        matchId={matchId}
        results={results}
        clipsEnabled={!!features?.clips}
        busy={busy}
        version={version}
        onCorrect={correct}
        onSelect={(t) => {
          const i = results.possession_timeline.findIndex((s) => s.t >= t);
          setReviewIndex(i < 0 ? results.possession_timeline.length - 1 : i);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      />

      <div className="card heatmap-card">
        <div className="card-header">
          <h3>Positional heatmap</h3>
          <select value={selection} onChange={(e) => setSelection(e.target.value)}>
            <option value="team_a">{teamLabel(labels, "team_a")} (all)</option>
            <option value="team_b">{teamLabel(labels, "team_b")} (all)</option>
            {results.players.map((p) => (
              <option key={p.track_id} value={String(p.track_id)}>
                {p.role === "goalkeeper" ? "Goalkeeper" : "Player"} {playerLabel(labels, p.track_id)} ({teamLabel(labels, p.team)})
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

      <PlayersTable
        results={results}
        busy={busy}
        onRenamePlayer={renamePlayer}
        onCorrect={correct}
        onOpenProfile={onOpenProfile}
      />

      {features?.clips && <Highlights matchId={matchId} watermark={features.watermark} />}
      <RecordingTips tips={results.recording_tips} />
    </div>
    </LabelsContext.Provider>
  );
}
