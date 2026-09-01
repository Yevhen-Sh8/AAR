/**
 * Export links used to be plain `<a href>`, which cannot carry a bearer token.
 * With the production auth gate on, every «Завантажити XLSX» answered 401 and
 * the analyst was told, in the docs, to fetch it with curl instead.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setSession, clearSession, getToken } from "./auth";
import { downloadFile } from "./download";

let clicked: { href: string; download: string } | null = null;
let revoked: string[] = [];

beforeEach(() => {
  clicked = null;
  revoked = [];
  clearSession();
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:fake"),
    revokeObjectURL: vi.fn((u: string) => revoked.push(u)),
  });
  // Capture the synthetic <a> without letting jsdom navigate.
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked = { href: this.href, download: this.download };
  });
});

afterEach(() => vi.restoreAllMocks());

function serve(status: number, body = "binary") {
  const spy = vi.fn(async () => new Response(body, { status }));
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("authenticated download", () => {
  it("sends the session token in a header, never in the URL", async () => {
    setSession("secret-token-value", "a@b.c");
    const spy = serve(200);

    const res = await downloadFile("/reports/monthly.xlsx?year=2025&month=12", "m.xlsx");
    expect(res.ok).toBe(true);

    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer secret-token-value",
    );
    // A token in the query string would end up in history, proxy logs and Referer.
    expect(url).not.toContain("secret-token-value");
  });

  it("hands the blob to the browser under the requested filename", async () => {
    setSession("t", "a@b.c");
    serve(200);

    await downloadFile("/reports/daily.pdf?date=2025-11-15", "aar-daily-2025-11-15.pdf");

    expect(clicked).not.toBeNull();
    expect(clicked!.download).toBe("aar-daily-2025-11-15.pdf");
    expect(revoked).toEqual(["blob:fake"]);
  });

  it("bounces an expired session to login instead of saving an error page", async () => {
    setSession("stale", "a@b.c");
    serve(401);
    const onUnauthorized = vi.fn();
    window.addEventListener("aar:unauthorized", onUnauthorized);

    const res = await downloadFile("/reports/monthly.xlsx", "m.xlsx");

    expect(res.ok).toBe(false);
    expect(res.error).toContain("Сесія завершилась");
    expect(getToken()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalled();
    // Nothing was written to disk — the old behaviour saved the 401 body as
    // if it were the report.
    expect(clicked).toBeNull();
    window.removeEventListener("aar:unauthorized", onUnauthorized);
  });

  it("explains a permissions refusal", async () => {
    setSession("t", "a@b.c");
    serve(403);
    const res = await downloadFile("/reports/monthly.xlsx", "m.xlsx");
    expect(res.ok).toBe(false);
    expect(res.error).toContain("Немає прав");
    expect(clicked).toBeNull();
  });

  it("reports a server-side failure with its status", async () => {
    setSession("t", "a@b.c");
    serve(500);
    const res = await downloadFile("/reports/monthly.xlsx", "m.xlsx");
    expect(res.ok).toBe(false);
    expect(res.error).toContain("500");
    expect(clicked).toBeNull();
  });

  it("reports a dead connection without throwing", async () => {
    setSession("t", "a@b.c");
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    const res = await downloadFile("/reports/monthly.xlsx", "m.xlsx");
    expect(res.ok).toBe(false);
    expect(res.error).toContain("Немає зв'язку");
  });
});
