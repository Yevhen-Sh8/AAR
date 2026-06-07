const DEMO = import.meta.env.VITE_DEMO === "true";
const BASE = DEMO ? `${import.meta.env.BASE_URL}mock` : "/api";

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

  const resp = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) throw new Error(`API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export const IS_DEMO = DEMO;
