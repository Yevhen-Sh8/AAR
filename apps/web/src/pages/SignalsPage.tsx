import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  FolderPlus,
  Megaphone,
  Send,
  XCircle,
} from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";

interface Signal {
  id: number;
  kind: "warning" | "risk" | "proposal" | "info";
  title: string;
  description: string | null;
  author: string | null;
  task_context: string | null;
  status: "new" | "acknowledged" | "accepted" | "dismissed" | "converted";
  review_note: string | null;
  case_id: number | null;
  created_at: string;
  reviewed_at: string | null;
}

const KIND_LABELS: Record<Signal["kind"], string> = {
  warning: "Попередження",
  risk: "Ризик",
  proposal: "Пропозиція",
  info: "Інформація",
};

const STATUS_LABELS: Record<Signal["status"], string> = {
  new: "нове",
  acknowledged: "розглядається",
  accepted: "прийнято",
  dismissed: "відхилено",
  converted: "→ AAR-кейс",
};

function statusChip(s: Signal["status"]): string {
  switch (s) {
    case "accepted":
      return "chip chip-active";
    case "dismissed":
      return "chip chip-error";
    case "converted":
      return "chip chip-mid";
    case "acknowledged":
      return "chip chip-draft";
    default:
      return "chip";
  }
}

function kindChip(k: Signal["kind"]): string {
  switch (k) {
    case "warning":
      return "chip chip-low";
    case "risk":
      return "chip chip-error";
    case "proposal":
      return "chip chip-active";
    default:
      return "chip";
  }
}

const EMPTY_FORM = {
  kind: "warning" as Signal["kind"],
  title: "",
  description: "",
  author: "",
  task_context: "",
};

export default function SignalsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [statusFilter, setStatusFilter] = useState("");

  const signals = useQuery({
    queryKey: ["signals", statusFilter],
    queryFn: () =>
      apiFetch<Signal[]>(
        `/signals${statusFilter ? `?status=${statusFilter}` : ""}`,
      ),
  });

  const create = useMutation({
    mutationFn: (body: typeof EMPTY_FORM) =>
      apiFetch<Signal>("/signals", {
        method: "POST",
        body: JSON.stringify({
          kind: body.kind,
          title: body.title,
          description: body.description || null,
          author: body.author || null,
          task_context: body.task_context || null,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["signals"] });
      setForm(EMPTY_FORM);
    },
  });

  const review = useMutation({
    mutationFn: (vars: { id: number; status: string; note?: string }) =>
      apiFetch<Signal>(`/signals/${vars.id}/review`, {
        method: "POST",
        body: JSON.stringify({ status: vars.status, review_note: vars.note ?? null }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });

  const convert = useMutation({
    mutationFn: (id: number) =>
      apiFetch<Signal>(`/signals/${id}/convert`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });

  const rows = signals.data ?? [];
  const open = rows.filter((s) => s.status === "new" || s.status === "acknowledged");

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Megaphone size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Проактивні сигнали — до виконання завдання
          </span>
          <span className="card-badge badge-gold">{open.length} відкритих</span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16 }}>
          Будь-хто може заздалегідь зареєструвати попередження, ризик або
          пропозицію — ще до початку виконання завдання. Відповідальна особа
          розглядає сигнал: приймає, відхиляє (з причиною) або перетворює на
          повноцінний AAR-кейс. Так висновки минулих розборів працюють на
          підготовку наступних дій, а не лише на аналіз завершених.
        </p>

        <div className="form-grid">
          <label>
            Тип сигналу
            <select
              className="form-input"
              value={form.kind}
              onChange={(e) =>
                setForm({ ...form, kind: e.target.value as Signal["kind"] })
              }
            >
              {Object.entries(KIND_LABELS).map(([v, label]) => (
                <option key={v} value={v}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Контекст завдання (необов'язково)
            <input
              className="form-input"
              value={form.task_context}
              onChange={(e) => setForm({ ...form, task_context: e.target.value })}
              placeholder="напр.: Виліт 20.07, сектор Б"
            />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            Заголовок
            <input
              className="form-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Коротко: що варто врахувати"
            />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            Опис
            <textarea
              className="form-input"
              rows={3}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Деталі спостереження, ризику або пропозиції"
            />
          </label>
          <label>
            Автор (порожньо = анонімно)
            <input
              className="form-input"
              value={form.author}
              onChange={(e) => setForm({ ...form, author: e.target.value })}
              placeholder="анонімно"
            />
          </label>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              onClick={() => create.mutate(form)}
              disabled={create.isPending || IS_DEMO || !form.title.trim()}
            >
              <Send size={14} /> Подати сигнал
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Журнал сигналів</span>
          <select
            className="form-input"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">Усі статуси</option>
            {Object.entries(STATUS_LABELS).map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </div>

        {signals.isLoading && <div className="loading">Завантаження…</div>}
        {!signals.isLoading && rows.length === 0 && (
          <div className="loading">Сигналів немає — подай перший вище.</div>
        )}

        <div className="signal-cards">
          {rows.map((s) => (
            <div key={s.id} className="signal-review-card">
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span className={kindChip(s.kind)}>{KIND_LABELS[s.kind]}</span>
                <span className={statusChip(s.status)}>{STATUS_LABELS[s.status]}</span>
                {s.task_context && (
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {s.task_context}
                  </span>
                )}
              </div>
              <div style={{ fontWeight: 500, margin: "8px 0 4px" }}>{s.title}</div>
              {s.description && (
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  {s.description}
                </div>
              )}
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                {s.author ?? "анонімно"} · {new Date(s.created_at).toLocaleString("uk")}
                {s.case_id && ` · кейс #${s.case_id}`}
                {s.review_note && ` · «${s.review_note}»`}
              </div>
              {(s.status === "new" || s.status === "acknowledged") && (
                <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
                  {s.status === "new" && (
                    <button
                      className="secondary"
                      disabled={review.isPending || IS_DEMO}
                      onClick={() => review.mutate({ id: s.id, status: "acknowledged" })}
                    >
                      Взяти в розгляд
                    </button>
                  )}
                  <button
                    disabled={review.isPending || IS_DEMO}
                    onClick={() =>
                      review.mutate({
                        id: s.id,
                        status: "accepted",
                        note: "враховано у підготовці",
                      })
                    }
                  >
                    <CheckCircle2 size={14} /> Прийняти
                  </button>
                  <button
                    className="secondary"
                    style={{ color: "var(--accent-red)" }}
                    disabled={review.isPending || IS_DEMO}
                    onClick={() => {
                      const note = window.prompt("Причина відхилення:") ?? "";
                      if (note.trim()) {
                        review.mutate({ id: s.id, status: "dismissed", note });
                      }
                    }}
                  >
                    <XCircle size={14} /> Відхилити
                  </button>
                  <button
                    className="secondary"
                    disabled={convert.isPending || IS_DEMO}
                    onClick={() => convert.mutate(s.id)}
                    title="Створити AAR-кейс із цього сигналу"
                  >
                    <FolderPlus size={14} /> В AAR-кейс
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {IS_DEMO && (
          <p style={{ color: "var(--accent-gold)", fontSize: 12, marginTop: 12 }}>
            <AlertTriangle size={12} style={{ verticalAlign: "-2px" }} /> Demo-режим:
            подання і розгляд сигналів не зберігаються.
          </p>
        )}
      </div>
    </div>
  );
}
