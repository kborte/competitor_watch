// Matches backend/companies.py's canonical names exactly — logos fetched
// from each company's own official site (or Wikimedia Commons), preferring
// transparent/white-background versions. Two exceptions, both flagged
// during sourcing: Bupa Arabia's official asset is a solid colored square
// (renders fine as a colored icon, just isn't transparent), and QGIRCO's
// only usable asset was its icon mark rather than a full wordmark (the
// wordmark version was white-on-transparent, invisible on a light chip).
export const COMPANY_LOGOS: Record<string, string> = {
  "Bupa Arabia": "/logos/bupa-arabia.jpg",
  "Tawuniya": "/logos/tawuniya.svg",
  "ADNIC": "/logos/adnic.png",
  "Sukoon Insurance": "/logos/sukoon.svg",
  "Alkhaleej Takaful": "/logos/alkhaleej-takaful.png",
  "Beema": "/logos/beema.svg",
  "Doha Insurance": "/logos/doha-insurance.png",
  "QIIC": "/logos/qiic.png",
  "Qatar Insurance Company": "/logos/qic.png",
  "Qatar General Insurance & Reinsurance": "/logos/qgirco.jpg",
};

export function logoForCompany(company: string): string | null {
  return COMPANY_LOGOS[company] ?? null;
}

// Fallback avatar for anything without a logo asset (e.g. "Qatar Insurance
// Market" — not a real tracked company, just the market-wide keyword — or
// any future company added before its logo is sourced).
export function initialsForCompany(company: string): string {
  const words = company.split(/\s+/).filter(Boolean);
  const initials = words.slice(0, 2).map((w) => w[0]).join("");
  return initials.toUpperCase() || "?";
}
