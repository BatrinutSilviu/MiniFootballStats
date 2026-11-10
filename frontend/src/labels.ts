import { createContext, useContext } from "react";
import type { Labels } from "./types";
import { TEAM_LABELS } from "./teams";

export const EMPTY_LABELS: Labels = { title: null, team_names: {}, player_names: {} };

/** Names the user gave to the teams and players of the match being shown. */
export const LabelsContext = createContext<Labels>(EMPTY_LABELS);

export function useLabels(): Labels {
  return useContext(LabelsContext);
}

export function teamLabel(labels: Labels, team: string | null | undefined): string {
  if (!team) return "Unknown team";
  return labels.team_names[team] || TEAM_LABELS[team] || team;
}

/** "Andrei #7", or the tracking ID when the player hasn't been named. */
export function playerLabel(labels: Labels, tid: number | null | undefined): string {
  if (tid === null || tid === undefined) return "";
  const p = labels.player_names[String(tid)];
  if (!p || (!p.name && p.number === null)) return `#${tid}`;
  return [p.name, p.number !== null ? `#${p.number}` : ""].filter(Boolean).join(" ");
}

export function clock(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** "12:34" or "754" → seconds; null when unparseable. */
export function parseClock(v: string): number | null {
  const m = v.trim().match(/^(\d+)(?::(\d{1,2}))?$/);
  if (!m) return null;
  return m[2] === undefined ? Number(m[1]) : Number(m[1]) * 60 + Number(m[2]);
}
