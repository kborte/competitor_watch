"use client";

import type { Finding } from "@/lib/types";
import { CATEGORY_LABELS } from "@/lib/types";
import { formatQatarDate, formatRelativeQatarDay } from "@/lib/time";
import { LinkPreviewCard } from "./LinkPreviewCard";

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
  // A <div> acting as a button, not a real <button> — LinkPreviewCard
  // renders an <a>, and nesting interactive `<a>`/`<button>` elements
  // inside a `<button>` is invalid HTML (and breaks focus/click behavior).
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect();
      }}
      className={[
        "w-full cursor-pointer rounded-xl border bg-white p-4 text-left transition-colors",
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
        {!finding.verified && (
          <span
            className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700"
            title="The source page couldn't be independently fetched — this claim rests on the research summary alone."
          >
            Unverified
          </span>
        )}
        <span className="ml-auto shrink-0 text-xs text-slate-400">
          {formatRelativeQatarDay(finding.retrieved_at)}
        </span>
      </div>

      <h3 className="mt-2 text-base font-semibold text-slate-900">{finding.title}</h3>
      <p className="mt-1 text-sm text-slate-600">{finding.summary}</p>

      <p className="mt-2 text-xs text-slate-400">
        {finding.published_at && <>Published {formatQatarDate(finding.published_at)} · </>}
        Crawled {formatQatarDate(finding.retrieved_at)}
      </p>

      <div className="mt-3">
        <LinkPreviewCard
          url={finding.source_url}
          ogTitle={finding.og_title}
          ogImageUrl={finding.og_image_url}
          ogSiteName={finding.og_site_name}
        />
      </div>
    </div>
  );
}
