import type { Finding } from "./types";

/**
 * Social-source titles are often just page labels ("Customer Reviews",
 * "Reddit Discussion"). Their structured summaries contain the actual
 * cross-review signal, so promote that grounded signal to the headline.
 */
export function headlineForFinding(finding: Pick<Finding, "category" | "title" | "summary">): string {
  const headline = finding.category === "social_sentiment" && finding.summary.trim()
    ? finding.summary.trim()
    : finding.title.trim();
  return headline.replace(/[.!?]+$/, "");
}
