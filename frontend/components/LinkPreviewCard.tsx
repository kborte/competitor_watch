interface LinkPreviewCardProps {
  url: string;
  ogTitle: string | null;
  ogImageUrl: string | null;
  ogSiteName: string | null;
}

// Messenger-style link-preview card, rendered from Open Graph metadata
// captured at crawl time (see research_crawler/fetch.py) — not a live
// unfurl, so it reflects the page as it looked when observed, consistent
// with source_html's own "auditable snapshot" philosophy. Falls back to a
// plain domain+title row when a source has no OG tags (PDFs, plain-text
// pages, or anything the crawler couldn't capture cleanly).
export function LinkPreviewCard({ url, ogTitle, ogImageUrl, ogSiteName }: LinkPreviewCardProps) {
  let domain = url;
  try {
    domain = new URL(url).hostname.replace(/^www\./, "");
  } catch {
    // leave as-is if it's not a parseable URL
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex overflow-hidden rounded-lg border border-slate-200 bg-white transition-colors hover:border-slate-300"
    >
      {ogImageUrl && (
        <span className="relative hidden h-20 w-28 shrink-0 bg-slate-100 sm:block">
          {/* eslint-disable-next-line @next/next/no-img-element -- arbitrary,
              ever-changing external source domains: not practical to
              allowlist every one via next/image's remotePatterns config */}
          <img src={ogImageUrl} alt="" className="h-full w-full object-cover" />
        </span>
      )}
      <span className="flex min-w-0 flex-col justify-center gap-0.5 px-3 py-2">
        <span className="truncate text-xs font-medium uppercase tracking-wide text-slate-400">
          {ogSiteName || domain}
        </span>
        <span className="truncate text-sm font-medium text-slate-700">{ogTitle || domain}</span>
      </span>
    </a>
  );
}
