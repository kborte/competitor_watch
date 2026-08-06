// Qatar is a fixed UTC+3 offset year-round (no DST) — matches the backend's
// own window-boundary math, so no timezone library is needed here.
const QATAR_OFFSET_MS = 3 * 60 * 60 * 1000;

function toQatar(iso: string): Date {
  return new Date(new Date(iso).getTime() + QATAR_OFFSET_MS);
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatQatarDate(iso: string): string {
  const d = toQatar(iso);
  return `${String(d.getUTCDate()).padStart(2, "0")} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function formatQatarDateTime(iso: string): string {
  const d = toQatar(iso);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${formatQatarDate(iso)}, ${hh}:${mm} AST`;
}

// Relative label using Qatar-local calendar-day difference, consistent with
// the backend's own "today" window definition — not raw elapsed hours.
export function formatRelativeQatarDay(iso: string): string {
  const now = toQatar(new Date().toISOString());
  const then = toQatar(iso);
  const startOfDay = (d: Date) => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const dayDiff = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);

  if (dayDiff <= 0) return "today";
  if (dayDiff === 1) return "yesterday";
  return `${dayDiff} days ago`;
}
