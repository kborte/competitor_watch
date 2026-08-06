"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listCompanies, listFindings } from "@/lib/api";
import type { Category, Window } from "@/lib/types";
import { FilterBar } from "@/components/FilterBar";
import { SortToggle } from "@/components/SortToggle";
import { FeedList } from "@/components/FeedList";
import { RecordPanel } from "@/components/RecordPanel";

export default function Home() {
  const [windowValue, setWindowValue] = useState<Window>("week");
  const [category, setCategory] = useState<Category | undefined>(undefined);
  const [company, setCompany] = useState<string | undefined>(undefined);
  const [chronological, setChronological] = useState(false);
  const [selectedId, setSelectedId] = useState<number | undefined>(undefined);

  const canPrioritize = windowValue === "week" || windowValue === "month";

  const { data: companies = [] } = useQuery({
    queryKey: ["companies"],
    queryFn: listCompanies,
  });

  const { data: findings = [], isLoading } = useQuery({
    queryKey: ["findings", windowValue, category, company, canPrioritize && chronological],
    queryFn: () =>
      listFindings({
        window: windowValue,
        category,
        company,
        prioritized: canPrioritize ? !chronological : undefined,
      }),
  });

  // Derived, not synced via effect: falls back to the first result whenever
  // the current selection isn't in the (possibly just-changed) result set.
  const effectiveSelectedId =
    selectedId && findings.some((f) => f.id === selectedId) ? selectedId : findings[0]?.id;

  return (
    <main className="flex flex-1 flex-col">
      <FilterBar
        window={windowValue}
        onWindowChange={setWindowValue}
        category={category}
        onCategoryChange={setCategory}
        company={company}
        onCompanyChange={setCompany}
        companies={companies}
        summary={`${findings.length} finding${findings.length === 1 ? "" : "s"}`}
      />

      <div className="grid flex-1 grid-cols-1 gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div>
          {canPrioritize && (
            <SortToggle
              chronological={chronological}
              onToggle={() => setChronological((v) => !v)}
              count={findings.length}
            />
          )}
          <FeedList findings={findings} selectedId={effectiveSelectedId} onSelect={setSelectedId} isLoading={isLoading} />
        </div>

        <div>
          {effectiveSelectedId ? (
            <RecordPanel id={effectiveSelectedId} />
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-400">
              Select a finding to see the full record.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
