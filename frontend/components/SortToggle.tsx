"use client";

interface SortToggleProps {
  chronological: boolean;
  onToggle: () => void;
  count: number;
}

export function SortToggle({ chronological, onToggle, count }: SortToggleProps) {
  return (
    <div className="flex items-center gap-2 px-1 pb-2 text-sm text-slate-500">
      <span>{chronological ? "Sorted by time" : "Sorted by materiality"} —</span>
      <button className="font-semibold text-indigo-600 underline underline-offset-2" onClick={onToggle}>
        {chronological ? `view by materiality` : `view all ${count} chronologically`}
      </button>
    </div>
  );
}
