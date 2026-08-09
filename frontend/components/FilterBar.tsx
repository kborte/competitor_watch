"use client";

import Image from "next/image";
import type { Category, Company, Line, SortBy, SortDir, Window } from "@/lib/types";
import {
  CATEGORIES, CATEGORY_LABELS, LINES, LINE_LABELS, SORT_OPTIONS,
} from "@/lib/types";
import { initialsForCompany, logoForCompany } from "@/lib/companies";
import { Select } from "./Select";

const WINDOWS: { value: Window; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
  { value: "year", label: "Year" },
  { value: "all", label: "All" },
];

const ALL = "__all__";

function CompanyAvatar({ company }: { company: string }) {
  const logo = logoForCompany(company);
  if (logo) {
    return (
      <span className="relative grid h-5 w-5 shrink-0 place-items-center overflow-hidden rounded-md bg-white ring-1 ring-black/5">
        <Image src={logo} alt="" fill sizes="20px" className="object-contain p-0.5" />
      </span>
    );
  }
  return (
    <span className="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-violet-100 text-[8px] font-bold text-violet-700">
      {initialsForCompany(company)}
    </span>
  );
}

interface FilterBarProps {
  window: Window;
  onWindowChange: (value: Window) => void;
  category: Category | undefined;
  onCategoryChange: (value: Category | undefined) => void;
  line: Line | undefined;
  onLineChange: (value: Line | undefined) => void;
  company: string | undefined;
  onCompanyChange: (value: string | undefined) => void;
  companies: Company[];
  sortBy: SortBy;
  sortDir: SortDir;
  onSortChange: (sortBy: SortBy, sortDir: SortDir) => void;
  summary: string;
}

export function FilterBar(props: FilterBarProps) {
  const categoryOptions = [
    { value: ALL, label: "All categories" },
    ...CATEGORIES.map((category) => ({ value: category, label: CATEGORY_LABELS[category] })),
  ];

  return (
    <div className="sticky top-12 z-30 border-b border-[#e4e4ee] bg-white shadow-[0_1px_0_rgba(26,22,51,0.02)]">
      <div className="flex min-h-12 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 sm:px-6">
        <ControlLabel>Period</ControlLabel>
        <div className="flex rounded-lg bg-[#f2f2f8] p-0.5">
          {WINDOWS.map((item) => (
            <button
              key={item.value}
              onClick={() => props.onWindowChange(item.value)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                props.window === item.value
                  ? "bg-white text-[#1a1633] shadow-sm"
                  : "text-[#6c6c85] hover:text-[#1a1633]"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <Divider />
        <ControlLabel>Category</ControlLabel>
        <Select
          value={props.category ?? ALL}
          onValueChange={(value) => props.onCategoryChange(value === ALL ? undefined : value as Category)}
          options={categoryOptions}
          ariaLabel="Filter by category"
        />

        <Divider />
        <ControlLabel>Sort</ControlLabel>
        <Select
          value={`${props.sortBy}:${props.sortDir}`}
          onValueChange={(value) => {
            const option = SORT_OPTIONS.find((candidate) => candidate.value === value);
            if (option) props.onSortChange(option.sortBy, option.sortDir);
          }}
          options={SORT_OPTIONS}
          ariaLabel="Sort findings"
        />

        <span className="ml-auto hidden text-xs text-[#8b8ba0] xl:block">{props.summary}</span>
      </div>

      <FilterRow label="Line">
        <Chip active={props.line === undefined} onClick={() => props.onLineChange(undefined)}>
          All lines
        </Chip>
        {LINES.map((line) => (
          <Chip key={line} active={props.line === line} onClick={() => props.onLineChange(line)}>
            {LINE_LABELS[line]}
          </Chip>
        ))}
      </FilterRow>

      <FilterRow label="Company">
        <Chip active={props.company === undefined} onClick={() => props.onCompanyChange(undefined)}>
          All companies
        </Chip>
        {props.companies.map((company) => (
          <Chip
            key={company.company}
            active={props.company === company.company}
            onClick={() => props.onCompanyChange(company.company)}
          >
            <CompanyAvatar company={company.company} />
            {company.company}
          </Chip>
        ))}
      </FilterRow>
    </div>
  );
}

function ControlLabel({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-[10px] font-medium uppercase tracking-[0.11em] text-[#a3a3b8]">{children}</span>;
}

function Divider() {
  return <span className="hidden h-5 w-px bg-[#ededf4] sm:block" />;
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-12 items-center gap-3 border-t border-[#f0f0f6] px-4 sm:px-6">
      <ControlLabel>{label}</ControlLabel>
      <div className="no-scrollbar flex min-w-0 flex-1 items-center gap-2 overflow-x-auto py-2">{children}</div>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
        active
          ? "border-[#5b4fe8] bg-[#5b4fe8] text-white"
          : "border-[#e0e0ec] bg-white text-[#4a4a63] hover:border-[#c7c0fa]"
      }`}
    >
      {children}
    </button>
  );
}
