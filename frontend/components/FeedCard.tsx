"use client";

import type { Finding } from "@/lib/types";
import { CATEGORY_LABELS } from "@/lib/types";
import { formatRelativeQatarDay } from "@/lib/time";

const MATERIALITY_CLASS: Record<string, string> = {
  high: "bg-rose-100 text-rose-700",
  medium: "bg-slate-100 text-slate-600",
  low: "bg-slate-100 text-slate-500",
};

interface FeedCardProps {
  finding: Finding;
  selected: boolean;
  onSelect: () => void;
}

export function FeedCard({ finding, selected, onSelect }: FeedCardProps) {
  let sourceDomain = finding.source_url;
  try {
    sourceDomain = new URL(finding.source_url).hostname.replace(/^www\./, "");
  } catch {
    // leave as-is if it's not a parseable URL
  }

  return (
    <button
      onClick={onSelect}
      className={[
        "w-full rounded-xl border bg-white p-4 text-left transition-colors",
        selected ? "border-indigo-400 ring-1 ring-indigo-400" : "border-slate-200 hover:border-slate-300",
      ].join(" ")}
    >
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <span className="font-medium text-slate-700">{finding.company}</span>
        <span>·</span>
        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
          {CATEGORY_LABELS[finding.category]}
        </span>
        {finding.materiality && (
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${MATERIALITY_CLASS[finding.materiality]}`}>
            {finding.materiality[0].toUpperCase() + finding.materiality.slice(1)}
          </span>
        )}
        <span className="ml-auto shrink-0 text-xs text-slate-400">
          {formatRelativeQatarDay(finding.retrieved_at)}
        </span>
      </div>

      <h3 className="mt-2 text-base font-semibold text-slate-900">{finding.title}</h3>
      <p className="mt-1 text-sm text-slate-600">{finding.summary}</p>
      <p className="mt-2 truncate text-xs text-slate-400">{sourceDomain}</p>
    </button>
  );
}
