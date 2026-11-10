import type {
  ClipFormat,
  CoachReport,
  Corrections,
  Features,
  HighlightsStatus,
  Labels,
  MatchMeta,
  MatchResults,
  PlayerLabel,
  PlayerProfile,
} from "./types";

const API_BASE = "http://localhost:8000";

async function check<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    try {
      throw new Error(JSON.parse(body).detail ?? body);
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(body);
      throw e;
    }
  }
  return res.json();
}

export async function uploadVideo(file: File): Promise<{ match_id: string }> {
  const form = new FormData();
  form.append("video", file);
  return check(await fetch(`${API_BASE}/api/matches`, { method: "POST", body: form }));
}

export function panoramaUrl(matchId: string, version?: string): string {
  return `${API_BASE}/api/matches/${matchId}/panorama${version ? `?v=${encodeURIComponent(version)}` : ""}`;
}

export function reviewFrameUrl(matchId: string, index: number, version?: string): string {
  return `${API_BASE}/api/matches/${matchId}/review/${index}.jpg${version ? `?v=${encodeURIComponent(version)}` : ""}`;
}

export async function getMatch(matchId: string): Promise<MatchMeta> {
  return check(await fetch(`${API_BASE}/api/matches/${matchId}`));
}

export async function listMatches(): Promise<MatchMeta[]> {
  return check(await fetch(`${API_BASE}/api/matches`));
}

export async function calibrateMatch(
  matchId: string,
  corners: number[][],
  pitchLengthM: number,
  pitchWidthM: number,
): Promise<void> {
  await check(
    await fetch(`${API_BASE}/api/matches/${matchId}/calibrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corners, pitch_length_m: pitchLengthM, pitch_width_m: pitchWidthM }),
    }),
  );
}

export async function retryMatch(matchId: string): Promise<void> {
  await check(await fetch(`${API_BASE}/api/matches/${matchId}/retry`, { method: "POST" }));
}

export async function getResults(matchId: string): Promise<MatchResults> {
  return check(await fetch(`${API_BASE}/api/matches/${matchId}/results`));
}

export async function getFeatures(): Promise<Features> {
  return check(await fetch(`${API_BASE}/api/features`));
}

export async function createCoachReport(matchId: string): Promise<CoachReport> {
  return check(await fetch(`${API_BASE}/api/matches/${matchId}/coach-report`, { method: "POST" }));
}

export async function updateLabels(
  matchId: string,
  body: { title?: string; team_names?: Record<string, string>; player_names?: Record<string, PlayerLabel> },
): Promise<Labels> {
  return check(
    await fetch(`${API_BASE}/api/matches/${matchId}/labels`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

/** Saves track merges / event fixes; the server recomputes the stats and returns the new results. */
export async function updateCorrections(matchId: string, corrections: Corrections): Promise<MatchResults> {
  return check(
    await fetch(`${API_BASE}/api/matches/${matchId}/corrections`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corrections),
    }),
  );
}

export async function suggestCorners(matchId: string): Promise<number[][] | null> {
  const r: { corners: number[][] | null } = await check(await fetch(`${API_BASE}/api/matches/${matchId}/suggested-corners`));
  return r.corners;
}

export function clipUrl(matchId: string, t: number, format: ClipFormat, download = false, version?: string): string {
  const q = new URLSearchParams({ t: t.toFixed(2), format });
  if (download) q.set("download", "true");
  if (version) q.set("v", version);
  return `${API_BASE}/api/matches/${matchId}/clip.mp4?${q}`;
}

export async function startHighlights(matchId: string, format: ClipFormat): Promise<HighlightsStatus> {
  return check(
    await fetch(`${API_BASE}/api/matches/${matchId}/highlights`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    }),
  );
}

export function highlightsUrl(matchId: string, format: ClipFormat, download = false, version?: string): string {
  const q = new URLSearchParams({ format });
  if (download) q.set("download", "true");
  if (version) q.set("v", version);
  return `${API_BASE}/api/matches/${matchId}/highlights.mp4?${q}`;
}

export async function deleteMatch(matchId: string): Promise<void> {
  await check(await fetch(`${API_BASE}/api/matches/${matchId}`, { method: "DELETE" }));
}

export async function listPlayers(): Promise<PlayerProfile[]> {
  return check(await fetch(`${API_BASE}/api/players`));
}
