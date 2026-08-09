import type { Finding } from "@/lib/types";
import { formatRelativeQatarDay } from "@/lib/time";

export function AttentionPanel({ findings, onSelect }: { findings: Finding[]; onSelect: (id: number) => void }) {
  if (findings.length === 0) return null;
  return (
    <section className="mt-3 overflow-hidden rounded-2xl border border-[#e9e9f2] bg-white">
      <div className="flex items-baseline gap-2 px-5 py-3.5">
        <h2 className="text-sm font-semibold">Needs your attention</h2>
        <span className="text-xs text-[#8b8ba0]">{findings.length} highest-materiality finding{findings.length === 1 ? "" : "s"}</span>
      </div>
      {findings.map((finding) => (
        <button key={finding.id} onClick={() => onSelect(finding.id)} className="grid w-full grid-cols-[58px_minmax(0,1fr)_auto] gap-3 border-t border-[#f0f0f6] px-5 py-3 text-left transition hover:bg-[#fafafd]">
          <span className="mt-0.5 rounded-md bg-[#c4433a] py-1 text-center font-mono text-[10px] font-semibold tracking-wider text-white">HIGH</span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold leading-snug">{finding.title}</span>
            <span className="mt-1 line-clamp-1 block text-xs text-[#6c6c85]">{finding.summary}</span>
          </span>
          <span className="text-right text-xs">
            <strong className="block whitespace-nowrap">{finding.company}</strong>
            <span className="mt-1 block text-[#8b8ba0]">{formatRelativeQatarDay(finding.retrieved_at)}</span>
          </span>
        </button>
      ))}
    </section>
  );
}
