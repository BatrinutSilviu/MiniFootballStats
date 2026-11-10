import { useState } from "react";
import { clipUrl } from "../api";
import { clock, parseClock, playerLabel, teamLabel, useLabels } from "../labels";
import type { Corrections, Labels, MatchEvent, MatchResults, ShotOutcome } from "../types";
import TeamName from "./TeamName";
import VideoModal from "./VideoModal";

const OUTCOME_TEXT: Record<ShotOutcome, string> = {
  goal: "Goal",
  saved: "Saved by the keeper",
  blocked: "Blocked",
  off_target: "Off target",
  unknown: "On target, outcome unclear",
};

const RESTART_TEXT: Record<string, string> = {
  kick_in: "kick-in",
  corner: "corner",
  goal_clearance: "goal clearance",
  goal: "goal",
};

type KeyedEvent = MatchEvent & { key: string };

function describe(e: MatchEvent, labels: Labels): string | null {
  if (e.type === "shot") {
    const who = e.shooter !== undefined ? `${playerLabel(labels, e.shooter)}: ` : "";
    if (e.manual) return `${who}${OUTCOME_TEXT[e.outcome]} (added by you)`;
    const extra = e.inferred ? " — ball not seen in flight, inferred from the keeper catching it" : "";
    const fixed = e.edited ? " (corrected)" : "";
    const dist = e.distance_m !== null ? ` from ${e.distance_m} m` : "";
    return `${who}Shot${dist}${e.speed_kmh ? ` at ~${Math.round(e.speed_kmh)} km/h` : ""}: ${OUTCOME_TEXT[e.outcome]}${fixed}${extra}`;
  }
  if (e.type === "out") {
    const line = e.line === "goal_line" ? "over the goal line" : e.line === "touchline" ? "over the touchline" : "out of play";
    const restart = e.restart ? ` → ${RESTART_TEXT[e.restart]}` : "";
    return e.restart === "goal" ? "Ball in the net" : `Ball ${line}${e.team ? " (last touch)" : ""}${restart}`;
  }
  if (e.type === "keeper_handling" || e.type === "keeper_touch") {
    const what =
      e.type === "keeper_handling"
        ? `${e.save ? "Keeper save, ball in hands" : "Keeper holds the ball"} for ${Math.max(1, Math.round(e.duration_s))} s${e.in_area ? "" : " — outside the area?"}`
        : "Keeper plays the ball with the feet";
    const next = e.distribution === "teammate" ? " → finds a teammate" : e.distribution === "opponent" ? " → gives it to the opponent" : "";
    return what + next;
  }
  return null;
}

function AddGoalForm({ results, onAdd }: { results: MatchResults; onAdd: (t: number, team: string, shooter?: number) => void }) {
  const labels = useLabels();
  const [time, setTime] = useState("");
  const [who, setWho] = useState("team_a");
  const t = parseClock(time);
  const valid = t !== null && t <= results.duration_s + 5;
  return (
    <form
      className="add-goal"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        if (who.startsWith("team_")) onAdd(t, who);
        else onAdd(t, results.roles[who]?.team ?? "team_a", Number(who));
        setTime("");
      }}
    >
      <span>Missed a goal?</span>
      <input placeholder="mm:ss" value={time} onChange={(e) => setTime(e.target.value)} size={6} aria-label="time of the goal" />
      <select value={who} onChange={(e) => setWho(e.target.value)} aria-label="who scored">
        <option value="team_a">{teamLabel(labels, "team_a")}</option>
        <option value="team_b">{teamLabel(labels, "team_b")}</option>
        {results.players
          .filter((p) => p.role === "player")
          .map((p) => (
            <option key={p.track_id} value={String(p.track_id)}>
              {playerLabel(labels, p.track_id)} ({teamLabel(labels, p.team)})
            </option>
          ))}
      </select>
      <button className="secondary" disabled={!valid}>
        Add goal
      </button>
    </form>
  );
}

export default function KeyMoments({
  matchId,
  results,
  clipsEnabled,
  busy,
  version,
  onSelect,
  onCorrect,
}: {
  matchId: string;
  version?: string;
  results: MatchResults;
  clipsEnabled: boolean;
  busy: boolean;
  onSelect: (t: number) => void;
  onCorrect: (next: Corrections) => void;
}) {
  const labels = useLabels();
  const [playing, setPlaying] = useState<KeyedEvent | null>(null);
  const corr = results.corrections;
  const edits = corr.event_edits;
  const moments = (results.events as KeyedEvent[]).filter(
    (e) => e.type === "shot" || e.type === "keeper_handling" || e.type === "keeper_touch" || e.type === "out",
  );

  function setEdits(next: Partial<Corrections["event_edits"]>) {
    onCorrect({ ...corr, event_edits: { ...edits, ...next } });
  }

  function remove(e: KeyedEvent) {
    if (e.key.startsWith("manual@")) {
      const i = Number(e.key.split("@")[1]);
      setEdits({ added: edits.added.filter((_, k) => k !== i) });
    } else {
      setEdits({ removed: [...edits.removed, e.key] });
    }
  }

  function setOutcome(e: KeyedEvent, outcome: ShotOutcome) {
    if (e.key.startsWith("manual@")) {
      const i = Number(e.key.split("@")[1]);
      setEdits({ added: edits.added.map((a, k) => (k === i ? { ...a, outcome } : a)) });
    } else {
      setEdits({ outcomes: { ...edits.outcomes, [e.key]: outcome } });
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Key moments</h3>
        {busy && <span className="hint">Updating stats…</span>}
      </div>
      <p className="hint">
        Click a moment to check it in the ball-state review{clipsEnabled ? ", ▶ to watch and download it as a clip" : ""}.
        Wrong call? Fix the outcome or remove it — the score and stats update.
      </p>
      {moments.length === 0 ? (
        <p className="hint">No shots, goalkeeper actions or balls out were detected.</p>
      ) : (
        <ul className="moments">
          {moments.map((e) => (
            <li key={e.key}>
              <span className="clock clickable" onClick={() => onSelect(e.t)} title="show this moment">
                {clock(e.t)}
              </span>
              <TeamName team={e.team} colors={results.team_colors} />
              <span className="clickable" onClick={() => onSelect(e.t)} title="show this moment">
                {describe(e, labels)}
              </span>
              <span className="moment-actions">
                {clipsEnabled && (
                  <button className="icon-button" title="watch clip" onClick={() => setPlaying(e)}>
                    ▶
                  </button>
                )}
                {e.type === "shot" && (
                  <select
                    value={e.outcome}
                    disabled={busy}
                    title="correct the outcome"
                    onChange={(ev) => setOutcome(e, ev.target.value as ShotOutcome)}
                  >
                    {Object.entries(OUTCOME_TEXT).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                )}
                {(e.type === "shot" || e.type === "keeper_handling") && (
                  <button className="icon-button" title="this didn't happen — remove it" disabled={busy} onClick={() => remove(e)}>
                    ✕
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      <AddGoalForm
        results={results}
        onAdd={(t, team, shooter) =>
          setEdits({ added: [...edits.added, { type: "shot", t, outcome: "goal", team, ...(shooter !== undefined ? { shooter } : {}) }] })
        }
      />

      {results.removed_events.length > 0 && (
        <div className="removed">
          <span className="hint">Removed by you:</span>
          {results.removed_events.map((e) => (
            <button
              key={e.key}
              className="chip"
              disabled={busy}
              title="restore"
              onClick={() => setEdits({ removed: edits.removed.filter((k) => k !== e.key) })}
            >
              {clock(e.t)} {e.type === "shot" ? "shot" : "keeper"} ↺
            </button>
          ))}
        </div>
      )}

      {playing && (
        <VideoModal
          title={`${clock(playing.t)} · ${describe(playing, labels) ?? ""}`}
          src={clipUrl(matchId, playing.t, "wide", false, version)}
          downloads={[
            { label: "Download for stories (9:16)", href: clipUrl(matchId, playing.t, "vertical", true, version) },
            { label: "Download wide", href: clipUrl(matchId, playing.t, "wide", true, version) },
          ]}
          onClose={() => setPlaying(null)}
        />
      )}
    </div>
  );
}
