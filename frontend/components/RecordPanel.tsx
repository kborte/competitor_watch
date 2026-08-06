"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as Collapsible from "@radix-ui/react-collapsible";
import { getFinding, getSnapshotUrl } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/types";
import { formatQatarDate, formatQatarDateTime } from "@/lib/time";

const MATERIALITY_CLASS: Record<string, string> = {
  high: "bg-rose-100 text-rose-700",
  medium: "bg-slate-100 text-slate-600",
  low: "bg-slate-100 text-slate-500",
};

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

  if (isLoading || !summary) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-400">
        Loading record…
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white">
        <span className="tracking-wide">RECORD</span>
        <a href={summary.source_url} target="_blank" rel="noreferrer" className="hover:underline">
          Open source ↗
        </a>
      </div>

      <div className="p-6">
        <h2 className="text-xl font-bold text-slate-900">{summary.title}</h2>
        <p className="mt-2 text-slate-600">{summary.summary}</p>

        <div className="mt-4 flex gap-2">
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-600">
            {CATEGORY_LABELS[summary.category]}
          </span>
          {summary.change && (
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${MATERIALITY_CLASS[summary.change.materiality]}`}
            >
              {summary.change.materiality[0].toUpperCase() + summary.change.materiality.slice(1)} materiality
            </span>
          )}
        </div>

        <hr className="my-5 border-slate-100" />

        <div className="text-xs font-semibold tracking-wide text-slate-400">SOURCE</div>
        <p className="mt-2 text-sm text-slate-700">{summary.source_url}</p>
        <p className="mt-1 text-xs text-slate-400">
          {summary.published_at && <>Published {formatQatarDate(summary.published_at)}&emsp;</>}
          Retrieved {formatQatarDate(summary.retrieved_at)}
        </p>

        <blockquote className="mt-4 border-l-2 border-indigo-200 pl-3 text-sm italic text-slate-600">
          &ldquo;{summary.source_excerpt}&rdquo;
        </blockquote>

        {summary.has_snapshot && (
          <div className="mt-4">
            <button
              className="text-sm font-semibold text-indigo-600 underline underline-offset-2"
              onClick={() => setShowSnapshot((v) => !v)}
            >
              {showSnapshot ? "Hide captured page" : "View captured page"}
            </button>
            {showSnapshot && (
              <iframe
                src={getSnapshotUrl(id)}
                sandbox=""
                className="mt-3 h-96 w-full rounded-lg border border-slate-200"
                title="Captured source page"
              />
            )}
          </div>
        )}

        <Collapsible.Root open={detailOpen} onOpenChange={setDetailOpen} className="mt-5">
          <Collapsible.Trigger className="text-sm font-semibold text-indigo-600">
            Why was it read this way? {detailOpen ? "▲" : "▼"}
          </Collapsible.Trigger>
          <Collapsible.Content className="mt-3 rounded-lg bg-indigo-50/60 p-4 text-sm text-slate-700">
            {!full ? (
              <p className="text-slate-400">Loading classification detail…</p>
            ) : (
              <>
                {full.change && <p>{full.change.rationale}</p>}
                {full.llm_call && (
                  <>
                    <p className="mt-3 font-mono text-xs text-slate-500">
                      Model {full.llm_call.model} · confidence {full.change?.confidence.toFixed(2)}
                    </p>
                    <p className="font-mono text-xs text-slate-500">
                      Retrieved {formatQatarDateTime(full.llm_call.called_at)}
                    </p>
                    <button
                      className="mt-2 font-mono text-xs font-semibold text-indigo-600 underline underline-offset-2"
                      onClick={() => setShowRawLog((v) => !v)}
                    >
                      raw log
                    </button>
                    {showRawLog && (
                      <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
                        {full.llm_call.raw_output}
                      </pre>
                    )}
                  </>
                )}
              </>
            )}
          </Collapsible.Content>
        </Collapsible.Root>
      </div>
    </div>
  );
}
