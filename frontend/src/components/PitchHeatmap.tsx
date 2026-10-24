const VIEW_W = 400;

export default function PitchHeatmap({
  grid,
  lengthM,
  widthM,
}: {
  grid: number[][];
  lengthM: number;
  widthM: number;
}) {
  const viewH = VIEW_W * (widthM / lengthM);
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  const cellW = VIEW_W / cols;
  const cellH = viewH / rows;

  return (
    <svg width="100%" viewBox={`0 0 ${VIEW_W} ${viewH}`} className="pitch-svg">
      <rect x={0} y={0} width={VIEW_W} height={viewH} fill="#1c6e3a" stroke="white" strokeWidth={2} />
      <line x1={VIEW_W / 2} y1={0} x2={VIEW_W / 2} y2={viewH} stroke="white" strokeWidth={1.5} />
      <circle cx={VIEW_W / 2} cy={viewH / 2} r={viewH * 0.15} fill="none" stroke="white" strokeWidth={1.5} />

      {grid.map((row, r) =>
        row.map((v, c) => {
          if (v <= 0) return null;
          return (
            <rect
              key={`${r}-${c}`}
              x={c * cellW}
              y={r * cellH}
              width={cellW}
              height={cellH}
              fill="#ff3b30"
              opacity={Math.min(0.85, v * 0.85)}
            />
          );
        }),
      )}
    </svg>
  );
}
