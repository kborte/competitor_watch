"use client";

import * as Tabs from "@radix-ui/react-tabs";
import type { Category, Company, Window } from "@/lib/types";
import { CATEGORIES, CATEGORY_LABELS } from "@/lib/types";

const WINDOWS: { value: Window; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "all", label: "All" },
];

const ALL_CATEGORIES = "__all__";

function tabTriggerClass(active: boolean) {
  return [
    "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
    active ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-slate-800",
  ].join(" ");
}

function chipClass(active: boolean) {
  return [
    "shrink-0 rounded-full border px-3 py-1 text-sm font-medium transition-colors",
    active
      ? "border-indigo-600 bg-indigo-600 text-white"
      : "border-slate-300 text-slate-600 hover:border-slate-400",
  ].join(" ");
}

interface FilterBarProps {
  window: Window;
  onWindowChange: (value: Window) => void;
  category: Category | undefined;
  onCategoryChange: (value: Category | undefined) => void;
  company: string | undefined;
  onCompanyChange: (value: string | undefined) => void;
  companies: Company[];
  summary: string;
}

export function FilterBar({
  window: windowValue,
  onWindowChange,
  category,
  onCategoryChange,
  company,
  onCompanyChange,
  companies,
  summary,
}: FilterBarProps) {
  return (
    <div className="border-b border-slate-200 bg-white px-6 py-3">
      <Tabs.Root value={windowValue} onValueChange={(v) => onWindowChange(v as Window)}>
        <Tabs.List className="flex gap-1">
          {WINDOWS.map((w) => (
            <Tabs.Trigger key={w.value} value={w.value} className={tabTriggerClass(windowValue === w.value)}>
              {w.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
      </Tabs.Root>

      <div className="mt-3">
        <Tabs.Root
          value={category ?? ALL_CATEGORIES}
          onValueChange={(v) => onCategoryChange(v === ALL_CATEGORIES ? undefined : (v as Category))}
        >
          <Tabs.List className="flex flex-wrap gap-1">
            <Tabs.Trigger value={ALL_CATEGORIES} className={tabTriggerClass(category === undefined)}>
              All categories
            </Tabs.Trigger>
            {CATEGORIES.map((c) => (
              <Tabs.Trigger key={c} value={c} className={tabTriggerClass(category === c)}>
                {CATEGORY_LABELS[c]}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </Tabs.Root>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
          <button className={chipClass(company === undefined)} onClick={() => onCompanyChange(undefined)}>
            All
          </button>
          {companies.map((c) => (
            <button
              key={c.company}
              className={chipClass(company === c.company)}
              onClick={() => onCompanyChange(c.company)}
            >
              {c.company}
            </button>
          ))}
        </div>
        <span className="shrink-0 text-sm text-slate-400">{summary}</span>
      </div>
    </div>
  );
}
