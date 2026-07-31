import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Pencil, Plus, Trash2, Users, X } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";
import {
  errMessage,
  functionLabel,
  FUNCTION_LABELS,
  FUNCTION_ORDER,
  operatorLabel,
  OperatorRow,
  PersonOut,
  Role,
  ROLE_LABELS,
  ROLE_ORDER,
} from "../lib/people";

interface PersonDraft {
  full_name: string;
  callsign: string;
  email: string;
  role: Role;
  operator_id: string; // "" = без експлуатанта
  function: string; // "" = не вказано
  is_active: boolean;
  password: string;
}

const EMPTY_DRAFT: PersonDraft = {
  full_name: "",
  callsign: "",
  email: "",
  role: "participant",
  operator_id: "",
  function: "",
  is_active: true,
  password: "",
};

function draftFrom(p: PersonOut): PersonDraft {
  return {
    full_name: p.full_name,
    callsign: p.callsign ?? "",
    email: p.email ?? "",
    role: p.role,
    operator_id: p.operator_id == null ? "" : String(p.operator_id),
    function: p.function ?? "",
    is_active: p.is_active,
    password: "",
  };
}

/** Only the payload fields the API accepts; empty strings become null. */
function toBody(d: PersonDraft, opts: { withPassword: boolean }): Record<string, unknown> {
  const body: Record<string, unknown> = {
    full_name: d.full_name.trim(),
    callsign: d.callsign.trim() || null,
    email: d.email.trim() || null,
    role: d.role,
    operator_id: d.operator_id === "" ? null : Number(d.operator_id),
    function: d.function === "" ? null : d.function,
  };
  if (opts.withPassword && d.password.trim()) body.password = d.password.trim();
  return body;
}

/** Rows rendered per page. We fetch one more to detect (and announce) a cut. */
const LIST_LIMIT = 200;

export default function PeoplePage() {
  const qc = useQueryClient();

  // ---- filters (all caller-explicit; nothing is filtered implicitly) -----
  const [q, setQ] = useState("");
  const [fOperator, setFOperator] = useState(""); // "" = усі експлуатанти
  const [fFunction, setFFunction] = useState(""); // "" = усі функції
  const [includeInactive, setIncludeInactive] = useState(false);

  const [addDraft, setAddDraft] = useState<PersonDraft>(EMPTY_DRAFT);
  const [editId, setEditId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<PersonDraft>(EMPTY_DRAFT);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");

  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (fOperator) params.set("operator_id", fOperator);
  if (fFunction) params.set("function", fFunction);
  if (includeInactive) params.set("include_inactive", "true");
  // Fetch one more than we render so a full page is detectable — a silently
  // truncated roster would hide exactly the people the flexible model exists
  // to reach (the server ranks affiliated people first).
  params.set("limit", String(LIST_LIMIT + 1));
  const url = `/people?${params.toString()}`;

  const people = useQuery({
    queryKey: ["people", q.trim(), fOperator, fFunction, includeInactive],
    queryFn: () => apiFetch<PersonOut[]>(url),
  });
  const operators = useQuery({
    queryKey: ["dict", "/dictionaries/operators"],
    queryFn: () => apiFetch<OperatorRow[]>("/dictionaries/operators"),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["people"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch<PersonOut>("/people", {
        method: "POST",
        body: JSON.stringify(toBody(addDraft, { withPassword: true })),
      }),
    onSuccess: () => {
      invalidate();
      setAddDraft(EMPTY_DRAFT);
      setErr("");
      setNotice("Особу додано.");
    },
    onError: (e) => setErr(errMessage(e)),
  });

  const update = useMutation({
    mutationFn: (id: number) =>
      apiFetch<PersonOut>(`/people/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          ...toBody(editDraft, { withPassword: false }),
          is_active: editDraft.is_active,
        }),
      }),
    onSuccess: () => {
      invalidate();
      setEditId(null);
      setErr("");
      setNotice("");
    },
    onError: (e) => setErr(errMessage(e)),
  });

  const setPassword = useMutation({
    mutationFn: (vars: { id: number; password: string }) =>
      apiFetch<PersonOut>(`/people/${vars.id}/set-password`, {
        method: "POST",
        body: JSON.stringify({ password: vars.password }),
      }),
    onSuccess: () => {
      invalidate();
      setErr("");
      setNotice("Пароль встановлено — особа тепер може входити.");
    },
    onError: (e) => setErr(errMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ deleted: number }>(`/people/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      setErr("");
      setNotice("");
    },
    onError: (e) => setErr(errMessage(e)),
  });

  function startEdit(p: PersonOut) {
    setEditId(p.id);
    setEditDraft(draftFrom(p));
    setErr("");
    setNotice("");
  }

  const ops = operators.data ?? [];
  const fetched = people.data ?? [];
  const truncated = fetched.length > LIST_LIMIT;
  const rows = truncated ? fetched.slice(0, LIST_LIMIT) : fetched;

  const operatorSelect = (value: string, onChange: (v: string) => void, disabled: boolean) => (
    <select
      className="form-input"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">— без експлуатанта —</option>
      {ops.map((o) => (
        <option key={o.id} value={String(o.id)}>
          {o.code} · {o.name_uk}
        </option>
      ))}
    </select>
  );

  const functionSelect = (value: string, onChange: (v: string) => void, disabled: boolean) => (
    <select
      className="form-input"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">не вказано</option>
      {FUNCTION_ORDER.map((f) => (
        <option key={f} value={f}>
          {FUNCTION_LABELS[f]}
        </option>
      ))}
    </select>
  );

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Users size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Люди (учасники AAR)
          </span>
          <span className="card-badge badge-blue">{rows.length} у списку</span>
          {truncated && (
            <span style={{ fontSize: 11, color: "var(--accent-gold)" }}>
              показано перших {LIST_LIMIT} — звузьте пошук, щоб побачити решту
            </span>
          )}
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          Реєстр осіб, з якого добираються учасники AAR-кейсу. Особа без пароля —
          «тільки реєстр»: її можна обрати учасником і запитати звіт, але вона не
          входить у систему. Експлуатант — це <b>типова приналежність</b>: вона
          підказує порядок у списку і <b>ніколи</b> не обмежує вибір учасників у кейсі.
          {IS_DEMO && " У режимі демо редагування вимкнено."}
        </p>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Фільтри</span>
        </div>
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
              <option value="">усі експлуатанти</option>
              {ops.map((o) => (
                <option key={o.id} value={String(o.id)}>
                  {o.code} · {o.name_uk}
                </option>
              ))}
            </select>
          </label>
          <label>
            Функція
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
          <label>
            Неактивні
            <select
              className="form-input"
              value={includeInactive ? "1" : "0"}
              onChange={(e) => setIncludeInactive(e.target.value === "1")}
            >
              <option value="0">лише активні</option>
              <option value="1">показати й неактивних</option>
            </select>
          </label>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Список осіб</span>
        </div>

        {err && <div className="error-msg" style={{ marginBottom: 10 }}>{err}</div>}
        {notice && (
          <p style={{ color: "var(--accent-blue)", fontSize: 12, marginBottom: 10 }}>
            ⓘ {notice}
          </p>
        )}
        {people.isLoading && <div className="loading">Завантаження…</div>}
        {people.isError && <div className="error-msg">Помилка завантаження</div>}

        {people.data && (
          <table className="data-table">
            <thead>
              <tr>
                <th>ПІБ</th>
                <th>Позивний</th>
                <th>Експлуатант</th>
                <th>Функція</th>
                <th>Активність</th>
                <th>Може входити</th>
                <th style={{ width: 120, textAlign: "right" }}>Дії</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) =>
                editId === p.id ? (
                  <Fragment key={p.id}>
                    <tr>
                      <td>
                        <input
                          className="form-input"
                          value={editDraft.full_name}
                          onChange={(e) =>
                            setEditDraft({ ...editDraft, full_name: e.target.value })
                          }
                        />
                      </td>
                      <td>
                        <input
                          className="form-input"
                          value={editDraft.callsign}
                          placeholder="—"
                          onChange={(e) =>
                            setEditDraft({ ...editDraft, callsign: e.target.value })
                          }
                        />
                      </td>
                      <td>
                        {operatorSelect(
                          editDraft.operator_id,
                          (v) => setEditDraft({ ...editDraft, operator_id: v }),
                          false,
                        )}
                      </td>
                      <td>
                        {functionSelect(
                          editDraft.function,
                          (v) => setEditDraft({ ...editDraft, function: v }),
                          false,
                        )}
                      </td>
                      <td>
                        <select
                          className="form-input"
                          value={editDraft.is_active ? "1" : "0"}
                          onChange={(e) =>
                            setEditDraft({ ...editDraft, is_active: e.target.value === "1" })
                          }
                        >
                          <option value="1">активна</option>
                          <option value="0">неактивна</option>
                        </select>
                      </td>
                      <td>
                        <span className={p.can_login ? "chip chip-active" : "chip"}>
                          {p.can_login ? "так" : "ні"}
                        </span>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button
                          className="icon-btn"
                          title="Зберегти"
                          disabled={update.isPending || !editDraft.full_name.trim()}
                          onClick={() => update.mutate(p.id)}
                        >
                          <Check size={16} />
                        </button>
                        <button
                          className="icon-btn"
                          title="Скасувати"
                          onClick={() => {
                            setEditId(null);
                            setErr("");
                          }}
                        >
                          <X size={16} />
                        </button>
                      </td>
                    </tr>
                    <tr>
                      <td colSpan={7}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <input
                            className="form-input"
                            style={{ flex: 1 }}
                            value={editDraft.email}
                            placeholder="email (потрібен для входу)"
                            onChange={(e) =>
                              setEditDraft({ ...editDraft, email: e.target.value })
                            }
                          />
                          <select
                            className="form-input"
                            style={{ width: 190 }}
                            value={editDraft.role}
                            onChange={(e) =>
                              setEditDraft({ ...editDraft, role: e.target.value as Role })
                            }
                          >
                            {ROLE_ORDER.map((r) => (
                              <option key={r} value={r}>
                                {ROLE_LABELS[r]}
                              </option>
                            ))}
                          </select>
                        </div>
                      </td>
                    </tr>
                  </Fragment>
                ) : (
                  <tr key={p.id}>
                    <td>
                      {p.full_name}
                      {p.email && (
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          {p.email}
                        </div>
                      )}
                    </td>
                    <td className="mono">{p.callsign ?? "—"}</td>
                    <td>{operatorLabel(p.operator_id, ops)}</td>
                    <td>{functionLabel(p.function)}</td>
                    <td>
                      <span className={p.is_active ? "chip chip-active" : "chip chip-error"}>
                        {p.is_active ? "активна" : "неактивна"}
                      </span>
                    </td>
                    <td>
                      <span className={p.can_login ? "chip chip-active" : "chip"}>
                        {p.can_login ? "так" : "ні"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button
                        className="icon-btn"
                        title="Редагувати"
                        disabled={IS_DEMO}
                        onClick={() => startEdit(p)}
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        className="icon-btn"
                        title="Задати пароль (дозволити вхід)"
                        disabled={IS_DEMO || setPassword.isPending}
                        onClick={() => {
                          const pw = prompt(
                            `Новий пароль для «${p.full_name}» (мінімум 8 символів):`,
                          );
                          if (pw && pw.trim().length >= 8) {
                            setPassword.mutate({ id: p.id, password: pw.trim() });
                          } else if (pw !== null) {
                            setErr("Пароль має містити щонайменше 8 символів.");
                          }
                        }}
                      >
                        <KeyRound size={15} />
                      </button>
                      <button
                        className="icon-btn"
                        title="Видалити"
                        disabled={IS_DEMO || remove.isPending}
                        onClick={() => {
                          if (confirm(`Видалити «${p.full_name}»?`)) remove.mutate(p.id);
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ),
              )}

              {/* add row */}
              <tr>
                <td>
                  <input
                    className="form-input"
                    value={addDraft.full_name}
                    placeholder="ПІБ"
                    disabled={IS_DEMO}
                    onChange={(e) => setAddDraft({ ...addDraft, full_name: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    className="form-input"
                    value={addDraft.callsign}
                    placeholder="позивний"
                    disabled={IS_DEMO}
                    onChange={(e) => setAddDraft({ ...addDraft, callsign: e.target.value })}
                  />
                </td>
                <td>
                  {operatorSelect(
                    addDraft.operator_id,
                    (v) => setAddDraft({ ...addDraft, operator_id: v }),
                    IS_DEMO,
                  )}
                </td>
                <td>
                  {functionSelect(
                    addDraft.function,
                    (v) => setAddDraft({ ...addDraft, function: v }),
                    IS_DEMO,
                  )}
                </td>
                <td colSpan={2}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input
                      className="form-input"
                      value={addDraft.email}
                      placeholder="email (необов'язково)"
                      disabled={IS_DEMO}
                      onChange={(e) => setAddDraft({ ...addDraft, email: e.target.value })}
                    />
                    <input
                      className="form-input"
                      type="password"
                      value={addDraft.password}
                      placeholder="пароль (admin)"
                      disabled={IS_DEMO}
                      onChange={(e) => setAddDraft({ ...addDraft, password: e.target.value })}
                    />
                  </div>
                </td>
                <td style={{ textAlign: "right" }}>
                  <button
                    className="icon-btn"
                    title="Додати"
                    disabled={IS_DEMO || create.isPending || !addDraft.full_name.trim()}
                    onClick={() => {
                      // Mirror the server's minimum so the user gets a readable
                      // message instead of a pydantic 422 array that
                      // errMessage() cannot unpack.
                      const pw = addDraft.password.trim();
                      if (pw && pw.length < 8) {
                        setErr("Пароль має містити щонайменше 8 символів.");
                        return;
                      }
                      create.mutate();
                    }}
                  >
                    <Plus size={16} />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        )}

        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
          Видалення заборонено, доки на особу посилаються індивідуальні звіти чи
          контекст-активи — у такому разі зробіть її неактивною замість видалення.
        </p>
      </div>
    </div>
  );
}
