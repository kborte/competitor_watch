"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as Collapsible from "@radix-ui/react-collapsible";
import { getFinding, getSnapshotUrl } from "@/lib/api";
import { CATEGORY_LABELS, LINE_LABELS } from "@/lib/types";
import { formatQatarDate, formatQatarDateTime } from "@/lib/time";
import { headlineForFinding } from "@/lib/findings";
import { LinkPreviewCard } from "./LinkPreviewCard";

export function RecordPanel({ id }: { id: number }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [showRawLog, setShowRawLog] = useState(false);
  const [showSnapshot, setShowSnapshot] = useState(false);
  const { data: summary, isLoading } = useQuery({
    queryKey: ["finding", id, "summary"],
    queryFn: () => getFinding(id, "summary"),
  });
  const { data: full } = useQuery({
    queryKey: ["finding", id, "full"],
    queryFn: () => getFinding(id, "full"),
    enabled: detailOpen,
  });

  if (isLoading || !summary) return <div className="rounded-2xl border border-[#e9e9f2] bg-white p-8 text-sm text-[#8b8ba0]">Loading record…</div>;

  let sourceName = summary.og_site_name;
  if (!sourceName) {
    try { sourceName = new URL(summary.source_url).hostname.replace(/^www\./, ""); } catch { sourceName = "Source"; }
  }

  return (
    <aside className="overflow-hidden rounded-2xl border border-[#e9e9f2] bg-white">
      <div className="max-h-[calc(100vh-14.5rem)] overflow-y-auto p-5">
        <div className="flex items-baseline gap-2">
          <span className="min-w-0 truncate font-mono text-[10px] uppercase tracking-[0.1em] text-[#a3a3b8]">{sourceName}</span>
          <a href={summary.source_url} target="_blank" rel="noreferrer" className="ml-auto shrink-0 text-xs font-semibold text-[#5b4fe8] hover:underline">Open source ↗</a>
        </div>

        <h2 className="mt-3 text-xl font-semibold leading-snug tracking-tight">{headlineForFinding(summary)}</h2>
        <blockquote className="mt-4 border-l-2 border-[#5b4fe8] pl-3 text-sm leading-relaxed text-[#1a1633]">“{summary.source_excerpt}”</blockquote>
        {summary.source_location && <p className="mt-2 pl-3 text-xs leading-relaxed text-[#8b8ba0]">{summary.source_location}</p>}

        <div className="my-5 h-px bg-[#ededf4]" />
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-xs">
          <dt className="text-[#a3a3b8]">Line</dt><dd>{summary.line ? LINE_LABELS[summary.line] : "Unclassified"}</dd>
          <dt className="text-[#a3a3b8]">Category</dt><dd>{CATEGORY_LABELS[summary.category]}</dd>
          <dt className="text-[#a3a3b8]">Materiality</dt><dd className="capitalize">{summary.change?.materiality ?? "Unclassified"}</dd>
          {summary.tone && <><dt className="text-[#a3a3b8]">Tone</dt><dd className="capitalize">{summary.tone}</dd></>}
          <dt className="text-[#a3a3b8]">Published</dt><dd>{summary.published_at ? formatQatarDate(summary.published_at) : "Undated"}</dd>
          <dt className="text-[#a3a3b8]">Retrieved</dt><dd>{formatQatarDate(summary.retrieved_at)}</dd>
          <dt className="text-[#a3a3b8]">URL</dt><dd className="break-all font-mono text-[10px] leading-relaxed text-[#6c6c85]">{summary.source_url}</dd>
        </dl>

        {!summary.verified && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">The source page could not be independently fetched. This finding rests on the grounded research result.</div>}

        <div className="mt-4">
          <LinkPreviewCard url={summary.source_url} ogTitle={summary.og_title} ogImageUrl={summary.og_image_url} ogSiteName={summary.og_site_name} />
        </div>

        {summary.has_snapshot && (
          <div className="mt-4">
            <button className="text-xs font-semibold text-[#5b4fe8]" onClick={() => setShowSnapshot((value) => !value)}>{showSnapshot ? "Hide captured page" : "View captured page"}</button>
            {showSnapshot && <iframe src={getSnapshotUrl(id)} sandbox="" className="mt-3 h-96 w-full rounded-lg border border-[#e9e9f2]" title="Captured source page" />}
          </div>
        )}

        <Collapsible.Root open={detailOpen} onOpenChange={setDetailOpen} className="mt-5">
          <Collapsible.Trigger className="text-xs font-semibold text-[#5b4fe8]">{detailOpen ? "Hide classification detail" : "Why was it read this way?"}</Collapsible.Trigger>
          <Collapsible.Content className="mt-3 space-y-2 rounded-xl bg-[#f6f5fe] p-4 text-xs leading-relaxed text-[#6c6c85]">
            {!full ? <p>Loading classification detail…</p> : <>
              {full.change && <p>{full.change.rationale}</p>}
              {full.llm_call && <>
                <p className="font-mono text-[10px] text-[#8b8ba0]">{full.llm_call.model} · confidence {full.change?.confidence.toFixed(2)} · {formatQatarDateTime(full.llm_call.called_at)}</p>
                <button className="font-mono text-[10px] font-semibold text-[#5b4fe8] underline" onClick={() => setShowRawLog((value) => !value)}>raw log</button>
                {showRawLog && <pre className="max-h-64 overflow-auto rounded-lg bg-[#1a1633] p-3 text-[10px] text-white">{full.llm_call.raw_output}</pre>}
              </>}
            </>}
          </Collapsible.Content>
        </Collapsible.Root>
      </div>
    </aside>
  );
}
