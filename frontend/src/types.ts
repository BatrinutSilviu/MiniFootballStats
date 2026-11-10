export type MatchStatus =
  | "queued"
  | "analyzing"
  | "awaiting_calibration"
  | "computing"
  | "done"
  | "error";

export interface CameraQuality {
  registered_frames: number;
  total_frames: number;
  registration_rate: number;
  keyframes: number;
}

export interface MatchMeta {
  id: string;
  status: MatchStatus;
  progress?: number;
  error?: string;
  video_filename: string;
  panorama_width?: number;
  panorama_height?: number;
  camera?: CameraQuality;
  pitch_length_m: number;
  pitch_width_m: number;
  corners?: number[][];
  title?: string;
  team_names?: Record<string, string>;
  highlights?: HighlightsStatus;
  created_at?: string;
  updated_at?: string;
}

export interface KeeperStats {
  handlings: number;
  handlings_in_area: number;
  hold_s: number;
  touches_outside_area: number;
  saves: number;
  save_pct: number | null;
  distributions: number;
  distribution_success_pct: number | null;
}

export interface TeamStats {
  possession_pct: number | null;
  distance_m: number;
  observed_player_minutes: number;
  m_per_min: number | null;
  passes: number;
  turnovers: number;
  pass_accuracy_pct: number | null;
  turnovers_own_third: number;
  shots: number;
  shots_on_target: number;
  goals: number;
  shots_conceded: number;
  balls_out: number;
  goals_conceded: number;
  keeper: KeeperStats;
  avg_recovery_s: number | null;
  territory_pct: { defensive: number; middle: number; attacking: number } | null;
  width_in_possession_m: number | null;
  depth_out_of_possession_m: number | null;
}

export interface PlayerStats {
  track_id: number;
  team: string;
  role: "player" | "goalkeeper";
  distance_m: number;
  observed_s: number;
  m_per_min: number;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  sample_count: number;
  passes: number;
  turnovers: number;
  shots: number;
  shots_on_target: number;
  goals: number;
  saves: number;
  keeper_handlings: number;
  heatmap: number[][];
}

export type MatchEvent =
  | { type: "pass"; team: string; t: number; from?: number; to?: number }
  | { type: "turnover"; team: string; to_team: string; t: number; from?: number }
  | {
      type: "shot";
      team: string | null;
      t: number;
      shooter?: number;
      target_side: string | null;
      distance_m: number | null;
      speed_kmh: number | null;
      on_target: boolean;
      outcome: ShotOutcome;
      inferred?: boolean;
      edited?: boolean;
      manual?: boolean;
    }
  | {
      type: "keeper_handling" | "keeper_touch";
      team: string | null;
      side: string;
      t: number;
      keeper?: number;
      duration_s: number;
      in_area: boolean;
      save: boolean;
      distribution: "teammate" | "opponent" | null;
    }
  | {
      type: "out";
      t: number;
      team: string | null;
      line: "touchline" | "goal_line" | null;
      side: string | null;
      restart: "kick_in" | "corner" | "goal_clearance" | "goal" | null;
    };

export type ShotOutcome = "goal" | "saved" | "blocked" | "off_target" | "unknown";

export type BallState = "keeper" | "ground" | "air" | "out";

export interface BallSample {
  t: number;
  state: BallState;
  holder: number | null;
  x: number | null;
  y: number | null;
  src: "detected" | "interpolated" | "flight" | "inferred";
  box: number[] | null;
}

export interface BallSummary {
  keeper_pct: number;
  ground_pct: number;
  air_pct: number;
  out_pct: number;
  unknown_pct: number;
  in_play_pct: number;
  outs: number;
  restarts: { kick_in: number; corner: number; goal_clearance: number; goal: number };
  keeper_holds: number;
}

export interface PossessionSample {
  t: number;
  team: string | null;
}

export type Confidence = "low" | "medium" | "high";

export interface Insight {
  title: string;
  detail: string;
  evidence: string;
  confidence: Confidence;
  drill?: string;
}

export interface TeamInsights {
  strengths: Insight[];
  lessons: Insight[];
}

export interface Quality {
  camera_registration_rate: number;
  ball_detected_rate: number;
  ball_known_rate: number;
  ball_size_norm: number;
  sides_known: boolean;
  goalkeepers_found: number;
  tracks: number;
}

export interface CoachReport {
  model: string;
  summary: string;
  teams: {
    team: string;
    headline: string;
    strengths: { title: string; explanation: string }[];
    lessons: { title: string; explanation: string; drill: string }[];
  }[];
  caveats: string[];
  stale?: boolean;
}

export interface PlayerLabel {
  name: string;
  number: number | null;
}

export interface Labels {
  title: string | null;
  team_names: Record<string, string>;
  player_names: Record<string, PlayerLabel>;
}

export interface AddedShot {
  type: "shot";
  t: number;
  outcome: ShotOutcome;
  team: string | null;
  shooter?: number;
}

export interface Corrections {
  track_merges: Record<string, number>;
  event_edits: { removed: string[]; outcomes: Record<string, ShotOutcome>; added: AddedShot[] };
}

export interface RecordingTip {
  severity: "high" | "medium" | "low" | "ok";
  title: string;
  detail: string;
}

export interface HighlightsStatus {
  status: "rendering" | "done" | "error";
  format: ClipFormat;
  progress?: number;
  moments?: number;
  version?: string;
  error?: string;
}

export type ClipFormat = "vertical" | "wide";

export interface Features {
  coach_report: boolean;
  clips: boolean;
  watermark: boolean;
}

export interface Rating {
  overall: number;
  pace: number;
  work_rate: number;
  passing: number;
  shooting?: number;
  keeping?: number;
}

export interface PlayerProfile {
  name: string;
  number: number | null;
  role: "player" | "goalkeeper";
  matches: number;
  observed_s: number;
  distance_m: number;
  m_per_min: number;
  top_speed_kmh: number;
  passes: number;
  turnovers: number;
  shots: number;
  shots_on_target: number;
  goals: number;
  saves: number;
  record: { W: number; D: number; L: number };
  rating: Rating;
  history: {
    match_id: string;
    date: string | null;
    title: string;
    team: string;
    opponent: string;
    result: "W" | "D" | "L" | null;
    score: string | null;
    role: string;
    goals: number;
    shots: number;
    passes: number;
    saves: number;
    m_per_min: number;
    max_speed_kmh: number;
  }[];
}

export interface MatchResults {
  pitch: { length_m: number; width_m: number };
  duration_s: number;
  frame_sample_count: number;
  team_colors: Record<string, string>;
  teams: Record<string, TeamStats>;
  players: PlayerStats[];
  team_heatmaps: Record<string, number[][]>;
  possession_timeline: PossessionSample[];
  ball_track: (BallSample | null)[];
  ball_summary: BallSummary;
  roles: Record<string, { role: string; team: string | null }>;
  events: MatchEvent[];
  removed_events: (MatchEvent & { key: string })[];
  recording_tips: RecordingTip[];
  labels: Labels;
  corrections: Corrections;
  quality: Quality;
  insights: { team_a: TeamInsights; team_b: TeamInsights; notes: string[] };
  coach_report?: CoachReport;
}
