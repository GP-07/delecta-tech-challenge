import { useState } from "react";

import { api } from "../api";
import type { MatchGroup } from "../schemas";
import { fmt } from "../format";
import { useApi } from "../useApi";
import { GROUPS } from "./Kpis";
import { Card, Segmented, Status } from "./ui";

const ADMIN_FILTER: Partial<Record<MatchGroup, string>> = {
  review: "/admin/venues/venuematch/?status__exact=REVIEW",
  rejected: "/admin/venues/venuematch/?status__exact=REJECTED",
};
const PAGE_SIZE = 25;

export function Venues({ group, onGroup }: { group: MatchGroup; onGroup: (group: MatchGroup) => void }) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useApi(() => api.venues(group, page), [group, page]);
  const select = (next: MatchGroup) => {
    onGroup(next);
    setPage(1);
  };
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;
  const admin = ADMIN_FILTER[group];

  return (
    <Card title="Restaurantes por estado del vínculo"
      note={<>{GROUPS.find((g) => g.group === group)?.note}.{" "}
        {admin && <a href={admin}>Revisarlos en el admin</a>}</>}
      actions={<Segmented label="Estado" value={group} onChange={select}
        options={GROUPS.map((g) => [g.group, g.label])} />}>
      <Status loading={loading && !data} error={error} />
      {data && data.count === 0 && <p className="empty">No hay restaurantes en este estado.</p>}
      {data && data.count > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Just Eat</th><th>Cocinas</th><th className="num">Rating JE</th>
                  {group !== "unmatched" && <><th>Google</th><th className="num">Rating Google</th>
                    <th className="num">Score</th><th className="num">Distancia</th></>}
                </tr>
              </thead>
              <tbody>
                {data.results.map((venue) => (
                  <tr key={venue.id}>
                    <td>
                      {venue.url ? <a href={venue.url} target="_blank" rel="noopener noreferrer">{venue.name}</a>
                        : venue.name}
                      <div className="muted small">{venue.address}</div>
                    </td>
                    <td>{venue.cuisines.slice(0, 3).map((c) => <span key={c} className="badge">{c}</span>)}</td>
                    <td className="num">{fmt.num(venue.star_rating)}
                      <div className="muted small">{venue.rating_count != null && `${fmt.int(venue.rating_count)} op.`}</div>
                    </td>
                    {group !== "unmatched" && (
                      <>
                        <td>{venue.google?.name}<div className="muted small">{venue.google?.address}</div></td>
                        <td className="num">{fmt.num(venue.google?.star_rating ?? null)}</td>
                        <td className="num">{fmt.num(venue.google?.score ?? null)}</td>
                        <td className="num">{venue.google ? `${fmt.int(Math.round(venue.google.distance_m))} m` : "—"}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span>{fmt.int(data.count)} restaurantes · página {page} de {pages}</span>
            <button type="button" className="ghost" disabled={!data.previous} onClick={() => setPage(page - 1)}>
              Anterior
            </button>
            <button type="button" className="ghost" disabled={!data.next} onClick={() => setPage(page + 1)}>
              Siguiente
            </button>
          </div>
        </>
      )}
    </Card>
  );
}
