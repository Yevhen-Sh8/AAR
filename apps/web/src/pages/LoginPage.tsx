import { useState } from "react";
import { LogIn } from "lucide-react";
import { API_BASE } from "../lib/api";
import { setSession } from "../lib/auth";

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail ?? `Помилка входу (${resp.status})`);
        return;
      }
      const data = (await resp.json()) as { access_token: string };
      setSession(data.access_token, email.trim());
      onLogin();
    } catch {
      setError("Не вдалося з'єднатися з сервером. Спробуйте ще раз.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo">AAR</div>
        <p className="login-sub">After Action Review — вхід у систему</p>

        <label className="login-field">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@aar.local"
            autoComplete="username"
            required
          />
        </label>
        <label className="login-field">
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button type="submit" disabled={busy} className="login-btn">
          <LogIn size={16} /> {busy ? "Вхід…" : "Увійти"}
        </button>

        <p className="login-hint">
          Типовий доступ: <code>admin@aar.local</code> · пароль задається
          змінною <code>AAR_ADMIN_PASSWORD</code> в Render (за замовчуванням —{" "}
          <code>aar-admin-2026</code>, якщо не змінено).
        </p>
      </form>
    </div>
  );
}
