import { API_BASE, IS_DEMO } from "./api";
import { clearSession, emitUnauthorized, getToken } from "./auth";

/**
 * Fetch a generated file with the session token and hand it to the browser.
 *
 * A plain `<a href="/api/reports/monthly.xlsx">` cannot carry an Authorization
 * header, so in production — where the global auth gate is on — every export
 * link answered 401 and the operator got a page of JSON instead of a report.
 * The documented workaround was «вивантажуйте через API з токеном», which for
 * an analyst means: use curl. That is not a workaround, it is an unshipped
 * feature.
 *
 * The token stays in a header. Putting it in the query string would be the
 * easy fix and the wrong one: URLs land in browser history, proxy logs and
 * `Referer`, and this token is a full session.
 */
export interface DownloadOutcome {
  ok: boolean;
  /** Ukrainian, ready to show; null when ok. */
  error: string | null;
}

function resolve(path: string): string {
  // Same resolution as apiFetch: in production the frontend may be a static
  // site on another origin, so a literal "/api" would hit the CDN and 404.
  const base = IS_DEMO ? import.meta.env.BASE_URL + "mock" : API_BASE;
  return `${base}${path}`;
}

export async function downloadFile(
  path: string,
  filename: string,
): Promise<DownloadOutcome> {
  let resp: Response;
  try {
    const token = getToken();
    resp = await fetch(resolve(path), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    return { ok: false, error: "Немає зв'язку з сервером." };
  }

  if (resp.status === 401) {
    // Same contract as apiFetch: a dead session bounces to login rather than
    // silently producing an empty file.
    clearSession();
    emitUnauthorized();
    return { ok: false, error: "Сесія завершилась — увійдіть ще раз." };
  }
  if (resp.status === 403) {
    return { ok: false, error: "Немає прав на це вивантаження." };
  }
  if (!resp.ok) {
    return { ok: false, error: `Не вдалося сформувати файл (HTTP ${resp.status}).` };
  }

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return { ok: true, error: null };
}
