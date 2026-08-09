"use client";

import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import { getCrawlStatus } from "@/lib/api";
import { formatQatarDateTime } from "@/lib/time";

export function Header() {
  const { data } = useQuery({ queryKey: ["crawl-status"], queryFn: getCrawlStatus, refetchInterval: 60_000 });
  return (
    <header className="sticky top-0 z-40 flex h-12 items-center gap-3 bg-[#241c55] px-4 text-white sm:px-6">
      <span className="relative h-7 w-10 overflow-hidden rounded-md bg-white">
        <Image src="/logos/qic.png" alt="QIC" fill sizes="40px" className="object-contain p-1" priority />
      </span>
      <span className="text-sm font-semibold tracking-tight">Competitor Watch</span>
      <span className="ml-auto font-mono text-[10px] text-white/50 sm:text-[11px]">
        {data?.latest_crawl_at ? `crawled ${formatQatarDateTime(data.latest_crawl_at)}` : "no crawl data yet"}
      </span>
    </header>
  );
}
