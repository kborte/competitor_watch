"use client";

import type { SortBy, SortDir } from "@/lib/types";
import { SORT_OPTIONS } from "@/lib/types";
import { Select } from "./Select";

interface SortSelectProps {
  sortBy: SortBy;
  sortDir: SortDir;
  onChange: (sortBy: SortBy, sortDir: SortDir) => void;
}

export function SortSelect({ sortBy, sortDir, onChange }: SortSelectProps) {
  const value = `${sortBy}:${sortDir}`;
  return (
    <div className="flex items-center gap-2 pb-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Sort</span>
      <Select
        value={value}
        onValueChange={(v) => {
          const option = SORT_OPTIONS.find((o) => o.value === v);
          if (option) onChange(option.sortBy, option.sortDir);
        }}
        options={SORT_OPTIONS}
        ariaLabel="Sort findings"
      />
    </div>
  );
}
