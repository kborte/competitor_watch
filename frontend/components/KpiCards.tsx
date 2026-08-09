import type { DashboardStats, Window } from "@/lib/types";

const WINDOW_COPY: Record<Window, { label: string; previous: string }> = {
  today: { label: "Findings today", previous: "yesterday" },
  week: { label: "Findings this week", previous: "the week before" },
  month: { label: "Findings this month", previous: "the month before" },
  year: { label: "Findings this year", previous: "the year before" },
  all: { label: "All findings", previous: "" },
};

export function KpiCards({ stats, isLoading }: { stats: DashboardStats | undefined; isLoading: boolean }) {
  const copy = WINDOW_COPY[stats?.window ?? "week"];
  const delta = stats?.delta;
  const tone = stats?.current.tone;
  const competitorTone = !tone || Object.values(tone).every((count) => count === 0)
    ? "No signal"
    : tone.negative > tone.positive
      ? `Falling · ${tone.negative} negative`
      : tone.positive > tone.negative
        ? `Improving · ${tone.positive} positive`
        : "Flat";

  const qic = stats?.qic_reference;
  const qicDirection = qic?.previous_mentions == null
    ? ""
    : qic.mentions > qic.previous_mentions ? "Rising · "
      : qic.mentions < qic.previous_mentions ? "Falling · " : "Flat · ";

  if (isLoading && !stats) {
    return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((n) => <div key={n} className="h-28 animate-pulse rounded-2xl bg-white" />)}</div>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label={copy.label}>
        <div className="flex items-baseline gap-2">
          <strong className="text-3xl font-semibold tracking-tight">{stats?.current.findings ?? 0}</strong>
          {delta != null && <span className={`text-xs font-semibold ${delta > 0 ? "text-[#c4433a]" : "text-[#6c6c85]"}`}>{delta >= 0 ? "↑" : "↓"} {Math.abs(delta)}</span>}
        </div>
        <Note>{stats?.previous ? `${stats.previous.findings} in ${copy.previous}` : "complete history in scope"}</Note>
      </MetricCard>

      <MetricCard label="Need attention">
        <div className="flex items-baseline gap-2">
          <strong className={`text-3xl font-semibold ${stats?.current.high_materiality ? "text-[#c4433a]" : ""}`}>{stats?.current.high_materiality ?? 0}</strong>
          <span className="text-xs font-semibold text-[#8b8ba0]">high materiality</span>
        </div>
        <Note>{stats?.current.high_materiality ? "read these first" : "nothing urgent in scope"}</Note>
      </MetricCard>

      <MetricCard label="Most active">
        <strong className="mt-1 block truncate text-xl font-semibold tracking-tight">{stats?.most_active?.company ?? "—"}</strong>
        <Note>{stats?.most_active ? `${stats.most_active.count} finding${stats.most_active.count === 1 ? "" : "s"} in scope` : "no activity in scope"}</Note>
      </MetricCard>

      <MetricCard label="Sentiment">
        <div className="mt-1 space-y-1.5 text-sm">
          <div><strong className={tone && tone.negative > tone.positive ? "text-[#c4433a]" : "text-[#4a4a63]"}>{competitorTone}</strong> <span className="text-xs text-[#8b8ba0]">competitors</span></div>
          <div><strong className="text-[#4a4a63]">{qicDirection}{qic?.mentions ?? 0} mentions</strong> <span className="text-xs text-[#8b8ba0]">QIC reference</span></div>
        </div>
      </MetricCard>
    </div>
  );
}

function MetricCard({ label, children }: { label: string; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-[#e9e9f2] bg-white px-5 py-4"><div className="mb-2 text-xs text-[#8b8ba0]">{label}</div>{children}</section>;
}

function Note({ children }: { children: React.ReactNode }) {
  return <div className="mt-2 text-xs text-[#a3a3b8]">{children}</div>;
}
