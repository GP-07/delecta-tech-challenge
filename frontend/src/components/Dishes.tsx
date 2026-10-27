import { useState } from "react";

import { api } from "../api";
import type { DishGroup } from "../schemas";
import { fmt } from "../format";
import { useApi } from "../useApi";
import { GROUPS } from "./Kpis";
import { Card, Segmented, Status } from "./ui";

const PAGE_SIZE = 25;
// Only matched restaurants have their dishes categorized (and stored): the other groups have no dish list.
const DISH_GROUPS = GROUPS.filter((g): g is (typeof GROUPS)[number] & { group: DishGroup } =>
  g.group === "accepted" || g.group === "confirmed");

export function Dishes() {
  const [group, setGroup] = useState<DishGroup>("accepted");
  const [page, setPage] = useState(1);
  const { data, error, loading } = useApi(() => api.dishes(group, page), [group, page]);
  const select = (next: DishGroup) => {
    setGroup(next);
    setPage(1);
  };
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  return (
    <Card title="Platos por estado del vínculo"
      note="Los platos de los restaurantes matcheados, con su categoría. Los de los demás grupos no se categorizan."
      actions={<Segmented label="Estado" value={group} onChange={select}
        options={DISH_GROUPS.map((g) => [g.group, g.label])} />}>
      <Status loading={loading && !data} error={error} />
      {data && data.count === 0 && <p className="empty">No hay platos en este estado.</p>}
      {data && data.count > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Restaurante</th><th>Plato</th><th>Categoría</th><th className="num">Confianza</th>
                  <th className="num">Precio</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((dish) => (
                  <tr key={dish.id}>
                    <td>{dish.venue}</td>
                    <td>{dish.name}<div className="muted small">{dish.section}</div></td>
                    <td>{dish.category ?? "—"}
                      {dish.category && <div className="muted small">{dish.parent} · {dish.family}</div>}</td>
                    <td className="num">{fmt.num(dish.confidence)}</td>
                    <td className="num">{fmt.eur(dish.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span>{fmt.int(data.count)} platos · página {page} de {pages}</span>
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
