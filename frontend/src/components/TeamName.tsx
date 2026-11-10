import { TEAM_LABELS } from "../teams";
import { teamLabel, useLabels } from "../labels";

export default function TeamName({ team, colors }: { team: string | null; colors: Record<string, string> }) {
  const labels = useLabels();
  if (!team || !TEAM_LABELS[team]) return <span>Unknown team</span>;
  return (
    <span className="team-name">
      <span className="swatch" style={{ background: colors[team] ?? "#888" }} title="detected jersey color" />
      {teamLabel(labels, team)}
    </span>
  );
}
