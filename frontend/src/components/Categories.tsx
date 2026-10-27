import { useState } from "react";

import { api } from "../api";
import type { CategoryRow, Family, Level, Order } from "../schemas";
import { fmt } from "../format";
import { useApi } from "../useApi";
import { Bars } from "./Bars";
import { Card, Fact, Segmented, Status } from "./ui";

const TOP = 15;

function CategoryTooltip({ row }: { row: CategoryRow }) {
  return (
    <>
      <strong>{row.key}</strong>
      <div>{fmt.int(row.venues)} restaurantes ({fmt.pct(row.venues_share)})</div>
      <div>{fmt.int(row.items)} platos · precio mediano {fmt.eur(row.median_price)}</div>
    </>
  );
}

export function Categories() {
  const [family, setFamily] = useState<Family>("food");
  const [level, setLevel] = useState<Level>("parent");
  const [order, setOrder] = useState<Order>("venues");
  const [table, setTable] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, error, loading } = useApi(() => api.categories(family, level, order, TOP), [family, level, order]);
  const reset = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setSelected(null);
  };

  return (
    <div className="grid-2">
      <Card title="Oferta principal por categoría"
        note={order === "venues"
          ? "Categorías que ofrecen más restaurantes vinculados. Hacé clic en una barra para ver el detalle."
          : "Categorías con más platos en los menús. Hacé clic en una barra para ver el detalle."}
        actions={
          <div className="controls">
            <Segmented label="Familia" value={family} onChange={reset(setFamily)}
              options={[["food", "Comida"], ["drink", "Bebida"]]} />
            <Segmented label="Nivel" value={level} onChange={reset(setLevel)}
              options={[["parent", "Grupo"], ["name", "Categoría"]]} />
            <Segmented label="Medida" value={order} onChange={setOrder}
              options={[["venues", "Restaurantes"], ["items", "Platos"]]} />
          </div>
        }>
        <Status loading={loading && !data} error={error} />
        {data && data.length === 0 && <p className="empty">No hay platos categorizados.</p>}
        {data && data.length > 0 && (table ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Categoría</th><th className="num">Restaurantes</th><th className="num">%</th>
                  <th className="num">Platos</th><th className="num">Precio mediano</th></tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.key} className="clickable" onClick={() => setSelected(row.key)}>
                    <td>{row.key}</td><td className="num">{fmt.int(row.venues)}</td>
                    <td className="num">{fmt.pct(row.venues_share)}</td><td className="num">{fmt.int(row.items)}</td>
                    <td className="num">{fmt.eur(row.median_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Bars data={data} label="key" value={order} format={fmt.int} selected={selected}
            onSelect={(row) => setSelected(row.key)} tooltip={(row) => <CategoryTooltip row={row} />} />
        ))}
        <button type="button" className="link-button" onClick={() => setTable(!table)}>
          {table ? "Ver gráfico" : "Ver como tabla"}
        </button>
      </Card>
      {selected ? <CategoryDetailCard level={level} keyName={selected} onClose={() => setSelected(null)} />
        : <PricesCard data={data} />}
    </div>
  );
}

// Without a selected category: the median price of the same top categories (combos left out).
function PricesCard({ data }: { data: CategoryRow[] | null }) {
  const priced = (data ?? []).filter((row) => row.median_price != null)
    .sort((a, b) => (b.median_price ?? 0) - (a.median_price ?? 0));
  return (
    <Card title="Precio mediano por categoría"
      note="Precio mediano de los platos de cada categoría del ranking, sin contar combos ni menús.">
      {priced.length === 0 ? <p className="empty">Sin precios.</p> : (
        <Bars data={priced} label="key" value="median_price" format={(v) => fmt.eur(v)}
          tooltip={(row) => <CategoryTooltip row={row} />} />
      )}
    </Card>
  );
}

function CategoryDetailCard({ level, keyName, onClose }: { level: Level; keyName: string; onClose: () => void }) {
  const { data, error, loading } = useApi(() => api.category(level, keyName), [level, keyName]);
  return (
    <Card title={`Detalle: ${keyName}`} note={level === "parent" ? "Grupo de categorías" : "Categoría"}
      actions={<button type="button" className="ghost" onClick={onClose}>Cerrar</button>}>
      <Status loading={loading} error={error} />
      {data && !loading && (
        <>
          <div className="facts">
            <Fact value={fmt.int(data.venues)} label="restaurantes" />
            <Fact value={fmt.int(data.items)} label="platos" />
            <Fact value={fmt.eur(data.median_price)} label="precio mediano" />
          </div>
          {data.subcategories.length > 1 && (
            <>
              <h3>Categorías del grupo</h3>
              <Bars data={data.subcategories.slice(0, 10)} label="key" value="items" format={fmt.int}
                tooltip={(row) => (
                  <>
                    <strong>{row.key}</strong>
                    <div>{fmt.int(row.items)} platos · {fmt.int(row.venues)} restaurantes</div>
                    <div>precio mediano {fmt.eur(row.median_price)}</div>
                  </>
                )} />
            </>
          )}
          <div className="grid-2">
            <div className="table-wrap">
              <h3>Platos más repetidos</h3>
              <table>
                <thead><tr><th>Plato</th><th className="num">Veces</th><th className="num">Precio</th></tr></thead>
                <tbody>
                  {data.top_dishes.map((dish) => (
                    <tr key={dish.name}><td>{dish.name}</td><td className="num">{fmt.int(dish.items)}</td>
                      <td className="num">{fmt.eur(dish.median_price)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-wrap">
              <h3>Restaurantes con más platos</h3>
              <table>
                <thead><tr><th>Restaurante</th><th className="num">Platos</th></tr></thead>
                <tbody>
                  {data.top_venues.map((venue) => (
                    <tr key={venue.name}><td>{venue.name}</td><td className="num">{fmt.int(venue.items)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
