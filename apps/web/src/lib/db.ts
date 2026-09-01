import { openDB, type DBSchema, type IDBPDatabase } from "idb";

/**
 * Queue states.
 *
 *  pending — not delivered yet; WILL be retried automatically.
 *  syncing — a POST is in flight right now.
 *  synced  — the server has it.
 *  failed  — the server explicitly REJECTED the payload (4xx). No automatic
 *            retry would ever succeed; a human has to look at it.
 *
 * `failed` is the only terminal state, and it is reachable only when the
 * server said "this data is not acceptable". Anything that might succeed
 * later — network down, 5xx, timeout — stays `pending` forever. In a tool
 * that records equipment losses, a queue that keeps trying is strictly
 * better than one that quietly gives up.
 */
export type QueuedStatus = "pending" | "syncing" | "synced" | "failed";

export interface QueuedEvent {
  client_event_id: string;
  payload: Record<string, unknown>;
  status: QueuedStatus;
  attempts: number;
  last_error: string | null;
  enqueued_at: number;
  server_id: number | null;
  /** Earliest ms-epoch at which this entry may be attempted again (backoff). */
  next_attempt_at: number;
  /** When the in-flight attempt started; lets us spot an abandoned `syncing`. */
  last_attempt_at: number | null;
}

interface AARDB extends DBSchema {
  event_queue: {
    key: string;
    value: QueuedEvent;
    indexes: { by_status: QueuedStatus };
  };
}

const DB_NAME = "aar";
/** v2 adds `next_attempt_at` / `last_attempt_at` for backoff and stall recovery. */
const DB_VERSION = 2;

export async function openAARDB(): Promise<IDBPDatabase<AARDB>> {
  return openDB<AARDB>(DB_NAME, DB_VERSION, {
    async upgrade(db, oldVersion, _newVersion, tx) {
      if (!db.objectStoreNames.contains("event_queue")) {
        const store = db.createObjectStore("event_queue", {
          keyPath: "client_event_id",
        });
        store.createIndex("by_status", "status");
      }
      if (oldVersion < 2) {
        // Backfill the new fields on rows written by v1, and rescue anything
        // v1 had already parked in a dead state: `failed` was terminal there
        // even for a plain 502, and `syncing` was never revisited at all.
        // Those rows are real events someone submitted — requeue them.
        const store = tx.objectStore("event_queue");
        for (const row of await store.getAll()) {
          const legacy = row as Partial<QueuedEvent> & { status: QueuedStatus };
          if (legacy.next_attempt_at === undefined) legacy.next_attempt_at = 0;
          if (legacy.last_attempt_at === undefined) legacy.last_attempt_at = null;
          if (legacy.status === "failed" || legacy.status === "syncing") {
            legacy.status = "pending";
            legacy.next_attempt_at = 0;
          }
          await store.put(legacy as QueuedEvent);
        }
      }
    },
  });
}

export async function enqueueEvent(
  payload: Record<string, unknown>,
): Promise<QueuedEvent> {
  const db = await openAARDB();
  const id =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `c-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const entry: QueuedEvent = {
    client_event_id: id,
    payload: { ...payload, client_event_id: id },
    status: "pending",
    attempts: 0,
    last_error: null,
    enqueued_at: Date.now(),
    server_id: null,
    next_attempt_at: 0,
    last_attempt_at: null,
  };
  await db.put("event_queue", entry);
  return entry;
}

export async function pendingEvents(): Promise<QueuedEvent[]> {
  const db = await openAARDB();
  return db.getAllFromIndex("event_queue", "by_status", "pending");
}

export async function failedEvents(): Promise<QueuedEvent[]> {
  const db = await openAARDB();
  return db.getAllFromIndex("event_queue", "by_status", "failed");
}

/**
 * How long a `syncing` entry may sit before we assume the attempt died with
 * the tab. The POST is idempotent server-side (`client_event_id` is unique),
 * so re-sending a request that actually did land is harmless — losing one
 * that did not is the failure we care about.
 */
export const STALE_SYNCING_MS = 2 * 60 * 1000;

/**
 * Entries eligible for a delivery attempt right now: everything `pending`
 * whose backoff has elapsed, plus `syncing` rows abandoned by a closed tab.
 */
export async function dueEvents(now: number = Date.now()): Promise<QueuedEvent[]> {
  const db = await openAARDB();
  const all = await db.getAll("event_queue");
  return all.filter((e) => {
    if (e.status === "pending") return e.next_attempt_at <= now;
    if (e.status === "syncing") {
      return (e.last_attempt_at ?? 0) + STALE_SYNCING_MS <= now;
    }
    return false;
  });
}

export async function updateEntry(entry: QueuedEvent): Promise<void> {
  const db = await openAARDB();
  await db.put("event_queue", entry);
}

/** Put a rejected entry back in line — the operator fixed the cause, or wants to try anyway. */
export async function requeueEntry(clientEventId: string): Promise<void> {
  const db = await openAARDB();
  const entry = await db.get("event_queue", clientEventId);
  if (!entry || entry.status === "synced") return;
  entry.status = "pending";
  entry.next_attempt_at = 0;
  entry.last_error = null;
  await db.put("event_queue", entry);
}

export async function allEvents(): Promise<QueuedEvent[]> {
  const db = await openAARDB();
  return db.getAll("event_queue");
}

export async function clearQueue(): Promise<void> {
  const db = await openAARDB();
  await db.clear("event_queue");
}
