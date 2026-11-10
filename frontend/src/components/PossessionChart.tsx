import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { PossessionSample } from "../types";

const BUCKETS = 24;

const FALLBACK = { team_a: "#4fb3ff", team_b: "#ff8a4f" };

export default function PossessionChart({
  timeline,
  colors,
}: {
  timeline: PossessionSample[];
  colors: Record<string, string>;
}) {
  const a = colors.team_a ?? FALLBACK.team_a;
  const b = colors.team_b ?? FALLBACK.team_b;
  if (timeline.length === 0) return null;
  const duration = timeline[timeline.length - 1].t || 1;
  const bucketSize = duration / BUCKETS;

  const buckets = Array.from({ length: BUCKETS }, (_, i) => ({
    t: Math.round(i * bucketSize),
    team_a: 0,
    team_b: 0,
    total: 0,
  }));

  for (const s of timeline) {
    const idx = Math.min(BUCKETS - 1, Math.floor(s.t / bucketSize));
    if (s.team === "team_a") buckets[idx].team_a += 1;
    else if (s.team === "team_b") buckets[idx].team_b += 1;
    buckets[idx].total += 1;
  }

  const data = buckets.map((b) => ({
    t: b.t,
    "Team A %": b.total ? Math.round((100 * b.team_a) / b.total) : 0,
    "Team B %": b.total ? Math.round((100 * b.team_b) / b.total) : 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a3438" />
        <XAxis dataKey="t" tickFormatter={(t) => `${t}s`} stroke="#8aa0a8" fontSize={12} />
        <YAxis stroke="#8aa0a8" fontSize={12} domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: "#12191c", border: "1px solid #2a3438" }}
          labelFormatter={(t) => `${t}s`}
        />
        <Area type="monotone" dataKey="Team A %" stackId="1" stroke={a} fill={`${a}77`} />
        <Area type="monotone" dataKey="Team B %" stackId="1" stroke={b} fill={`${b}77`} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
