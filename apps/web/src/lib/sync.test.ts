import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  allEvents,
  clearQueue,
  dueEvents,
  failedEvents,
  pendingEvents,
  updateEntry,
  STALE_SYNCING_MS,
} from "./db";
import { backoffFor, flushQueue, isRetryableStatus, retryFailed, submitEvent } from "./sync";

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", {
    value,
    configurable: true,
  });
}

function mockFetchOnce(seenIds: Set<string>) {
  return vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as { client_event_id: string };
    const isDup = seenIds.has(body.client_event_id);
    seenIds.add(body.client_event_id);
    return new Response(
      JSON.stringify({ id: 1000 + seenIds.size, client_event_id: body.client_event_id }),
      { status: isDup ? 200 : 201, headers: { "Content-Type": "application/json" } },
    );
  });
}

function respond(status: number, body: unknown = { detail: "щось не так" }) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const SAMPLE = {
  item_serial_no: "A-1",
  item_type_code: "A",
  operator_code: "E-01",
  event_date: "2025-11-15",
  outcome: "success",
};

describe("offline sync", () => {
  beforeEach(async () => {
    await clearQueue();
    setOnline(true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("queues events while offline and posts none until back online", async () => {
    setOnline(false);
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    for (let i = 0; i < 10; i++) {
      await submitEvent({ ...SAMPLE, item_serial_no: `A-${i}` });
    }

    expect(fetchSpy).not.toHaveBeenCalled();
    const pending = await pendingEvents();
    expect(pending).toHaveLength(10);
  });

  it("flushes 10 queued events without duplicates when network returns", async () => {
    setOnline(false);
    vi.stubGlobal("fetch", vi.fn());
    for (let i = 0; i < 10; i++) {
      await submitEvent({ ...SAMPLE, item_serial_no: `A-${i}` });
    }

    setOnline(true);
    const seen = new Set<string>();
    const fetchSpy = mockFetchOnce(seen);
    vi.stubGlobal("fetch", fetchSpy);

    const first = await flushQueue();
    expect(first).toEqual({ attempted: 10, succeeded: 10, deferred: 0, rejected: 0 });

    // Re-flush: nothing due, no duplicate POSTs
    const second = await flushQueue();
    expect(second).toEqual({ attempted: 0, succeeded: 0, deferred: 0, rejected: 0 });

    expect(fetchSpy).toHaveBeenCalledTimes(10);
    const synced = (await allEvents()).filter((e) => e.status === "synced");
    expect(synced).toHaveLength(10);
    expect(new Set(synced.map((e) => e.server_id)).size).toBe(10);
  });
});

describe("a server-side outage must not eat the event", () => {
  beforeEach(async () => {
    await clearQueue();
    setOnline(true);
  });
  afterEach(() => vi.restoreAllMocks());

  it("keeps a 502 retryable instead of burying it in `failed`", async () => {
    // This is the regression. A 502 from a proxy used to set status=failed,
    // and flushQueue only ever read `pending` — so the event was gone for good
    // while the operator's screen said it had been submitted.
    vi.stubGlobal("fetch", respond(502));
    await submitEvent(SAMPLE);

    const [entry] = await allEvents();
    expect(entry.status).toBe("pending");
    expect(await failedEvents()).toHaveLength(0);

    // …and it comes back once the backoff elapses and the server recovers.
    entry.next_attempt_at = 0;
    await updateEntry(entry);
    vi.stubGlobal("fetch", mockFetchOnce(new Set()));
    const res = await flushQueue();
    expect(res.succeeded).toBe(1);
  });

  it.each([500, 503, 504, 408, 429])("treats HTTP %i as retryable", async (status) => {
    vi.stubGlobal("fetch", respond(status));
    await submitEvent(SAMPLE);
    const [entry] = await allEvents();
    expect(entry.status).toBe("pending");
  });

  it("backs off so a flapping link cannot hammer the API", async () => {
    vi.stubGlobal("fetch", respond(503));
    const before = Date.now();
    await submitEvent(SAMPLE);
    const [entry] = await allEvents();
    expect(entry.next_attempt_at).toBeGreaterThan(before);

    // Not due yet → flushQueue leaves it alone.
    expect(await dueEvents()).toHaveLength(0);
    expect(await flushQueue()).toEqual({
      attempted: 0, succeeded: 0, deferred: 0, rejected: 0,
    });
  });

  it("grows the delay with each attempt and caps it", () => {
    expect(backoffFor(1)).toBe(5_000);
    expect(backoffFor(2)).toBe(10_000);
    expect(backoffFor(3)).toBe(20_000);
    expect(backoffFor(99)).toBe(5 * 60 * 1000);
  });

  it("retries a network-level failure rather than dropping it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    await submitEvent(SAMPLE);
    const [entry] = await allEvents();
    expect(entry.status).toBe("pending");
    expect(entry.last_error).toContain("Failed to fetch");
  });
});

describe("a rejected payload is a human problem, and is shown as one", () => {
  beforeEach(async () => {
    await clearQueue();
    setOnline(true);
  });
  afterEach(() => vi.restoreAllMocks());

  it("marks a 400 failed and keeps the server's explanation", async () => {
    vi.stubGlobal("fetch", respond(400, { detail: "невідомий код причини: zz" }));
    await submitEvent(SAMPLE);

    const [entry] = await allEvents();
    expect(entry.status).toBe("failed");
    expect(entry.last_error).toContain("невідомий код причини: zz");
    // Never retried on its own — identical bytes would be refused again.
    expect(await dueEvents()).toHaveLength(0);
  });

  it("counts rejections separately from deferrals", async () => {
    vi.stubGlobal("fetch", respond(422));
    await submitEvent(SAMPLE);
    vi.stubGlobal("fetch", respond(503));
    await submitEvent({ ...SAMPLE, item_serial_no: "A-2" });

    const entries = await allEvents();
    expect(entries.filter((e) => e.status === "failed")).toHaveLength(1);
    expect(entries.filter((e) => e.status === "pending")).toHaveLength(1);
  });

  it("lets the operator put a rejected event back in the queue", async () => {
    vi.stubGlobal("fetch", respond(400));
    await submitEvent(SAMPLE);
    expect(await failedEvents()).toHaveLength(1);

    vi.stubGlobal("fetch", mockFetchOnce(new Set()));
    const res = await retryFailed();
    expect(res.succeeded).toBe(1);
    expect(await failedEvents()).toHaveLength(0);
  });

  it("classifies statuses the way the queue depends on", () => {
    expect(isRetryableStatus(500)).toBe(true);
    expect(isRetryableStatus(502)).toBe(true);
    expect(isRetryableStatus(429)).toBe(true);
    expect(isRetryableStatus(400)).toBe(false);
    expect(isRetryableStatus(422)).toBe(false);
    expect(isRetryableStatus(404)).toBe(false);
  });
});

describe("an attempt abandoned by a closed tab", () => {
  beforeEach(async () => {
    await clearQueue();
    setOnline(true);
  });
  afterEach(() => vi.restoreAllMocks());

  it("is picked back up instead of sitting in `syncing` forever", async () => {
    // tryPost writes status=syncing BEFORE awaiting fetch. If the tab dies
    // there, the row used to be unreachable: flushQueue read only `pending`.
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("tab closed");
    }));
    await submitEvent(SAMPLE);

    const [entry] = await allEvents();
    entry.status = "syncing";
    entry.last_attempt_at = Date.now() - STALE_SYNCING_MS - 1;
    await updateEntry(entry);

    expect(await dueEvents()).toHaveLength(1);

    vi.stubGlobal("fetch", mockFetchOnce(new Set()));
    const res = await flushQueue();
    expect(res.succeeded).toBe(1);
  });

  it("leaves a genuinely in-flight attempt alone", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("x");
    }));
    await submitEvent(SAMPLE);
    const [entry] = await allEvents();
    entry.status = "syncing";
    entry.last_attempt_at = Date.now();
    await updateEntry(entry);

    expect(await dueEvents()).toHaveLength(0);
  });
});
