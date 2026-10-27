import type { MatchGroup, Summary } from "../schemas";
import { fmt } from "../format";

export const GROUPS: { group: MatchGroup; label: string; color: string; note: string }[] = [
  { group: "accepted", label: "Aceptados", color: "var(--good)", note: "vinculados automáticamente" },
  { group: "confirmed", label: "Confirmados", color: "var(--good-2)", note: "una persona confirmó el vínculo" },
  { group: "review", label: "A revisar", color: "var(--warning)", note: "esperan una decisión en el admin" },
  { group: "rejected", label: "Rechazados", color: "var(--critical)", note: "una persona descartó el vínculo" },
  { group: "unmatched", label: "Sin match", color: "var(--neutral)", note: "sin lugar de Google parecido" },
];

// The required KPI: matched restaurants (accepted + confirmed) out of the crawled ones.
export function MatchedKpi({ summary }: { summary: Summary }) {
  const { matched, crawled } = summary.matched;
  return (
    <div className="tile hero">
      <span className="tile-label">Restaurantes matcheados</span>
      <span className="tile-value">{fmt.int(matched)}</span>
      <span className="tile-note">
        {fmt.share(matched, crawled)} de {fmt.int(crawled)} restaurantes de Just Eat · aceptados automáticamente o
        confirmados por una persona
      </span>
    </div>
  );
}

// Crawled restaurants split by match group: one 100% bar; the legend says the numbers and opens each list.
export function MatchBreakdown({ summary, group, onGroup }: {
  summary: Summary;
  group: MatchGroup | null;
  onGroup: (group: MatchGroup) => void;
}) {
  const groups = summary.match_groups;
  const crawled = summary.matched.crawled;
  return (
    <div>
      <div className="stack" role="img"
        aria-label={GROUPS.map((g) => `${g.label}: ${groups[g.group]}`).join(", ")}>
        {GROUPS.filter((g) => groups[g.group] > 0).map((g) => (
          <span key={g.group} title={`${g.label}: ${fmt.int(groups[g.group])}`}
            style={{ flex: groups[g.group], background: g.color, opacity: group && group !== g.group ? 0.35 : 1 }} />
        ))}
      </div>
      <div className="legend">
        {GROUPS.map((g) => (
          <button key={g.group} type="button" className="link-button" onClick={() => onGroup(g.group)}
            aria-pressed={group === g.group} title={`Ver la lista: ${g.note}`}>
            <span><span className="dot" style={{ background: g.color }} />
              {g.label} <strong>{fmt.int(groups[g.group])}</strong> ({fmt.share(groups[g.group], crawled)})</span>
          </button>
        ))}
      </div>
    </div>
  );
}
