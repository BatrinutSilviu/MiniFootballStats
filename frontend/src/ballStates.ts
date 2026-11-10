import type { BallState } from "./types";

export type StateKey = BallState | "unknown";

export const STATE_META: Record<StateKey, { label: string; color: string }> = {
  keeper: { label: "Keeper has the ball", color: "#ffa500" },
  ground: { label: "In play, on the ground", color: "#50c850" },
  air: { label: "In play, in the air", color: "#3ca0ff" },
  out: { label: "Out of play", color: "#e63c3c" },
  unknown: { label: "Ball not found", color: "#5a666b" },
};
