import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Library, CheckCircle2, XCircle, Archive } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";

interface ContextAsset {
  id: number;
  type: string;
  title: string;
  description: string;
  status: string;
  source: string;
  source_agent: string;
  reusable_for: string[];
  confidence: number | null;
  owner_role: string | null;
  created_at: string;
  validated_at: string | null;
  superseded_by: number | null;
}

const TYPE_FILTERS = [
  { value: "", label: "Усі типи" },
  { value: "fact", label: "fact" },
  { value: "pattern", label: "pattern" },
  { value: "recommendation", label: "recommendation" },
  { value: "classifier", label: "classifier" },
  { value: "narrative", label: "narrative" },
];

const STATUS_FILTERS = [
  { value: "", label: "Усі статуси" },
  { value: "draft", label: "draft" },
  { value: "validated", label: "validated" },
  { value: "rejected", label: "rejected" },
  { value: "deprecated", label: "deprecated" },
];

function statusChip(s: string): string {
  const map: Record<string, string> = {
    draft: "chip chip-draft",
    validated: "chip chip-active",
    rejected: "chip chip-error",
    deprecated: "chip",
  };
  return map[s] ?? "chip";
}

export default function ContextPage() {
  const qc = useQueryClient();
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<ContextAsset | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const assets = useQuery({
    queryKey: ["context-assets", type, status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (type) params.set("type", type);
      if (status) params.set("status", status);
      params.set("limit", "100");
      return apiFetch<ContextAsset[]>(`/context/assets?${params}`);
    },
  });

  const validate = useMutation({
    mutationFn: (id: number) =>
      apiFetch<ContextAsset>(`/context/assets/${id}/validate`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["context-assets"] }),
  });

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      apiFetch<ContextAsset>(`/context/assets/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["context-assets"] });
      setRejectReason("");
    },
  });

  const deprecate = useMutation({
    mutationFn: ({ id, supersededBy }: { id: number; supersededBy: number | null }) =>
      apiFetch<ContextAsset>(`/context/assets/${id}/deprecate`, {
        method: "POST",
        body: JSON.stringify({ superseded_by: supersededBy }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["context-assets"] }),
  });

  const rows = assets.data ?? [];

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Library size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Контекст-активи (Context Accumulation Layer v1.1)
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <select className="form-input" value={type} onChange={(e) => setType(e.target.value)}>
              {TYPE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
            <select className="form-input" value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="context-split">
          <div className="context-list">
            {assets.isLoading && <div className="loading">Завантаження…</div>}
            {rows.length === 0 && !assets.isLoading && (
              <div className="loading">Жодного активу за фільтрами</div>
            )}
            {rows.map((a) => (
              <div
                key={a.id}
                className={
                  selected?.id === a.id ? "asset-card asset-selected" : "asset-card"
                }
                onClick={() => setSelected(a)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="chip">{a.type}</span>
                  <span className={statusChip(a.status)}>{a.status}</span>
                </div>
                <div className="asset-title">{a.title}</div>
                <div className="asset-meta">
                  {a.source_agent} · {new Date(a.created_at).toLocaleDateString("uk")}
                  {a.confidence !== null && ` · conf=${a.confidence.toFixed(2)}`}
                </div>
              </div>
            ))}
          </div>

          <div className="context-detail">
            {!selected && <div className="loading">Оберіть актив зліва</div>}
            {selected && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                  <span className="chip">{selected.type}</span>
                  <span className={statusChip(selected.status)}>{selected.status}</span>
                </div>
                <h3 style={{ marginBottom: 8, fontSize: 16 }}>{selected.title}</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}>
                  {selected.description || "—"}
                </p>

                <table className="kv-table">
                  <tbody>
                    <tr><td>Джерело</td><td className="mono">{selected.source}</td></tr>
                    <tr><td>Агент</td><td>{selected.source_agent}</td></tr>
                    <tr>
                      <td>Багатократне використання</td>
                      <td>{selected.reusable_for.join(", ") || "—"}</td>
                    </tr>
                    <tr><td>Конфіденс</td><td>{selected.confidence?.toFixed(2) ?? "—"}</td></tr>
                    <tr><td>Власник (роль)</td><td>{selected.owner_role ?? "—"}</td></tr>
                    <tr><td>Створено</td><td>{new Date(selected.created_at).toLocaleString("uk")}</td></tr>
                    <tr>
                      <td>Валідовано</td>
                      <td>
                        {selected.validated_at
                          ? new Date(selected.validated_at).toLocaleString("uk")
                          : "—"}
                      </td>
                    </tr>
                    {selected.superseded_by && (
                      <tr>
                        <td>Замінений на</td>
                        <td className="mono">#{selected.superseded_by}</td>
                      </tr>
                    )}
                  </tbody>
                </table>

                <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
                  {selected.status === "draft" && (
                    <>
                      <button
                        onClick={() => validate.mutate(selected.id)}
                        disabled={validate.isPending || IS_DEMO}
                      >
                        <CheckCircle2 size={14} /> Валідувати
                      </button>
                      <div style={{ display: "flex", gap: 4 }}>
                        <input
                          className="form-input"
                          placeholder="Причина відхилення"
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                        />
                        <button
                          className="secondary"
                          style={{ color: "var(--accent-red)" }}
                          disabled={reject.isPending || IS_DEMO || !rejectReason}
                          onClick={() =>
                            reject.mutate({ id: selected.id, reason: rejectReason })
                          }
                        >
                          <XCircle size={14} /> Відхилити
                        </button>
                      </div>
                    </>
                  )}
                  {selected.status === "rejected" && (
                    <button
                      onClick={() => validate.mutate(selected.id)}
                      disabled={validate.isPending || IS_DEMO}
                    >
                      <CheckCircle2 size={14} /> Повторно валідувати
                    </button>
                  )}
                  {selected.status === "validated" && (
                    <button
                      className="secondary"
                      onClick={() =>
                        deprecate.mutate({ id: selected.id, supersededBy: null })
                      }
                      disabled={deprecate.isPending || IS_DEMO}
                    >
                      <Archive size={14} /> Перевести в deprecated
                    </button>
                  )}
                </div>

                {IS_DEMO && (
                  <p style={{ color: "var(--accent-gold)", fontSize: 12, marginTop: 12 }}>
                    ⓘ У demo-режимі дії не зберігаються — це лише перегляд.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Про CAL v1.1 (ADR-007/008/009)</span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6 }}>
          Кожна функція LLM повертає <code>(task_output, context_assets[])</code>. Активи
          стартують як <b>draft</b> і потребують ручної валідації менеджером або аналітиком
          (ADR-008 — ніколи не авто-валідується). Пошук аналогій працює тільки по
          <b> validated </b>-активах (ADR-009).
        </p>
      </div>
    </div>
  );
}
