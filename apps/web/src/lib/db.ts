import { openDB, type DBSchema, type IDBPDatabase } from "idb";

export type QueuedStatus = "pending" | "syncing" | "synced" | "failed";

export interface QueuedEvent {
  client_event_id: string;
  payload: Record<string, unknown>;
  status: QueuedStatus;
  attempts: number;
  last_error: string | null;
  enqueued_at: number;
  server_id: number | null;
}

interface AARDB extends DBSchema {
  event_queue: {
    key: string;
    value: QueuedEvent;
    indexes: { by_status: QueuedStatus };
  };
}

const DB_NAME = "aar";
const DB_VERSION = 1;

export async function openAARDB(): Promise<IDBPDatabase<AARDB>> {
  return openDB<AARDB>(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains("event_queue")) {
        const store = db.createObjectStore("event_queue", {
          keyPath: "client_event_id",
        });
        store.createIndex("by_status", "status");
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
  };
  await db.put("event_queue", entry);
  return entry;
}

export async function pendingEvents(): Promise<QueuedEvent[]> {
  const db = await openAARDB();
  return db.getAllFromIndex("event_queue", "by_status", "pending");
}

export async function updateEntry(entry: QueuedEvent): Promise<void> {
  const db = await openAARDB();
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
