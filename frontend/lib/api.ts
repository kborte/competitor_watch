import type {
  Category,
  Company,
  CrawlStatus,
  Finding,
  FindingDetail,
  DashboardStats,
  Line,
  Materiality,
  SortBy,
  SortDir,
  View,
  Window,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

if (!BASE_URL) {
  throw new Error("NEXT_PUBLIC_API_BASE_URL is not set");
}

// Trailing slashes trimmed once, so "/api" and "/api/" behave identically.
const API_ROOT = BASE_URL.replace(/\/+$/, "");

/**
 * Joins the API root and a path by concatenation, deliberately not via
 * `new URL(path, base)`.
 *
 * `new URL()` resolves an absolute path against the base's *origin* and throws
 * the base's own path away: `new URL("/findings", "https://host/api")` yields
 * "https://host/findings" — the "/api" prefix silently vanishes. A relative
 * base is rejected outright, so `NEXT_PUBLIC_API_BASE_URL="/api"` would throw
 * a TypeError at the first request.
 *
 * A relative root is what lets one image serve every environment: the
 * dashboard and the API share an origin behind the Ingress, so the browser
 * resolves "/api/findings" against whatever domain the page was served from.
 */
function apiUrl(path: string, params?: object): string {
  const query = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) query.set(key, String(value));
    }
  }
  const suffix = query.toString();
  return `${API_ROOT}${path}${suffix ? `?${suffix}` : ""}`;
}

async function getJson<T>(path: string, params?: object): Promise<T> {
  const res = await fetch(apiUrl(path, params));
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

export interface ListFindingsParams {
  company?: string;
  category?: Category;
  line?: Line;
  materiality?: Materiality;
  window?: Window;
  sort_by?: SortBy;
  sort_dir?: SortDir;
  include_duplicates?: boolean;
  limit?: number;
  offset?: number;
}

export function listFindings(params: ListFindingsParams = {}): Promise<Finding[]> {
  return getJson<Finding[]>("/findings", params);
}

export function getFinding(id: number, view: View = "full"): Promise<FindingDetail> {
  return getJson<FindingDetail>(`/findings/${id}`, { view });
}

export function getSnapshotUrl(id: number): string {
  return apiUrl(`/findings/${id}/snapshot`);
}

export function listCompanies(): Promise<Company[]> {
  return getJson<Company[]>("/companies");
}

export function getCrawlStatus(): Promise<CrawlStatus> {
  return getJson<CrawlStatus>("/crawl-status");
}

export interface GetStatsParams {
  company?: string;
  category?: Category;
  line?: Line;
  window?: Window;
}

export function getStats(params: GetStatsParams = {}): Promise<DashboardStats> {
  return getJson<DashboardStats>("/stats", params);
}
