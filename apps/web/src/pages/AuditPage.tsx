import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Shield, RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";

interface AuditEntry {
  id: number;
  action: string;
  actor: string | null;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  entry_hash: string;
  created_at: string;
}

interface ChainStatus {
  ok: boolean;
  checked: number;
  broken_at_id: number | null;
  message: string;
}

const ACTION_FILTERS = [
  { value: "", label: "Усі дії" },
  { value: "event_created", label: "event_created" },
  { value: "case_opened", label: "case_opened" },
  { value: "case_closed", label: "case_closed" },
  { value: "asset_validated", label: "asset_validated" },
  { value: "asset_rejected", label: "asset_rejected" },
  { value: "asset_deprecated", label: "asset_deprecated" },
];

function short(hash: string): string {
  return hash.slice(0, 8) + "…" + hash.slice(-4);
}

export default function AuditPage() {
  const [action, setAction] = useState("");
  const log = useQuery({
    queryKey: ["audit-log", action],
    queryFn: () =>
      apiFetch<AuditEntry[]>(`/audit/log?limit=100${action ? `&action=${action}` : ""}`),
  });

  const verify = useMutation({
    mutationFn: () => apiFetch<ChainStatus>("/audit/verify"),
  });

  const rows = log.data ?? [];

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Shield size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Аудит-журнал
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <select
              className="form-input"
              value={action}
              onChange={(e) => setAction(e.target.value)}
            >
              {ACTION_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
            <button onClick={() => log.refetch()} className="secondary">
              <RefreshCw size={14} /> Оновити
            </button>
            <button onClick={() => verify.mutate()} disabled={verify.isPending || IS_DEMO}>
              {verify.isPending ? "Перевіряємо…" : "Перевірити цілісність ланцюга"}
            </button>
          </div>
        </div>

        {verify.data && (
          <div
            className="signal-item"
            style={{
              borderLeftColor: verify.data.ok ? "var(--accent-green)" : "var(--accent-red)",
              marginBottom: 12,
            }}
          >
            <div className="signal-title">
              {verify.data.ok ? (
                <><CheckCircle2 size={14} style={{ verticalAlign: "-2px" }} /> Ланцюг цілий</>
              ) : (
                <><AlertTriangle size={14} style={{ verticalAlign: "-2px" }} /> Ланцюг ПОШКОДЖЕНО</>
              )}
            </div>
            <div className="signal-meta">
              Перевірено записів: {verify.data.checked}
              {verify.data.broken_at_id !== null && ` · Розрив на id=${verify.data.broken_at_id}`}
              {verify.data.message ? ` · ${verify.data.message}` : ""}
            </div>
          </div>
        )}

        {log.isLoading && <div className="loading">Завантаження…</div>}
        {log.isError && <div className="error-msg">Помилка завантаження аудиту</div>}

        {!log.isLoading && rows.length === 0 && (
          <div className="loading">Жодного запису в аудит-журналі</div>
        )}

        {rows.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Дія</th>
                <th>Сутність</th>
                <th>ID</th>
                <th>Актор</th>
                <th>prev</th>
                <th>hash</th>
                <th>Час</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td>
                  <td><span className="chip">{r.action}</span></td>
                  <td>{r.entity_type}</td>
                  <td className="mono">{r.entity_id}</td>
                  <td>{r.actor ?? "—"}</td>
                  <td className="mono" title={r.prev_hash}>{short(r.prev_hash)}</td>
                  <td className="mono" title={r.entry_hash}>{short(r.entry_hash)}</td>
                  <td>{new Date(r.created_at).toLocaleString("uk")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Про append-only hash-chain</span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6 }}>
          Кожен запис містить SHA-256 від <code>(action, actor, entity_type, entity_id, payload, prev_hash)</code>.
          Перший запис посилається на genesis-хеш (64 нулі). Кнопка «Перевірити цілісність ланцюга»
          обходить усі рядки і повертає id першого розриву, якщо такий є. У demo-режимі ця кнопка вимкнена —
          доступна лише у dev/prod-середовищі.
        </p>
      </div>
    </div>
  );
}
