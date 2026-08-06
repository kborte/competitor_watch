"use client";

import { useQuery } from "@tanstack/react-query";
import { getCrawlStatus } from "@/lib/api";
import { formatQatarDateTime } from "@/lib/time";

export function Header() {
  const { data } = useQuery({
    queryKey: ["crawl-status"],
    queryFn: getCrawlStatus,
    refetchInterval: 60_000,
  });

  return (
    <header className="flex items-center justify-between bg-indigo-600 px-6 py-4 text-white">
      <div className="flex items-center gap-3">
        <span className="rounded bg-white/15 px-2 py-1 text-xs font-bold tracking-wide">
          QIC
        </span>
        <span className="text-lg font-semibold">Competitor Watch</span>
      </div>
      <span className="text-sm text-white/80">
        {data?.latest_crawl_at
          ? `Crawled ${formatQatarDateTime(data.latest_crawl_at)}`
          : "No crawl data yet"}
      </span>
    </header>
  );
}
