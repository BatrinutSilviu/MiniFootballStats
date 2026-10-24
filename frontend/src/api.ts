import type { MatchMeta, MatchResults } from "./types";

const API_BASE = "http://localhost:8000";

export async function uploadVideo(file: File): Promise<{ match_id: string }> {
  const form = new FormData();
  form.append("video", file);
  const res = await fetch(`${API_BASE}/api/matches`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function firstFrameUrl(matchId: string): string {
  return `${API_BASE}/api/matches/${matchId}/first-frame`;
}

export async function getMatch(matchId: string): Promise<MatchMeta> {
  const res = await fetch(`${API_BASE}/api/matches/${matchId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listMatches(): Promise<MatchMeta[]> {
  const res = await fetch(`${API_BASE}/api/matches`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function calibrateMatch(
  matchId: string,
  corners: number[][],
  pitchLengthM: number,
  pitchWidthM: number,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/matches/${matchId}/calibrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ corners, pitch_length_m: pitchLengthM, pitch_width_m: pitchWidthM }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function getResults(matchId: string): Promise<MatchResults> {
  const res = await fetch(`${API_BASE}/api/matches/${matchId}/results`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
