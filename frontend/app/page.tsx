"use client";

import { useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStats, listCompanies, listFindings } from "@/lib/api";
import type { Category, Line, SortBy, SortDir, Window } from "@/lib/types";
import { LINE_LABELS, LINES } from "@/lib/types";
import { FilterBar } from "@/components/FilterBar";
import { KpiCards } from "@/components/KpiCards";
import { AttentionPanel } from "@/components/AttentionPanel";
import { FeedList } from "@/components/FeedList";
import { RecordPanel } from "@/components/RecordPanel";

const LINE_STORE = "cw_line";
const LINE_EVENT = "competitor-watch-line-change";

function subscribeToLine(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(LINE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(LINE_EVENT, callback);
  };
}

function getStoredLine(): string {
  try { return localStorage.getItem(LINE_STORE) ?? "motor"; } catch { return "motor"; }
}

export default function Home() {
  const [windowValue, setWindowValue] = useState<Window>("week");
  const [category, setCategory] = useState<Category | undefined>();
  const storedLine = useSyncExternalStore(subscribeToLine, getStoredLine, () => "motor");
  const line = storedLine === "all" ? undefined : LINES.includes(storedLine as Line) ? storedLine as Line : "motor";
  const [company, setCompany] = useState<string | undefined>();
  const [sortBy, setSortBy] = useState<SortBy>("materiality");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selectedId, setSelectedId] = useState<number | undefined>();

  function changeLine(value: Line | undefined) {
    try {
      localStorage.setItem(LINE_STORE, value ?? "all");
      window.dispatchEvent(new Event(LINE_EVENT));
    } catch { /* localStorage may be unavailable in restricted browsers */ }
  }

  const filters = { window: windowValue, category, line, company };
  const { data: companies = [] } = useQuery({ queryKey: ["companies"], queryFn: listCompanies });
  const { data: findings = [], isLoading } = useQuery({
    queryKey: ["findings", filters, sortBy, sortDir],
    queryFn: () => listFindings({ ...filters, sort_by: sortBy, sort_dir: sortDir }),
  });
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["stats", filters],
    queryFn: () => getStats(filters),
  });
  const { data: attention = [] } = useQuery({
    queryKey: ["attention", filters],
    queryFn: () => listFindings({ ...filters, materiality: "high", sort_by: "materiality", sort_dir: "desc", limit: 3 }),
  });

  const effectiveSelectedId = selectedId && findings.some((finding) => finding.id === selectedId)
    ? selectedId
    : findings[0]?.id;
  const scope = `${line ? `${LINE_LABELS[line]} team view` : "All lines"} · ${stats?.current.findings ?? findings.length} finding${(stats?.current.findings ?? findings.length) === 1 ? "" : "s"}`;

  return (
    <main className="min-h-0 flex-1">
      <FilterBar
        window={windowValue}
        onWindowChange={setWindowValue}
        category={category}
        onCategoryChange={setCategory}
        line={line}
        onLineChange={changeLine}
        company={company}
        onCompanyChange={setCompany}
        companies={companies}
        sortBy={sortBy}
        sortDir={sortDir}
        onSortChange={(nextSortBy, nextSortDir) => { setSortBy(nextSortBy); setSortDir(nextSortDir); }}
        summary={scope}
      />

      <div className="mx-auto max-w-[1560px] px-4 pb-20 pt-5 sm:px-6">
        <KpiCards stats={stats} isLoading={statsLoading} />
        <AttentionPanel findings={attention} onSelect={setSelectedId} />

        <div className="mt-3 grid grid-cols-1 items-start gap-3 lg:grid-cols-[minmax(0,1fr)_400px]">
          <section className="min-w-0 overflow-hidden rounded-2xl border border-[#e9e9f2] bg-white">
            <FeedList
              findings={findings}
              selectedId={effectiveSelectedId}
              onSelect={setSelectedId}
              onLineSelect={changeLine}
              onCategorySelect={setCategory}
              isLoading={isLoading}
              sortBy={sortBy}
            />
          </section>
          <div className="lg:sticky lg:top-[13.5rem]">
            {effectiveSelectedId ? <RecordPanel id={effectiveSelectedId} /> : <div className="rounded-2xl border border-[#e9e9f2] bg-white p-8 text-center text-sm text-[#8b8ba0]">Select a finding to inspect its source and classification.</div>}
          </div>
        </div>
      </div>
    </main>
  );
}
