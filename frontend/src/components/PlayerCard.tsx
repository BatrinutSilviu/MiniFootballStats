import { useRef } from "react";
import type { PlayerProfile } from "../types";

const W = 320;
const H = 460;
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

function tier(overall: number): [string, string] {
  if (overall >= 80) return ["#f5d77a", "#b8892b"]; // gold
  if (overall >= 65) return ["#e3e8ec", "#8d99a3"]; // silver
  return ["#e8b48a", "#9a5b34"]; // bronze
}

const ATTR_LABELS: Record<string, string> = {
  pace: "PACE",
  work_rate: "WORK",
  passing: "PASS",
  shooting: "SHOOT",
  keeping: "KEEP",
};

/** A shareable rating card. Pure SVG, so it can be saved as a PNG without any library. */
export default function PlayerCard({ profile }: { profile: PlayerProfile }) {
  const ref = useRef<SVGSVGElement>(null);
  const r = profile.rating;
  const [light, dark] = tier(r.overall);
  const attrs = Object.entries(r).filter(([k]) => k !== "overall");

  async function downloadPng() {
    const svg = ref.current;
    if (!svg) return;
    const xml = new XMLSerializer().serializeToString(svg);
    const url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }));
    try {
      const img = new Image();
      await new Promise<void>((ok, fail) => {
        img.onload = () => ok();
        img.onerror = () => fail(new Error("could not draw the card"));
        img.src = url;
      });
      const canvas = document.createElement("canvas");
      canvas.width = W * 3;
      canvas.height = H * 3;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${profile.name.replace(/[^\p{L}\p{N}]+/gu, "-").toLowerCase()}-card.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  return (
    <div className="player-card-wrap">
      <svg ref={ref} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="player-card">
        <defs>
          <linearGradient id="card-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={light} />
            <stop offset="1" stopColor={dark} />
          </linearGradient>
        </defs>
        <path d={`M20 0 H${W - 20} L${W} 30 V${H - 60} L${W / 2} ${H} L0 ${H - 60} V30 Z`} fill="url(#card-bg)" />
        <path d={`M30 14 H${W - 30} L${W - 14} 38 V${H - 68} L${W / 2} ${H - 16} L14 ${H - 68} V38 Z`} fill="none" stroke="#1a1a1a" strokeOpacity="0.25" strokeWidth="2" />
        <text x="42" y="92" fontFamily={FONT} fontSize="64" fontWeight="800" fill="#1a1a1a">
          {r.overall}
        </text>
        <text x="46" y="122" fontFamily={FONT} fontSize="20" fontWeight="700" fill="#1a1a1a">
          {profile.role === "goalkeeper" ? "GK" : "PLAYER"}
        </text>
        {profile.number !== null && (
          <text x={W - 42} y="92" textAnchor="end" fontFamily={FONT} fontSize="52" fontWeight="800" fill="#1a1a1a" fillOpacity="0.35">
            {profile.number}
          </text>
        )}
        <text x={W / 2} y="210" textAnchor="middle" fontFamily={FONT} fontSize={profile.name.length > 14 ? 26 : 34} fontWeight="800" fill="#1a1a1a">
          {profile.name.toUpperCase()}
        </text>
        <line x1="50" x2={W - 50} y1="232" y2="232" stroke="#1a1a1a" strokeOpacity="0.3" />
        {attrs.map(([k, v], i) => {
          const x = i % 2 === 0 ? 70 : W / 2 + 30;
          const y = 280 + Math.floor(i / 2) * 50;
          return (
            <g key={k}>
              <text x={x} y={y} fontFamily={FONT} fontSize="30" fontWeight="800" fill="#1a1a1a">
                {v}
              </text>
              <text x={x + 48} y={y} fontFamily={FONT} fontSize="18" fontWeight="600" fill="#1a1a1a">
                {ATTR_LABELS[k] ?? k}
              </text>
            </g>
          );
        })}
        <line x1="50" x2={W - 50} y1="364" y2="364" stroke="#1a1a1a" strokeOpacity="0.3" />
        <text x={W / 2} y="392" textAnchor="middle" fontFamily={FONT} fontSize="15" fontWeight="600" fill="#1a1a1a">
          {profile.matches} match{profile.matches === 1 ? "" : "es"} · {profile.role === "goalkeeper" ? `${profile.saves} saves` : `${profile.goals} goals`} · {profile.record.W}W {profile.record.D}D {profile.record.L}L
        </text>
        <text x={W / 2} y="416" textAnchor="middle" fontFamily={FONT} fontSize="11" fill="#1a1a1a" fillOpacity="0.6">
          minifootball stats
        </text>
      </svg>
      <button className="secondary" onClick={downloadPng}>
        Save card as image
      </button>
    </div>
  );
}
