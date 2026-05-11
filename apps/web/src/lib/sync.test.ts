import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { allEvents, clearQueue, pendingEvents } from "./db";
import { flushQueue, submitEvent } from "./sync";

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

describe("offline sync", () => {
  beforeEach(async () => {
    await clearQueue();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("queues events while offline and posts none until back online", async () => {
    setOnline(false);
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    for (let i = 0; i < 10; i++) {
      await submitEvent({
        item_serial_no: `A-${i}`,
        item_type_code: "A",
        operator_code: "E-01",
        event_date: "2025-11-15",
        outcome: "success",
      });
    }

    expect(fetchSpy).not.toHaveBeenCalled();
    const pending = await pendingEvents();
    expect(pending).toHaveLength(10);
  });

  it("flushes 10 queued events without duplicates when network returns", async () => {
    setOnline(false);
    vi.stubGlobal("fetch", vi.fn());
    for (let i = 0; i < 10; i++) {
      await submitEvent({
        item_serial_no: `A-${i}`,
        item_type_code: "A",
        operator_code: "E-01",
        event_date: "2025-11-15",
        outcome: "success",
      });
    }

    setOnline(true);
    const seen = new Set<string>();
    const fetchSpy = mockFetchOnce(seen);
    vi.stubGlobal("fetch", fetchSpy);

    const first = await flushQueue();
    expect(first).toEqual({ attempted: 10, succeeded: 10, failed: 0 });

    // Re-flush: nothing pending, no duplicate POSTs
    const second = await flushQueue();
    expect(second).toEqual({ attempted: 0, succeeded: 0, failed: 0 });

    expect(fetchSpy).toHaveBeenCalledTimes(10);
    const synced = (await allEvents()).filter((e) => e.status === "synced");
    expect(synced).toHaveLength(10);
    expect(new Set(synced.map((e) => e.server_id)).size).toBe(10);
  });
});
