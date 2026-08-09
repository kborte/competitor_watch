"use client";

import type { Category, Finding, Line } from "@/lib/types";
import { CATEGORY_LABELS, LINE_LABELS } from "@/lib/types";
import { formatRelativeQatarDay } from "@/lib/time";

const MATERIALITY_LABEL = { high: "HIGH", medium: "MED", low: "LOW" } as const;

interface FeedCardProps {
  finding: Finding;
  selected: boolean;
  onSelect: () => void;
  onLineSelect?: (line: Line) => void;
  onCategorySelect?: (category: Category) => void;
}

export function FeedCard({ finding, selected, onSelect, onLineSelect, onCategorySelect }: FeedCardProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onSelect();
      }}
      className={`grid cursor-pointer grid-cols-[3px_minmax(0,1fr)_auto] gap-3 border-b border-[#f0f0f6] pr-5 transition hover:bg-[#fafafd] ${selected ? "bg-[#f6f5fe]" : "bg-white"}`}
    >
      <span className={selected ? "bg-[#5b4fe8]" : "bg-transparent"} />
      <div className="min-w-0 py-3.5">
        <h3 className={`text-sm leading-snug tracking-tight ${finding.materiality === "high" ? "font-semibold" : "font-medium"} ${finding.materiality === "low" ? "text-[#4a4a63]" : "text-[#1a1633]"}`}>{finding.title}</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold">{finding.company}</span>
          <span className="h-0.5 w-0.5 rounded-full bg-[#c9c9d8]" />
          {finding.line && (
            <button
              onClick={(event) => { event.stopPropagation(); onLineSelect?.(finding.line as Line); }}
              className="rounded-md bg-[#efedfe] px-2 py-0.5 text-[11px] font-medium text-[#4a3fd6]"
            >
              {LINE_LABELS[finding.line]}
            </button>
          )}
          <button
            onClick={(event) => { event.stopPropagation(); onCategorySelect?.(finding.category); }}
            className="rounded-md bg-[#f2f2f8] px-2 py-0.5 text-[11px] font-medium text-[#5a5a72]"
          >
            {CATEGORY_LABELS[finding.category]}
          </button>
          {finding.tone && <span className="text-[11px] capitalize text-[#8b8ba0]">{finding.tone}</span>}
          {!finding.verified && <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">Unverified</span>}
        </div>
      </div>
      <div className="py-3.5 text-right">
        <div className="whitespace-nowrap text-[11px] text-[#6c6c85]">{formatRelativeQatarDay(finding.retrieved_at)}</div>
        {finding.materiality && <div className={`mt-1 font-mono text-[10px] tracking-wider ${finding.materiality === "high" ? "text-[#c4433a]" : "text-[#6c6c85]"}`}>{MATERIALITY_LABEL[finding.materiality]}</div>}
      </div>
    </div>
  );
}
