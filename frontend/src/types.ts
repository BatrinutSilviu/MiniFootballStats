export type MatchStatus = "awaiting_calibration" | "queued" | "processing" | "done" | "error";

export interface MatchMeta {
  id: string;
  status: MatchStatus;
  progress?: number;
  error?: string;
  video_filename: string;
  frame_width: number;
  frame_height: number;
  pitch_length_m: number;
  pitch_width_m: number;
  corners?: number[][];
  created_at?: string;
  updated_at?: string;
}

export interface TeamStats {
  possession_pct: number;
  distance_m: number;
  passes: number;
  turnovers: number;
}

export interface PlayerStats {
  track_id: number;
  team: string;
  distance_m: number;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  sample_count: number;
  heatmap: number[][];
}

export interface MatchEvent {
  type: "pass" | "turnover";
  team: string;
  to_team?: string;
  t: number;
}

export interface PossessionSample {
  t: number;
  team: string | null;
}

export interface MatchResults {
  pitch: { length_m: number; width_m: number };
  duration_s: number;
  frame_sample_count: number;
  teams: Record<string, TeamStats>;
  players: PlayerStats[];
  possession_timeline: PossessionSample[];
  events: MatchEvent[];
}
