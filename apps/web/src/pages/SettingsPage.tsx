import { Settings as SettingsIcon, ExternalLink } from "lucide-react";
import { API_BASE, IS_DEMO } from "../lib/api";

const APP_VERSION = "0.4.0";

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
  { key: "ISO/IEC 27001:2022 controls", state: "partial", note: "docs/normative/iso-27001-controls.md" },
  { key: "Dictionary versioning", state: "planned", note: "Roadmap Stage 12" },
  { key: "Geospatial map UI", state: "planned", note: "next minor" },
  { key: "Telegram/Signal reminders", state: "planned", note: "Stage 13" },
];

function stateChip(s: string): string {
  return s === "available"
    ? "chip chip-active"
    : s === "partial"
      ? "chip chip-draft"
      : "chip";
}

export default function SettingsPage() {
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
