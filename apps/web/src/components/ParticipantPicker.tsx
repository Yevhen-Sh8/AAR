import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, UserPlus } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";
import {
  errMessage,
  functionLabel,
  FUNCTION_LABELS,
  FUNCTION_ORDER,
  operatorLabel,
  OperatorRow,
  PersonOut,
  ReportRequestSummary,
} from "../lib/people";

/**
 * Per-case participant picker.
 *
 * THE PROJECT AXIOM: the case's operator only RANKS the list (the server does
 * that via `suggest_for_case_id`) and marks rows «за замовчуванням». Every
 * person in the roster stays visible and checkable; the operator filter
 * defaults to «усі експлуатанти» and that option is always available.
 *
 * An off-roster pick is a normal 201 outcome — the returned `warnings[]` and
 * `off_roster_user_ids[]` are rendered as an informational notice, never as
 * an error.
 */

/** Rows rendered per page. We fetch one more to detect (and announce) a cut. */
const PICKER_LIMIT = 200;

export default function ParticipantPicker({
  caseId,
  caseOperatorId,
  onRequested,
}: {
  caseId: number;
  caseOperatorId: number | null;
  onRequested?: () => void;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const [q, setQ] = useState("");
  const [fOperator, setFOperator] = useState(""); // "" = усі експлуатанти (default)
  const [fFunction, setFFunction] = useState("");
  const [err, setErr] = useState("");
  const [summary, setSummary] = useState<ReportRequestSummary | null>(null);

  const params = new URLSearchParams();
  params.set("suggest_for_case_id", String(caseId));
  if (q.trim()) params.set("q", q.trim());
  if (fOperator) params.set("operator_id", fOperator);
  if (fFunction) params.set("function", fFunction);
  // Ask for one row MORE than we render, so a full page is detectable and the
  // cut is never silent. This matters for the axiom: the server ranks the
  // case operator's people first, so the rows a silent cap would drop are
  // exactly the off-roster people the flexible model exists to reach.
  params.set("limit", String(PICKER_LIMIT + 1));

  const people = useQuery({
    queryKey: ["people-suggest", caseId, q.trim(), fOperator, fFunction],
    queryFn: () => apiFetch<PersonOut[]>(`/people?${params.toString()}`),
  });
  const operators = useQuery({
    queryKey: ["dict", "/dictionaries/operators"],
    queryFn: () => apiFetch<OperatorRow[]>("/dictionaries/operators"),
  });

  const fetched = people.data ?? [];
  const truncated = fetched.length > PICKER_LIMIT;
  const rows = truncated ? fetched.slice(0, PICKER_LIMIT) : fetched;
  const ops = operators.data ?? [];
  const byId = useMemo(() => new Map(rows.map((p) => [p.id, p])), [rows]);

  const suggestedCount = caseOperatorId == null
    ? 0
    : rows.filter((p) => p.operator_id === caseOperatorId).length;

  const request = useMutation({
    mutationFn: () =>
      apiFetch<ReportRequestSummary>(`/aar/cases/${caseId}/request-reports`, {
        method: "POST",
        body: JSON.stringify({
          participants: selected.map((user_id) => ({ user_id })),
        }),
      }),
    onSuccess: (data) => {
      setErr("");
      setSummary(data && typeof data === "object" && "requested_count" in data ? data : null);
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["case-reports"] });
      onRequested?.();
    },
    onError: (e) => {
      setSummary(null);
      setErr(errMessage(e));
    },
  });

  function toggle(id: number) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  return (
    <div>
      <div className="card-header">
        <span className="card-title">
          <UserPlus size={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />
          Обрати учасників і запитати звіти
        </span>
        <span className="card-badge badge-blue">{selected.length} обрано</span>
      </div>

      <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "0 0 10px" }}>
        Приналежність до експлуатанта лише підказує порядок: рядки з позначкою
        «за замовчуванням» — це особи цього експлуатанта. Обрати можна будь-кого
        зі списку; вибір «поза складом» — нормальний і не є помилкою.
      </p>

      <div className="form-grid">
        <label>
          Пошук (ПІБ або позивний)
          <input
            className="form-input"
            value={q}
            placeholder="почніть вводити…"
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label>
          Експлуатант
          <select
            className="form-input"
            value={fOperator}
            onChange={(e) => setFOperator(e.target.value)}
          >
            {/* Always available, always the default — never hides the rest. */}
            <option value="">усі експлуатанти</option>
            {ops.map((o) => (
              <option key={o.id} value={String(o.id)}>
                {o.code} · {o.name_uk}
              </option>
            ))}
          </select>
        </label>
        <label>
          Фільтр за функцією
          <select
            className="form-input"
            value={fFunction}
            onChange={(e) => setFFunction(e.target.value)}
          >
            <option value="">усі функції</option>
            {FUNCTION_ORDER.map((f) => (
              <option key={f} value={f}>
                {FUNCTION_LABELS[f]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {err && <div className="error-msg" style={{ marginBottom: 10 }}>{err}</div>}
      {people.isLoading && <div className="loading">Завантаження списку осіб…</div>}
      {people.isError && <div className="error-msg">Не вдалося завантажити список осіб</div>}

      {people.data && (
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 36 }} />
              <th>ПІБ</th>
              <th>Позивний</th>
              <th>Експлуатант</th>
              <th>Функція</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const suggested = caseOperatorId != null && p.operator_id === caseOperatorId;
              return (
                <tr key={p.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Обрати ${p.full_name}`}
                      checked={selected.includes(p.id)}
                      onChange={() => toggle(p.id)}
                    />
                  </td>
                  <td>
                    {p.full_name}
                    {suggested && (
                      <span className="chip chip-mid" style={{ marginLeft: 6 }}>
                        за замовчуванням
                      </span>
                    )}
                  </td>
                  <td className="mono">{p.callsign ?? "—"}</td>
                  <td>{operatorLabel(p.operator_id, ops)}</td>
                  <td>{functionLabel(p.function)}</td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ color: "var(--text-muted)" }}>
                  Нікого не знайдено — послабте фільтри.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <button
          onClick={() => request.mutate()}
          disabled={request.isPending || IS_DEMO || selected.length === 0}
        >
          <Send size={14} /> Розіслати запити ({selected.length})
        </button>
        <button
          className="secondary"
          onClick={() => setSelected([])}
          disabled={selected.length === 0}
        >
          Зняти вибір
        </button>
        {caseOperatorId != null && (
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
            підказано за замовчуванням: {suggestedCount} з {rows.length}
          </span>
        )}
        {truncated && (
          <span style={{ fontSize: 11, color: "var(--accent-gold)" }}>
            показано перших {PICKER_LIMIT} — звузьте пошук, щоб побачити решту
            (список не обмежений експлуатантом)
          </span>
        )}
      </div>

      {summary && (
        <div
          style={{
            marginTop: 12,
            padding: 10,
            borderRadius: 6,
            background: "var(--accent-blue-muted)",
            color: "var(--accent-blue)",
            fontSize: 12,
          }}
        >
          <div>
            ⓘ Запитано звітів: {summary.requested_count}
            {summary.skipped_existing > 0 && ` · пропущено (вже запитано): ${summary.skipped_existing}`}
          </div>
          {summary.off_roster_user_ids.length > 0 && (
            <div style={{ marginTop: 6 }}>
              Поза складом експлуатанта кейсу:{" "}
              {summary.off_roster_user_ids
                .map((id) => byId.get(id)?.full_name ?? `#${id}`)
                .join(", ")}{" "}
              — це нормально: свідчення ззовні підвищує якість атрибуції.
            </div>
          )}
          {summary.warnings.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {summary.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
          {summary.missing_functions.length > 0 && (
            <div style={{ marginTop: 6 }}>
              Не покриті функції:{" "}
              {summary.missing_functions.map((f) => functionLabel(f)).join(", ")}
            </div>
          )}
        </div>
      )}

      {IS_DEMO && (
        <p style={{ color: "var(--accent-gold)", fontSize: 12, marginTop: 10 }}>
          ⓘ Demo-режим: запити не надсилаються.
        </p>
      )}
    </div>
  );
}
