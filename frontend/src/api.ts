// The dashboard API (Django, apps/dashboard): read-only, same site, session cookie. What each endpoint answers
// is the contract in schemas.ts.

import type {
  CategoryDetail,
  CategoryRow,
  DishGroup,
  DishRow,
  Family,
  Level,
  MatchGroup,
  Menus,
  Order,
  Page,
  Quality,
  Summary,
  VenueRow,
} from "./schemas";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string, params: Record<string, string | number> = {}): Promise<T> {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const response = await fetch(`/api/dashboard/${path}/${query.size ? `?${query}` : ""}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (response.status === 401 || response.status === 403) {
    window.location.assign("/accounts/login/?next=/dashboard/");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? `Error ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  summary: () => get<Summary>("summary"),
  categories: (family: Family, level: Level, order: Order, top: number) =>
    get<CategoryRow[]>("categories", { family, level, order, top }),
  category: (level: Level, key: string) => get<CategoryDetail>("categories/detail", { level, key }),
  venues: (group: MatchGroup, page: number) => get<Page<VenueRow>>("venues", { group, page }),
  dishes: (group: DishGroup, page: number) => get<Page<DishRow>>("dishes", { group, page }),
  menus: () => get<Menus>("menus"),
  quality: () => get<Quality>("quality"),
};

export function logout(): void {
  // Django's logout is a POST protected by CSRF: the token comes from the cookie the page set.
  const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? "";
  const form = document.createElement("form");
  form.method = "post";
  form.action = "/accounts/logout/";
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = "csrfmiddlewaretoken";
  input.value = decodeURIComponent(token);
  form.append(input);
  document.body.append(form);
  form.submit();
}
