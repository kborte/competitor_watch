"use client";

import type { Category, Finding, Line, SortBy } from "@/lib/types";
import { FeedCard } from "./FeedCard";

interface FeedListProps {
  findings: Finding[];
  selectedId: number | undefined;
  onSelect: (id: number) => void;
  onLineSelect: (line: Line) => void;
  onCategorySelect: (category: Category) => void;
  isLoading: boolean;
  sortBy: SortBy;
}

function groupLabel(finding: Finding, sortBy: SortBy): string {
  if (sortBy === "materiality") {
    if (finding.materiality === "high") return "High materiality";
    if (finding.materiality === "medium") return "Medium";
    if (finding.materiality === "low") return "Low";
    return "Unclassified";
  }
  const then = new Date(finding.published_at ?? finding.retrieved_at);
  const days = Math.max(0, Math.floor((Date.now() - then.getTime()) / 86_400_000));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 3) return "Earlier this week";
  if (days <= 7) return "Last week";
  if (days <= 31) return "This month";
  return "Older";
}

export function FeedList(props: FeedListProps) {
  if (props.isLoading) return <p className="p-8 text-center text-sm text-[#8b8ba0]">Loading findings…</p>;
  if (props.findings.length === 0) return <div className="p-10 text-center"><p className="text-sm font-semibold">No findings for these filters</p><p className="mt-1 text-xs text-[#8b8ba0]">Widen the line or clear another filter.</p></div>;

  const groups = new Map<string, Finding[]>();
  for (const finding of props.findings) {
    const label = groupLabel(finding, props.sortBy);
    groups.set(label, [...(groups.get(label) ?? []), finding]);
  }

  return (
    <div>
      {[...groups.entries()].map(([label, findings]) => (
        <section key={label}>
          <div className="flex items-baseline gap-2 border-y border-[#f0f0f6] bg-[#fafafd] px-5 py-2.5 font-mono text-[10px] uppercase tracking-[0.1em] text-[#6c6c85] first:border-t-0">
            <span>{label}</span><span className="text-[#a3a3b8]">{findings.length}</span>
          </div>
          {findings.map((finding) => (
            <FeedCard
              key={finding.id}
              finding={finding}
              selected={finding.id === props.selectedId}
              onSelect={() => props.onSelect(finding.id)}
              onLineSelect={props.onLineSelect}
              onCategorySelect={props.onCategorySelect}
            />
          ))}
        </section>
      ))}
    </div>
  );
}
