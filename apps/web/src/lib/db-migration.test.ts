/**
 * v1 → v2 upgrade.
 *
 * Runs in its own file so it gets a clean fake-indexeddb: the upgrade needs no
 * other connection holding the database open at the old version.
 *
 * The point is not the two new columns. It is that v1 left real events parked
 * in states nothing ever read again — `failed` (any 5xx got them there) and
 * `syncing` (a tab closed mid-POST). Those rows are in operators' browsers
 * right now, and the upgrade has to hand them back to the queue rather than
 * carry the loss forward.
 */
import "fake-indexeddb/auto";
import { describe, expect, it } from "vitest";
import { allEvents, dueEvents, openAARDB } from "./db";

/** Build the v1 schema by hand, without going through our own module. */
function seedV1(rows: Record<string, unknown>[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("aar", 1);
    req.onupgradeneeded = () => {
      const store = req.result.createObjectStore("event_queue", {
        keyPath: "client_event_id",
      });
      store.createIndex("by_status", "status");
    };
    req.onsuccess = () => {
      const db = req.result;
      const tx = db.transaction("event_queue", "readwrite");
      for (const row of rows) tx.objectStore("event_queue").put(row);
      tx.oncomplete = () => {
        db.close(); // release it so the version change is not blocked
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    };
    req.onerror = () => reject(req.error);
  });
}

const v1Row = (id: string, status: string) => ({
  client_event_id: id,
  payload: { client_event_id: id, item_serial_no: id, outcome: "lost" },
  status,
  attempts: 3,
  last_error: "HTTP 502",
  enqueued_at: 1_700_000_000_000,
  server_id: null,
});

describe("upgrading a queue written by v1", () => {
  it("rescues rows v1 had abandoned and backfills the new fields", async () => {
    await seedV1([
      v1Row("dead-on-502", "failed"),
      v1Row("tab-was-closed", "syncing"),
      v1Row("still-waiting", "pending"),
      v1Row("already-delivered", "synced"),
    ]);

    await openAARDB();

    const byId = new Map((await allEvents()).map((e) => [e.client_event_id, e]));
    expect(byId.size).toBe(4);

    // The two dead states are back in the queue…
    expect(byId.get("dead-on-502")!.status).toBe("pending");
    expect(byId.get("tab-was-closed")!.status).toBe("pending");
    // …untouched otherwise: this is the operator's data, not ours to rewrite.
    expect(byId.get("dead-on-502")!.payload).toMatchObject({ outcome: "lost" });
    expect(byId.get("dead-on-502")!.attempts).toBe(3);

    // Unaffected states stay put — a delivered event must not be re-sent.
    expect(byId.get("still-waiting")!.status).toBe("pending");
    expect(byId.get("already-delivered")!.status).toBe("synced");

    // New fields exist on every row, so `dueEvents` can reason about them.
    for (const e of byId.values()) {
      expect(typeof e.next_attempt_at).toBe("number");
      expect(e.last_attempt_at === null || typeof e.last_attempt_at === "number").toBe(true);
    }

    // All three undelivered rows are due immediately after the upgrade.
    const due = (await dueEvents()).map((e) => e.client_event_id).sort();
    expect(due).toEqual(["dead-on-502", "still-waiting", "tab-was-closed"]);
  });
});
