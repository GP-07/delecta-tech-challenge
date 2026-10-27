import { useState } from "react";

import { api, logout } from "./api";
import type { MatchGroup, Summary } from "./schemas";
import { Categories } from "./components/Categories";
import { Dishes } from "./components/Dishes";
import { MenusCard, QualityCard } from "./components/Insights";
import { MatchBreakdown, MatchedKpi } from "./components/Kpis";
import { Card, Status } from "./components/ui";
import { Venues } from "./components/Venues";
import { fmt } from "./format";
import { useApi } from "./useApi";

const STEP_NAMES: Record<string, string> = {
  crawl_just_eat: "Crawl Just Eat",
  load_google_venues: "Carga Google",
  match_venues: "Matching",
  categorize_menu_items: "Categorización",
  publish_run: "Publicación",
};

export function App() {
  const { data, error, loading } = useApi(api.summary, []);
  const [group, setGroup] = useState<MatchGroup | null>(null);

  return (
    <main className="app">
      <header className="header">
        <div>
          <h1>Restaurantes y menús</h1>
          {data && <RunInfo summary={data} />}
        </div>
        <button type="button" className="ghost" onClick={logout}>Salir</button>
      </header>
      <Status loading={loading} error={error} />
      {data && (
        <>
          <NewerRunBanner run={data.run} />
          <MatchedKpi summary={data} />
          <Card title="Restaurantes de Just Eat por vínculo con Google"
            note="Cada restaurante crawleado está en un solo grupo. Hacé clic para ver la lista.">
            <MatchBreakdown summary={data} group={group} onGroup={setGroup} />
          </Card>
          {group && <Venues group={group} onGroup={setGroup} />}
          <Categories />
          <MoreDetail />
        </>
      )}
    </main>
  );
}

// Beyond what was asked for: folded at first, and its data is only asked for once unfolded (the components mount,
// and so call the API, only when open).
function MoreDetail() {
  const [open, setOpen] = useState(false);
  return (
    <section className="details" aria-label="Más detalle">
      <button type="button" className="details-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <h2>Más detalle</h2>
        <span>{open ? "Ocultar" : "Platos de los restaurantes matcheados, menús y calidad de la categorización"}</span>
      </button>
      {open && (
        <>
          <Dishes />
          <div className="grid-2">
            <MenusCard />
            <QualityCard />
          </div>
        </>
      )}
    </section>
  );
}

function RunInfo({ summary }: { summary: Summary }) {
  const { run } = summary;
  return (
    <>
      <p>Corrida #{run.id} · terminada el {fmt.date(run.finished_at)} · duró {fmt.duration(run.seconds)}</p>
      <div className="steps">
        {run.steps.map((step) => (
          <span key={step.name}>{STEP_NAMES[step.name] ?? step.name}: {fmt.duration(step.seconds)}</span>
        ))}
      </div>
    </>
  );
}

// Only a published run changes what is shown: a later run that is going or failed is just mentioned.
function NewerRunBanner({ run }: { run: Summary["run"] }) {
  const newer = run.newer_run;
  if (newer == null) return null;
  return (
    <p className="banner" role="status">
      <strong>
        {newer.status === "FAILED" ? `La corrida #${newer.id} falló.` : `La corrida #${newer.id} está en curso.`}
      </strong>{" "}
      Los datos son los de la #{run.id}, la última publicada, completos.
      {newer.status !== "FAILED" && " Recargá la página cuando termine."}
    </p>
  );
}
