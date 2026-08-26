import { API_BASE, IS_DEMO } from "./api";
import { clearSession, emitUnauthorized, getToken } from "./auth";
import {
  dueEvents,
  enqueueEvent,
  failedEvents,
  requeueEntry,
  updateEntry,
  type QueuedEvent,
} from "./db";

export interface SyncResult {
  attempted: number;
  succeeded: number;
  /** Still undelivered, but will be retried automatically. */
  deferred: number;
  /** Rejected by the server; needs a human. */
  rejected: number;
}

/** Backoff: 5s, 10s, 20s … capped. Never gives up — see `db.ts` on `failed`. */
const BACKOFF_BASE_MS = 5_000;
const BACKOFF_CAP_MS = 5 * 60 * 1000;

export function backoffFor(attempts: number): number {
  const exp = BACKOFF_BASE_MS * 2 ** Math.max(0, attempts - 1);
  return Math.min(exp, BACKOFF_CAP_MS);
}

/**
 * Is this HTTP status worth trying again?
 *
 * 5xx, 408 (timeout), 425 (too early) and 429 (rate limited) are conditions of
 * the moment — a deploy, a proxy hiccup, a login storm. The event is fine.
 * Every other 4xx means the server looked at the payload and refused it
 * (unknown dictionary code, malformed date): retrying identical bytes forever
 * cannot help, and pretending otherwise hides a real data-entry problem.
 */
export function isRetryableStatus(status: number): boolean {
  if (status >= 500) return true;
  return status === 408 || status === 425 || status === 429;
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

async function defer(entry: QueuedEvent, error: string): Promise<void> {
  entry.status = "pending";
  entry.last_error = error;
  entry.next_attempt_at = Date.now() + backoffFor(entry.attempts);
  await updateEntry(entry);
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
  entry.last_attempt_at = Date.now();
  await updateEntry(entry);
  try {
    const token = getToken();
    const resp = await fetch(`${API_BASE}/events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(entry.payload),
    });
    if (resp.status >= 200 && resp.status < 300) {
      const body = (await resp.json()) as { id: number };
      entry.server_id = body.id;
      entry.status = "synced";
      entry.last_error = null;
      entry.next_attempt_at = 0;
      await updateEntry(entry);
      return true;
    }
    if (resp.status === 401) {
      // Session expired — keep the event queued and bounce to login. Retry
      // immediately once there is a token again; this is not the event's fault,
      // so it does not earn a backoff.
      clearSession();
      emitUnauthorized();
      entry.status = "pending";
      entry.last_error = "потрібен вхід";
      entry.next_attempt_at = 0;
      await updateEntry(entry);
      return false;
    }
    if (isRetryableStatus(resp.status)) {
      await defer(entry, `HTTP ${resp.status} — повтор автоматично`);
      return false;
    }
    // A real rejection. Park it where a person will see it, with the server's
    // own words: «HTTP 400» alone tells the operator nothing actionable.
    entry.status = "failed";
    entry.last_error = `HTTP ${resp.status}: ${await readError(resp)}`;
    await updateEntry(entry);
    return false;
  } catch (err) {
    // Network-level failure (offline, DNS, TLS, aborted). Always retryable.
    await defer(entry, err instanceof Error ? err.message : String(err));
    return false;
  }
}

/** Best-effort extraction of the API's error text; never throws. */
async function readError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail !== undefined) return JSON.stringify(body.detail);
    return resp.statusText || "без пояснення";
  } catch {
    return resp.statusText || "без пояснення";
  }
}

export async function flushQueue(): Promise<SyncResult> {
  const due = await dueEvents();
  let succeeded = 0;
  let deferred = 0;
  let rejected = 0;
  for (const entry of due) {
    const ok = await tryPost(entry);
    if (ok) succeeded += 1;
    else if (entry.status === "failed") rejected += 1;
    else deferred += 1;
  }
  return { attempted: due.length, succeeded, deferred, rejected };
}

/** Operator action: push every rejected entry back into the queue. */
export async function retryFailed(): Promise<SyncResult> {
  for (const entry of await failedEvents()) {
    await requeueEntry(entry.client_event_id);
  }
  return flushQueue();
}

/**
 * Retry on reconnect AND on a timer.
 *
 * The `online` event alone was not enough: it never fires when the outage is
 * on the server side (a deploy, a 502) rather than on the radio, so a deferred
 * entry would sit untouched until the operator happened to submit something
 * else. The interval is the thing that actually drains the queue.
 */
const AUTO_SYNC_INTERVAL_MS = 60_000;

export function installAutoSync(): () => void {
  const handler = () => {
    void flushQueue();
  };
  window.addEventListener("online", handler);
  const timer = window.setInterval(() => {
    if (navigator.onLine) void flushQueue();
  }, AUTO_SYNC_INTERVAL_MS);
  return () => {
    window.removeEventListener("online", handler);
    window.clearInterval(timer);
  };
}
