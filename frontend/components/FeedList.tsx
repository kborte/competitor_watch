"use client";

import type { Finding } from "@/lib/types";
import { FeedCard } from "./FeedCard";

interface FeedListProps {
  findings: Finding[];
  selectedId: number | undefined;
  onSelect: (id: number) => void;
  isLoading: boolean;
}

export function FeedList({ findings, selectedId, onSelect, isLoading }: FeedListProps) {
  if (isLoading) {
    return <p className="p-4 text-sm text-slate-400">Loading findings…</p>;
  }

  if (findings.length === 0) {
    return <p className="p-4 text-sm text-slate-400">No findings match these filters.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {findings.map((f) => (
        <FeedCard key={f.id} finding={f} selected={f.id === selectedId} onSelect={() => onSelect(f.id)} />
      ))}
    </div>
  );
}
