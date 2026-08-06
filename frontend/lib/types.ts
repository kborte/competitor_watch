export type Category =
  | "product"
  | "marketing"
  | "news"
  | "social_sentiment"
  | "regulatory"
  | "other";

export type Materiality = "low" | "medium" | "high";

export type Window = "today" | "week" | "month" | "all";

export type View = "full" | "summary";

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
  "other",
];

export const CATEGORY_LABELS: Record<Category, string> = {
  product: "Product",
  marketing: "Marketing",
  news: "News",
  social_sentiment: "Social",
  regulatory: "Regulatory",
  other: "Other",
};
