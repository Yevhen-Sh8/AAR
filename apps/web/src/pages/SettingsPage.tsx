import { useState } from "react";
import { Settings as SettingsIcon, ExternalLink, DatabaseBackup } from "lucide-react";
import { API_BASE, IS_DEMO } from "../lib/api";
import { getToken } from "../lib/auth";

const APP_VERSION = "1.8.0";

const FEATURES = [
  { key: "Two-level data model", state: "available", note: "Events → AAR Cases" },
  { key: "Daily / monthly reports (η, η_c, λ_c)", state: "available", note: "XLSX + PDF" },
  { key: "AAR triggers T1–T5", state: "available", note: "msr_drop, repeated_reason, item_anomaly, enterprise_drop, manual" },
  { key: "Audit hash-chain (SHA-256)", state: "available", note: "append-only, /audit/verify" },
  { key: "CSV/XLSX bulk import", state: "available", note: "POST /events/import" },
  { key: "Universal integrations", state: "available", note: "generic / ODIN / DELTA / Kropyva / SAP — Оберіг виключено" },
  { key: "Context Accumulation Layer v1.1", state: "available", note: "ADR-007/008/009" },
  { key: "PWA offline-first", state: "available", note: "Workbox + IndexedDB" },
  { key: "Order #440 form exports", state: "available", note: "services/mod440.py" },
  { key: "JWT auth + login rate limiting", state: "available", note: "/auth/login, 20 спроб/5 хв на IP" },
  { key: "Security response headers", state: "available", note: "CSP, X-Frame-Options, HSTS, тощо" },
  { key: "Admin JSON backup export", state: "available", note: "/admin/export, browser-only" },
  { key: "Проактивні сигнали (до завдання)", state: "available", note: "/signals, ескалація в AAR-кейс" },
  { key: "Брифінг місії + ШІ-синтез", state: "available", note: "/briefing/mission(/synthesis)" },
  { key: "Цикл навчання (мета-KPI)", state: "available", note: "/learning/loop-kpi" },
  { key: "Геокарта подій", state: "available", note: "MapPage / GET /events/geojson" },
  { key: "Telegram-сповіщення", state: "available", note: "ConnectorKind.telegram (Bot API)" },
  { key: "CRUD довідників (admin)", state: "available", note: "POST/PATCH/DELETE /dictionaries" },
  { key: "ISO/IEC 27001:2022 controls", state: "partial", note: "docs/normative/iso-27001-controls.md" },
  { key: "Signal-канал сповіщень", state: "planned", note: "за потреби; Telegram уже є" },
  { key: "Шифрування at-rest / PITR backup", state: "planned", note: "платний план Postgres" },
];

function stateChip(s: string): string {
  return s === "available"
    ? "chip chip-active"
    : s === "partial"
      ? "chip chip-draft"
      : "chip";
}

export default function SettingsPage() {
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);

  async function downloadBackup() {
    setBackupBusy(true);
    setBackupError(null);
    try {
      const token = getToken();
      const resp = await fetch(`${API_BASE}/admin/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        setBackupError(`Помилка експорту (${resp.status}). Потрібна роль admin.`);
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `aar-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setBackupError("Не вдалося з'єднатися з сервером.");
    } finally {
      setBackupBusy(false);
    }
  }

  const env = {
    "Build mode": IS_DEMO ? "demo (read-only)" : "live (full API)",
    "API base": IS_DEMO ? `${import.meta.env.BASE_URL}mock` : API_BASE,
    "VITE_API_BASE (build var)": import.meta.env.VITE_API_BASE || "(not set → /api)",
    "App version": APP_VERSION,
    "Base URL": import.meta.env.BASE_URL,
    "Build env": import.meta.env.MODE,
    "User agent": navigator.userAgent.slice(0, 80) + "…",
    "Online": navigator.onLine ? "yes" : "no",
  };

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <SettingsIcon size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Параметри середовища
          </span>
        </div>
        <table className="kv-table">
          <tbody>
            {Object.entries(env).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td className="mono">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!IS_DEMO && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <DatabaseBackup size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
              Резервна копія
            </span>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
            Безкоштовний план Postgres на Render не робить автоматичних бекапів
            і видаляється через 90 днів. Завантаж JSON-знімок усіх робочих
            таблиць прямо в браузер — рекомендовано робити це щотижня під час
            пілоту. Для повноцінних бекапів і point-in-time recovery — платний
            план Postgres (див. <code>docs/DEPLOY.md</code>).
          </p>
          <button onClick={downloadBackup} disabled={backupBusy}>
            <DatabaseBackup size={14} />{" "}
            {backupBusy ? "Формуємо…" : "Завантажити резервну копію (JSON)"}
          </button>
          {backupError && (
            <p style={{ color: "var(--accent-red)", fontSize: 12, marginTop: 8 }}>
              {backupError}
            </p>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <span className="card-title">Реалізовані модулі та функції</span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Модуль</th>
              <th>Стан</th>
              <th>Примітка</th>
            </tr>
          </thead>
          <tbody>
            {FEATURES.map((f) => (
              <tr key={f.key}>
                <td>{f.key}</td>
                <td><span className={stateChip(f.state)}>{f.state}</span></td>
                <td style={{ color: "var(--text-secondary)" }}>{f.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Корисні посилання</span>
        </div>
        <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 8 }}>
          <li>
            <a className="btn-link" href="https://github.com/yevhen-sh8/aar" target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> Репозиторій GitHub
            </a>
          </li>
          <li>
            <a className="btn-link" href="https://yevhen-sh8.github.io/AAR/" target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> Live demo (GitHub Pages)
            </a>
          </li>
          <li>
            <a
              className="btn-link"
              href="https://github.com/yevhen-sh8/aar/blob/main/docs/PROJECT.md"
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={14} /> Проєктна документація (docs/PROJECT.md)
            </a>
          </li>
          <li>
            <a
              className="btn-link"
              href="https://github.com/yevhen-sh8/aar/blob/main/docs/concept/AAR_v2.md"
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={14} /> Концепція AAR v2.0
            </a>
          </li>
        </ul>
      </div>
    </div>
  );
}
