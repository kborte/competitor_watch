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

async function getJson<T>(path: string, params?: object): Promise<T> {
  const url = new URL(path, BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  const res = await fetch(url);
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
  return new URL(`/findings/${id}/snapshot`, BASE_URL).toString();
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
