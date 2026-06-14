import { clearSession, emitUnauthorized, getToken } from "./auth";

const DEMO = import.meta.env.VITE_DEMO === "true";

// Live API base resolution:
//   - demo build        → static mock JSON under <base>/mock
//   - VITE_API_BASE set  → absolute backend URL (e.g. https://aar-api.onrender.com/api)
//   - otherwise          → same-origin "/api" (nginx proxy / vite dev proxy)
function safeBase(raw: string): string {
  if (!raw) return "/api";
  const trimmed = raw.replace(/\/+$/, "");
  if (trimmed.startsWith("/")) return trimmed; // relative — always valid
  try {
    // Reject a malformed absolute base (e.g. an empty host "https:///api"
    // from a misconfigured build var) so fetch never throws an opaque
    // "string did not match the expected pattern" error.
    const u = new URL(trimmed);
    if (!u.host) return "/api";
    return trimmed;
  } catch {
    return "/api";
  }
}

// Real backend base — used by both apiFetch (reads) and sync.ts (writes).
export const API_BASE = safeBase(import.meta.env.VITE_API_BASE || "/api");
const BASE = DEMO ? `${import.meta.env.BASE_URL}mock` : API_BASE;

const MOCK_ROUTES: Record<string, string> = {
  "/reports/monthly": "/monthly.json",
  "/reports/daily": "/daily.json",
  "/aar/cases": "/cases.json",
  "/events": "/events.json",
  "/dictionaries/operators": "/operators.json",
  "/dictionaries/loss-reasons": "/loss-reasons.json",
  "/dictionaries/repair-reasons": "/repair-reasons.json",
  "/dictionaries/item-types": "/item-types.json",
  "/audit/log": "/audit-log.json",
  "/audit/verify": "/audit-verify.json",
  "/context/assets": "/context-assets.json",
  "/integrations/subscriptions": "/integrations-subscriptions.json",
  "/integrations/deliveries": "/integrations-deliveries.json",
  "/integrations/connectors": "/integrations-connectors.json",
  "/learning/loop-kpi": "/loop-kpi.json",
};

function resolveDemoPath(path: string): string {
  for (const route of Object.keys(MOCK_ROUTES)) {
    if (path.startsWith(route)) return MOCK_ROUTES[route];
  }
  return path;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = DEMO ? `${BASE}${resolveDemoPath(path)}` : `${BASE}${path}`;
  const method = init?.method ?? "GET";

  if (DEMO && method !== "GET") {
    return [] as T; // demo is read-only — POST/PATCH return empty
  }

  const token = DEMO ? null : getToken();
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (resp.status === 401 && !DEMO) {
    // Token missing/expired → drop session and bounce to login.
    clearSession();
    emitUnauthorized();
    throw new Error("401: потрібен вхід");
  }
  if (!resp.ok) throw new Error(`API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export const IS_DEMO = DEMO;
