export type Category =
  | "product"
  | "marketing"
  | "news"
  | "social_sentiment"
  | "regulatory"
  | "investment_or_acquisition"
  | "financial_results"
  | "other";

export type Materiality = "low" | "medium" | "high";

export type Window = "today" | "week" | "month" | "year" | "all";

export type View = "full" | "summary";

export type SortBy = "materiality" | "published_at" | "retrieved_at";
export type SortDir = "asc" | "desc";

export interface Finding {
  id: number;
  keyword: string;
  company: string;
  category: Category;
  platform: string | null;
  source_url: string;
  title: string;
  summary: string;
  source_excerpt: string;
  published_at: string | null;
  retrieved_at: string;
  is_duplicate: boolean;
  materiality: Materiality | null;
  og_title: string | null;
  og_image_url: string | null;
  og_description: string | null;
  og_site_name: string | null;
  verified: boolean;
}

export interface Change {
  materiality: Materiality;
  confidence: number;
  evidence_quote: string;
  rationale: string;
}

export interface LlmCall {
  model: string;
  prompt: string;
  raw_output: string;
  called_at: string;
}

export interface FindingDetail extends Omit<Finding, "materiality"> {
  run_id: string;
  has_snapshot: boolean;
  change: Change | null;
  llm_call: LlmCall | null;
}

export interface Company {
  company: string;
  new_today: number;
  new_this_week: number;
  new_this_month: number;
  total_findings: number;
}

export interface CrawlStatus {
  latest_crawl_at: string | null;
}

export const CATEGORIES: Category[] = [
  "product",
  "marketing",
  "news",
  "social_sentiment",
  "regulatory",
  "investment_or_acquisition",
  "financial_results",
  "other",
];

export const CATEGORY_LABELS: Record<Category, string> = {
  product: "Product",
  marketing: "Marketing",
  news: "News",
  social_sentiment: "Social",
  regulatory: "Regulatory",
  investment_or_acquisition: "Investment/M&A",
  financial_results: "Financial Results",
  other: "Other",
};

export interface SortOption {
  value: string; // `${sortBy}:${sortDir}`, used as the Select's option value
  sortBy: SortBy;
  sortDir: SortDir;
  label: string;
}

export const SORT_OPTIONS: SortOption[] = [
  { value: "materiality:desc", sortBy: "materiality", sortDir: "desc", label: "Materiality (high to low)" },
  { value: "materiality:asc", sortBy: "materiality", sortDir: "asc", label: "Materiality (low to high)" },
  { value: "published_at:desc", sortBy: "published_at", sortDir: "desc", label: "Published date (newest first)" },
  { value: "published_at:asc", sortBy: "published_at", sortDir: "asc", label: "Published date (oldest first)" },
  { value: "retrieved_at:desc", sortBy: "retrieved_at", sortDir: "desc", label: "Crawled date (newest first)" },
  { value: "retrieved_at:asc", sortBy: "retrieved_at", sortDir: "asc", label: "Crawled date (oldest first)" },
];
