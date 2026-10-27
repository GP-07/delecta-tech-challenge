import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "../App";
import type { CategoryDetail, CategoryRow, DishRow, Menus, Page, Quality, Summary, VenueRow } from "../schemas";

// The answers of the API, typed with the contract (schemas.ts): if the contract changes, `tsc` flags them.

const summary = {
  run: { id: 5, finished_at: "2026-10-26T18:00:00Z", seconds: 600, newer_run: null,
    steps: [{ name: "crawl_just_eat", status: "SUCCEEDED", seconds: 540 }] },
  matched: { matched: 6, crawled: 10 },
  match_groups: { accepted: 5, confirmed: 1, review: 2, rejected: 1, unmatched: 1 },
} satisfies Summary;
const categories = [
  { key: "pizza", family: "food", items: 40, venues: 5, venues_share: 0.8333, median_price: 11 },
  { key: "fast food", family: "food", items: 20, venues: 3, venues_share: 0.5, median_price: 9 },
] satisfies CategoryRow[];
const detail = { key: "pizza", level: "parent", family: "food", items: 40, venues: 5, median_price: 11,
  subcategories: [], top_dishes: [{ name: "margherita", items: 5, median_price: 10 }],
  top_venues: [{ name: "Pizzeria Uno", items: 30 }] } satisfies CategoryDetail;
const review = { count: 1, next: null, previous: null, results: [{ id: "1", name: "Sushi Tres", city: "Barcelona",
  address: "Calle 1", url: "", cuisines: ["sushi"], star_rating: 4.8, rating_count: 10,
  google: { name: "Sushi 3", address: "Calle 1", star_rating: 4.4, rating_count: 5, status: "REVIEW", score: 0.6,
    distance_m: 300, reason: "x" } }] } satisfies Page<VenueRow>;
const responses: Record<string, unknown> = {
  "/api/dashboard/summary/": summary,
  "/api/dashboard/categories/": categories,
  "/api/dashboard/categories/detail/": detail,
  "/api/dashboard/venues/": review,
  "/api/dashboard/dishes/": { count: 1, next: null, previous: null, results: [{ id: 1, venue: "Pizzeria Uno",
    name: "Margherita", section: "Pizzas", category: "pizza margherita", parent: "pizza", family: "food",
    confidence: 0.95, method: "name", price: 10 }] } satisfies Page<DishRow>,
  "/api/dashboard/menus/": { venues: 6, median_items: 40, venues_with_drinks: 0.9, combo_share: 0.1 } satisfies Menus,
  "/api/dashboard/quality/": { items: { total: 100, categorized: 90, low_confidence: 9, pending: 0 },
    methods: [], confidence: [] } satisfies Quality,
};
const fetchMock = vi.fn(async (url: string) => {
  const path = url.split("?")[0];
  return new Response(JSON.stringify(responses[path]), { status: path in responses ? 200 : 404 });
});

beforeEach(() => vi.stubGlobal("fetch", fetchMock));
afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockClear();
});

test("shows the matched restaurants and every match group", async () => {
  render(<App />);

  const hero = (await screen.findByText("Restaurantes matcheados")).closest(".tile") as HTMLElement;
  expect(within(hero).getByText("6")).toBeTruthy();
  expect(within(hero).getByText(/60 % de 10 restaurantes de Just Eat/)).toBeTruthy();
  for (const group of [/^Aceptados ?5/, /^Confirmados ?1/, /^A revisar ?2/, /^Rechazados ?1/, /^Sin match ?1/]) {
    expect(screen.getByRole("button", { name: group })).toBeTruthy();
  }
});

test("a match group opens its restaurants", async () => {
  render(<App />);

  await userEvent.click(await screen.findByRole("button", { name: /^A revisar/ }));

  expect(await screen.findByText("Sushi Tres")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/venues/?group=review&page=1", expect.anything());
  expect(screen.getByRole("link", { name: "Revisarlos en el admin" })).toBeTruthy();
});

test("the top categories can be read as a table and opened", async () => {
  render(<App />);

  await userEvent.click(await screen.findByRole("button", { name: "Ver como tabla" }));
  await userEvent.click(await screen.findByRole("cell", { name: "pizza" }));

  expect(await screen.findByText("Detalle: pizza")).toBeTruthy();
  expect(screen.getByText("margherita")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/categories/detail/?level=parent&key=pizza", expect.anything());
});

test("the filters ask the API for drinks", async () => {
  render(<App />);

  await userEvent.click(await screen.findByRole("button", { name: "Bebida" }));

  expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/categories/?family=drink&level=parent&order=venues&top=15",
    expect.anything());
});

test("the extra detail is folded and asks for its data only when unfolded", async () => {
  render(<App />);
  const toggle = await screen.findByRole("button", { name: /Más detalle/ });

  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/dishes/"), expect.anything());

  await userEvent.click(toggle);

  expect(await screen.findByText("Margherita")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/dishes/?group=accepted&page=1", expect.anything());
  expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/menus/", expect.anything());
  expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/quality/", expect.anything());
});
