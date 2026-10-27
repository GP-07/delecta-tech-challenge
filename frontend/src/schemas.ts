// The contract of the dashboard API, as the frontend sees it. It mirrors, by hand, the response serializers of
// the backend (src/apps/dashboard/serializers.py): same names without "Serializer", same fields
// (VenueRowSerializer <-> VenueRow). Changing a field there means changing it here too, and `tsc` then points
// at every component that uses it.

// --- values the API accepts and answers (constants.py and the choices of the models) -------------------------

export type MatchGroup = "accepted" | "confirmed" | "review" | "rejected" | "unmatched"; // MatchGroup
export type DishGroup = "accepted" | "confirmed"; // DISH_GROUPS
export type Family = "food" | "drink"; // FAMILIES
export type Level = "parent" | "name"; // LEVELS
export type Order = "venues" | "items"; // ORDERS
export type RunStatus = "WAITING" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED"; // pipeline Status
export type MatchStatus = "ACCEPTED" | "REVIEW" | "CONFIRMED" | "REJECTED"; // venues MatchStatus
export type Method = // menus Method
  "name" | "section" | "description" | "embedding" | "non_food" | "unknown" | "pending" | "manual";

// --- summary/ -----------------------------------------------------------------------------------------------

export interface NewerRun {
  id: number;
  status: RunStatus;
}

export interface Step {
  name: string;
  status: RunStatus;
  seconds: number | null;
}

export interface RunInfo {
  id: number;
  finished_at: string; // ISO 8601
  seconds: number | null;
  newer_run: NewerRun | null;
  steps: Step[];
}

export interface MatchedRestaurants {
  matched: number;
  crawled: number;
}

export type MatchGroups = Record<MatchGroup, number>;

export interface Summary {
  run: RunInfo;
  matched: MatchedRestaurants;
  match_groups: MatchGroups;
}

// --- venues/ ------------------------------------------------------------------------------------------------

export interface GoogleLink {
  name: string;
  address: string;
  star_rating: number | null;
  rating_count: number | null;
  status: MatchStatus;
  score: number;
  distance_m: number;
  reason: string;
}

export interface VenueRow {
  id: string;
  name: string;
  city: string;
  address: string;
  url: string;
  cuisines: string[];
  star_rating: number | null;
  rating_count: number | null;
  google: GoogleLink | null;
}

// --- categories/ and categories/detail/ ---------------------------------------------------------------------

export interface CategoryRow {
  key: string;
  family: Family;
  items: number;
  venues: number;
  venues_share: number;
  median_price: number | null;
}

export interface Subcategory {
  key: string;
  items: number;
  venues: number;
  median_price: number | null;
}

export interface TopDish {
  name: string;
  items: number;
  median_price: number | null;
}

export interface TopVenue {
  name: string;
  items: number;
}

export interface CategoryDetail {
  key: string;
  level: Level;
  family: Family;
  items: number;
  venues: number;
  median_price: number | null;
  subcategories: Subcategory[];
  top_dishes: TopDish[];
  top_venues: TopVenue[];
}

// --- dishes/ ------------------------------------------------------------------------------------------------

export interface DishRow {
  id: number;
  venue: string;
  name: string;
  section: string;
  category: string | null;
  parent: string | null;
  family: Family | null;
  confidence: number;
  method: Method;
  price: number | null;
}

// --- menus/ and quality/ ------------------------------------------------------------------------------------

export interface Menus {
  venues: number;
  median_items: number | null;
  venues_with_drinks: number;
  combo_share: number;
}

export interface QualityItems {
  total: number;
  categorized: number;
  low_confidence: number;
  pending: number;
}

export interface MethodCount {
  method: Method;
  label: string;
  items: number;
}

export interface ConfidenceBucket {
  bucket: string;
  items: number;
}

export interface Quality {
  items: QualityItems;
  methods: MethodCount[];
  confidence: ConfidenceBucket[];
}

// --- the paginated lists (DRF's PageNumberPagination) -------------------------------------------------------

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
