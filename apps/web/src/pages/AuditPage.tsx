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

// Values MUST match AuditAction in apps/api/aar_api/models/audit.py — the
// router types the query param as the enum, so anything else is a 422. The
// members are dotted ("case.created"), never underscored.
export const ACTION_GROUPS: { group: string; items: { value: string; label: string }[] }[] = [
  {
    group: "Події",
    items: [
      { value: "event.created", label: "подія створена" },
      { value: "event.inbound", label: "подія з інтеграції" },
    ],
  },
  {
    group: "Кейси",
    items: [
      { value: "case.created", label: "кейс відкрито" },
      { value: "case.transitioned", label: "перехід стадії" },
      { value: "case.analysis_drafted", label: "чернетка аналізу" },
      { value: "case.closed", label: "кейс закрито" },
    ],
  },
  {
    group: "Рекомендації",
    items: [
      { value: "recommendation.updated", label: "оновлено" },
      { value: "recommendation.auto_validated", label: "автовалідовано" },
      { value: "recommendation.regressed", label: "регресія" },
    ],
  },
  {
    group: "Контекст-активи",
    items: [
      { value: "context_asset.created", label: "створено" },
      { value: "context_asset.validated", label: "валідовано" },
      { value: "context_asset.rejected", label: "відхилено" },
      { value: "context_asset.deprecated", label: "деприковано" },
    ],
  },
  {
    group: "Сигнали",
    items: [
      { value: "signal.created", label: "подано" },
      { value: "signal.reviewed", label: "розглянуто" },
      { value: "signal.converted", label: "ескальовано в кейс" },
    ],
  },
  {
    group: "Індивідуальні звіти",
    items: [
      { value: "individual_report.requested", label: "запит надіслано" },
      { value: "individual_report.submitted", label: "звіт подано" },
    ],
  },
  {
    group: "Люди",
    items: [
      { value: "person.created", label: "створено" },
      { value: "person.updated", label: "оновлено" },
      { value: "person.deleted", label: "видалено" },
      { value: "person.password_set", label: "встановлено пароль" },
    ],
  },
  {
    group: "Довідники",
    items: [
      { value: "dictionary.created", label: "створено" },
      { value: "dictionary.updated", label: "оновлено" },
      { value: "dictionary.deleted", label: "видалено" },
    ],
  },
  {
    group: "Система",
    items: [
      { value: "subscription.created", label: "підписку створено" },
      { value: "subscription.deleted", label: "підписку видалено" },
      { value: "triggers.run", label: "прогін тригерів" },
    ],
  },
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
              <option value="">Усі дії</option>
              {ACTION_GROUPS.map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.items.map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </optgroup>
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
