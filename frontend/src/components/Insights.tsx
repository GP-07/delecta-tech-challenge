import { api } from "../api";
import { fmt } from "../format";
import { useApi } from "../useApi";
import { Bars } from "./Bars";
import { Card, Fact, Status } from "./ui";

export function MenusCard() {
  const { data, error, loading } = useApi(api.menus, []);
  return (
    <Card title="Menús" note="Restaurantes matcheados, con sus platos categorizados.">
      <Status loading={loading} error={error} />
      {data && (
        <div className="facts">
          <Fact value={fmt.num(data.median_items)} label="platos por menú (mediana)" />
          <Fact value={fmt.pct(data.venues_with_drinks)} label="venden bebidas" />
          <Fact value={fmt.pct(data.combo_share)} label="de los platos son combos" />
        </div>
      )}
    </Card>
  );
}

export function QualityCard() {
  const { data, error, loading } = useApi(api.quality, []);
  return (
    <Card title="Calidad de la categorización" note="Qué decidió la categoría de cada plato y con cuánta confianza.">
      <Status loading={loading} error={error} />
      {data && (
        <>
          <div className="facts">
            <Fact value={fmt.int(data.items.categorized)}
              label={`platos categorizados (${fmt.share(data.items.categorized, data.items.total)})`} />
            <Fact value={fmt.share(data.items.low_confidence, data.items.categorized)}
              label={`confianza baja: ${fmt.int(data.items.low_confidence)} para revisar en el admin`} />
          </div>
          <div className="grid-2">
            <div>
              <h3>Qué decidió la categoría</h3>
              <Bars data={data.methods} label="label" value="items" format={fmt.int} tooltip={(row) => (
                <><strong>{row.label}</strong><div>{fmt.int(row.items)} platos</div></>
              )} />
            </div>
            <div>
              <h3>Confianza de la categoría</h3>
              <Bars data={data.confidence} label="bucket" value="items" layout="vertical" format={fmt.int}
                height={220} tooltip={(row) => <><strong>Confianza {row.bucket}</strong><div>{fmt.int(row.items)} platos</div></>} />
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
