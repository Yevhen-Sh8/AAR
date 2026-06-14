import { API_BASE, IS_DEMO } from "./api";
import { enqueueEvent, pendingEvents, updateEntry, type QueuedEvent } from "./db";

export interface SyncResult {
  attempted: number;
  succeeded: number;
  failed: number;
}

export async function submitEvent(
  payload: Record<string, unknown>,
): Promise<{ queued: QueuedEvent; sent: boolean }> {
  const queued = await enqueueEvent(payload);
  if (!navigator.onLine) {
    return { queued, sent: false };
  }
  const ok = await tryPost(queued);
  return { queued, sent: ok };
}

async function tryPost(entry: QueuedEvent): Promise<boolean> {
  // Demo build has no real backend — keep the entry queued with a clear note
  // instead of POSTing to a static host (which would 404 / return HTML).
  if (IS_DEMO) {
    entry.status = "pending";
    entry.last_error = "demo-режим — подія не зберігається на сервері";
    await updateEntry(entry);
    return false;
  }
  entry.status = "syncing";
  entry.attempts += 1;
  await updateEntry(entry);
  try {
    const resp = await fetch(`${API_BASE}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry.payload),
    });
    if (resp.status >= 200 && resp.status < 300) {
      const body = (await resp.json()) as { id: number };
      entry.server_id = body.id;
      entry.status = "synced";
      entry.last_error = null;
      await updateEntry(entry);
      return true;
    }
    entry.status = "failed";
    entry.last_error = `HTTP ${resp.status}`;
    await updateEntry(entry);
    return false;
  } catch (err) {
    entry.status = "pending";
    entry.last_error = err instanceof Error ? err.message : String(err);
    await updateEntry(entry);
    return false;
  }
}

export async function flushQueue(): Promise<SyncResult> {
  const pending = await pendingEvents();
  let succeeded = 0;
  let failed = 0;
  for (const entry of pending) {
    const ok = await tryPost(entry);
    if (ok) succeeded += 1;
    else failed += 1;
  }
  return { attempted: pending.length, succeeded, failed };
}

export function installAutoSync(): () => void {
  const handler = () => {
    void flushQueue();
  };
  window.addEventListener("online", handler);
  return () => window.removeEventListener("online", handler);
}
