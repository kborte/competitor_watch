/**
 * URL building in the API client.
 *
 * The dashboard and the API share one origin behind the Ingress (dashboard at
 * /, API at /api), which means the base URL is a *path prefix* and may be
 * relative. `new URL(path, base)` cannot express that: it resolves an absolute
 * path against the base's origin and discards the base's own path, so "/api"
 * silently vanished — and a relative base threw outright. These tests pin the
 * concatenation that replaced it.
 *
 * Run with `npm test` (Node's built-in runner; no test framework needed).
 */

import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

type Api = typeof import("./api");

/** Imports the module fresh with a given base URL, since it reads env at load. */
async function withBase(base: string): Promise<Api> {
  process.env.NEXT_PUBLIC_API_BASE_URL = base;
  // Cache-busting query so each base gets its own module instance.
  return (await import(`./api.ts?base=${encodeURIComponent(base)}`)) as Api;
}

describe("getSnapshotUrl", () => {
  it("keeps a relative path prefix", async () => {
    const api = await withBase("/api");
    assert.equal(api.getSnapshotUrl(412), "/api/findings/412/snapshot");
  });

  it("keeps an absolute base's path prefix", async () => {
    const api = await withBase("https://watch.example/api");
    assert.equal(
      api.getSnapshotUrl(412),
      "https://watch.example/api/findings/412/snapshot",
    );
  });

  it("treats a trailing slash the same as none", async () => {
    const withSlash = await withBase("/api/");
    assert.equal(withSlash.getSnapshotUrl(412), "/api/findings/412/snapshot");
  });

  it("works with an internal-DNS base and no prefix", async () => {
    const api = await withBase("http://competitor-watch-backend:8080");
    assert.equal(
      api.getSnapshotUrl(7),
      "http://competitor-watch-backend:8080/findings/7/snapshot",
    );
  });
});

describe("query strings", () => {
  let calls: string[];

  before(() => {
    calls = [];
    globalThis.fetch = (async (input: string) => {
      calls.push(String(input));
      return {
        ok: true,
        json: async () => [],
        text: async () => "",
      } as unknown as Response;
    }) as typeof fetch;
    return undefined;
  });

  it("appends defined params and keeps the prefix", async () => {
    const api = await withBase("/api");
    calls.length = 0;
    await api.listFindings({ window: "week", limit: 2 });
    assert.equal(calls[0], "/api/findings?window=week&limit=2");
  });

  it("omits undefined params rather than sending 'undefined'", async () => {
    const api = await withBase("/api");
    calls.length = 0;
    await api.listFindings({ window: "week", company: undefined });
    assert.equal(calls[0], "/api/findings?window=week");
  });

  it("emits no question mark when there are no params", async () => {
    const api = await withBase("/api");
    calls.length = 0;
    await api.listCompanies();
    assert.equal(calls[0], "/api/companies");
  });

  it("percent-encodes values", async () => {
    const api = await withBase("/api");
    calls.length = 0;
    await api.listFindings({ company: "Doha Insurance" });
    assert.equal(calls[0], "/api/findings?company=Doha+Insurance");
  });
});

describe("the behaviour that made this necessary", () => {
  it("new URL() would have dropped the /api prefix", () => {
    // Documents the trap rather than the fix, so nobody reintroduces it.
    assert.equal(
      new URL("/findings", "https://watch.example/api").toString(),
      "https://watch.example/findings",
    );
  });

  it("new URL() rejects a relative base outright", () => {
    assert.throws(() => new URL("/findings", "/api"), TypeError);
  });
});
