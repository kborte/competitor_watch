"use client";

import * as Tabs from "@radix-ui/react-tabs";
import Image from "next/image";
import type { Category, Company, Window } from "@/lib/types";
import { CATEGORIES, CATEGORY_LABELS } from "@/lib/types";
import { initialsForCompany, logoForCompany } from "@/lib/companies";
import { Select } from "./Select";

const WINDOWS: { value: Window; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "year", label: "This Year" },
  { value: "all", label: "All" },
];

const ALL_CATEGORIES = "__all__";

function windowTabClass(active: boolean) {
  return [
    "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
    active ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-slate-800",
  ].join(" ");
}

// Deliberately a different shape/surface than the window tabs (rounded
// rectangle, bordered, avatar-forward) so the three filter types read as
// different kinds of controls, not a wall of identical pills.
function companyChipClass(active: boolean, hasAvatar: boolean) {
  return [
    "flex shrink-0 items-center gap-2 rounded-lg border py-1 text-sm font-medium transition-colors",
    hasAvatar ? "pl-1.5 pr-3" : "px-3",
    active
      ? "border-indigo-600 bg-indigo-50 text-indigo-700"
      : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white",
  ].join(" ");
}

function CompanyAvatar({ company }: { company: string }) {
  const logo = logoForCompany(company);
  if (logo) {
    return (
      <span className="relative flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white ring-1 ring-slate-200">
        <Image src={logo} alt="" fill sizes="20px" className="object-contain p-0.5" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-300 text-[9px] font-bold text-white">
      {initialsForCompany(company)}
    </span>
  );
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
  const categoryOptions = [
    { value: ALL_CATEGORIES, label: "All categories" },
    ...CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABELS[c] })),
  ];

  return (
    <div className="border-b border-slate-200 bg-white px-6 py-3">
      <Tabs.Root value={windowValue} onValueChange={(v) => onWindowChange(v as Window)}>
        <Tabs.List className="flex flex-wrap gap-1">
          {WINDOWS.map((w) => (
            <Tabs.Trigger key={w.value} value={w.value} className={windowTabClass(windowValue === w.value)}>
              {w.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
      </Tabs.Root>

      <div className="mt-3 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Category</span>
        <Select
          value={category ?? ALL_CATEGORIES}
          onValueChange={(v) => onCategoryChange(v === ALL_CATEGORIES ? undefined : (v as Category))}
          options={categoryOptions}
          ariaLabel="Filter by category"
        />
      </div>

      <div className="mt-3 flex items-center gap-3">
        <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
          <button
            className={companyChipClass(company === undefined, false)}
            onClick={() => onCompanyChange(undefined)}
          >
            All
          </button>
          {companies.map((c) => (
            <button
              key={c.company}
              className={companyChipClass(company === c.company, true)}
              onClick={() => onCompanyChange(c.company)}
            >
              <CompanyAvatar company={c.company} />
              {c.company}
            </button>
          ))}
        </div>
        <span className="shrink-0 text-sm text-slate-400">{summary}</span>
      </div>
    </div>
  );
}
