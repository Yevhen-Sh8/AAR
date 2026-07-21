// Minimal JWT session store (Wave 5). The token lives in localStorage and is
// attached as a Bearer header by api.ts and sync.ts. On any 401 the API layer
// clears it and emits "aar:unauthorized" so the app falls back to the login
// screen.
const TOKEN_KEY = "aar_token";
const EMAIL_KEY = "aar_email";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getEmail(): string | null {
  return localStorage.getItem(EMAIL_KEY);
}

export function setSession(token: string, email: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EMAIL_KEY, email);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}

export function isAuthed(): boolean {
  return !!getToken();
}

export function emitUnauthorized(): void {
  window.dispatchEvent(new Event("aar:unauthorized"));
}
