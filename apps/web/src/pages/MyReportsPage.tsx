import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList, Send, Sprout } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";
import {
  errMessage,
  functionLabel,
  FUNCTION_LABELS,
  FUNCTION_ORDER,
  type ParticipantFunction,
} from "../lib/people";

/** Mirrors aar_api.models.aar.CaseStatus. */
type CaseStatus =
  | "open"
  | "analysed"
  | "endorsed"
  | "implemented"
  | "validated"
  | "closed";

/** Mirrors aar_api.models.aar.RecommendationStatus. */
type RecommendationStatus = "proposed" | "in_progress" | "done" | "validated";

/** Mirrors aar_api.schemas.aar.MyReportRequestOut. */
interface MyReportRequest {
  report_id: number;
  case_id: number;
  case_title: string;
  case_status: CaseStatus;
  requested_at: string | null;
  submitted_at: string | null;
  anonymous: boolean;
  function: ParticipantFunction | null;
}

/** Mirrors aar_api.schemas.aar.MyObservationRecommendationOut. */
interface MyObservationRecommendation {
  id: number;
  text: string;
  status: RecommendationStatus;
  auto_validated_at: string | null;
  regressed_at: string | null;
}

/** Mirrors aar_api.schemas.aar.MyObservationOut. */
interface MyObservation {
  report_id: number;
  case_id: number;
  case_title: string;
  case_status: CaseStatus;
  submitted_at: string | null;
  anonymous: boolean;
  outcome_uk: string;
  lesson_identified: string | null;
  recommendations: MyObservationRecommendation[];
}

const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  open: "розбір триває",
  analysed: "аналіз зроблено",
  endorsed: "призначено відповідального",
  implemented: "зміну впроваджено",
  validated: "підтверджено даними",
  closed: "закрито",
};

const REC_STATUS_LABELS: Record<RecommendationStatus, string> = {
  proposed: "запропоновано",
  in_progress: "у роботі",
  done: "виконано",
  validated: "підтверджено даними",
};

function caseChip(s: CaseStatus): string {
  switch (s) {
    case "validated":
    case "implemented":
      return "chip chip-active";
    case "endorsed":
    case "analysed":
      return "chip chip-mid";
    case "closed":
      return "chip";
    default:
      return "chip chip-draft";
  }
}

function recChip(s: RecommendationStatus): string {
  switch (s) {
    case "validated":
      return "chip chip-active";
    case "done":
      return "chip chip-mid";
    case "in_progress":
      return "chip chip-draft";
    default:
      return "chip";
  }
}

function fmtDate(v: string | null): string {
  if (!v) return "—";
  return new Date(v).toLocaleString("uk");
}

/** The six AAR questions, in the order the interview should follow. */
const QUESTIONS = [
  { key: "what_happened", label: "Що сталося" },
  { key: "what_worked", label: "Що спрацювало" },
  { key: "what_failed", label: "Що не спрацювало" },
  { key: "why", label: "Чому, на вашу думку" },
  { key: "external_factors", label: "Зовнішні чинники (РЕБ, погода, ППО…)" },
  { key: "what_to_change", label: "Що змінити наступного разу" },
] as const;

type AnswerKey = (typeof QUESTIONS)[number]["key"];

type ReportForm = Record<AnswerKey, string> & {
  function: ParticipantFunction | "";
  anonymous: boolean;
};

function emptyForm(fn: ParticipantFunction | null): ReportForm {
  return {
    what_happened: "",
    what_worked: "",
    what_failed: "",
    why: "",
    external_factors: "",
    what_to_change: "",
    function: fn ?? "",
    anonymous: false,
  };
}

export default function MyReportsPage() {
  const qc = useQueryClient();
  const [openFor, setOpenFor] = useState<number | null>(null);
  const [form, setForm] = useState<ReportForm>(emptyForm(null));

  const requests = useQuery({
    queryKey: ["my-report-requests"],
    queryFn: () =>
      apiFetch<MyReportRequest[]>(
        "/aar/my-report-requests?include_submitted=false",
      ),
  });

  const observations = useQuery({
    queryKey: ["my-observations"],
    queryFn: () => apiFetch<MyObservation[]>("/aar/my-observations"),
  });

  const submit = useMutation({
    mutationFn: (vars: { req: MyReportRequest; body: ReportForm }) =>
      apiFetch<{ id: number }>(`/aar/cases/${vars.req.case_id}/reports`, {
        method: "POST",
        body: JSON.stringify({
          request_id: vars.req.report_id,
          function: vars.body.function || null,
          anonymous: vars.body.anonymous,
          what_happened: vars.body.what_happened || null,
          what_worked: vars.body.what_worked || null,
          what_failed: vars.body.what_failed || null,
          why: vars.body.why || null,
          external_factors: vars.body.external_factors || null,
          what_to_change: vars.body.what_to_change || null,
        }),
      }),
    onSuccess: () => {
      setOpenFor(null);
      setForm(emptyForm(null));
      qc.invalidateQueries({ queryKey: ["my-report-requests"] });
      qc.invalidateQueries({ queryKey: ["my-observations"] });
    },
  });

  const pending = requests.data ?? [];
  const obs = observations.data ?? [];

  function startReport(r: MyReportRequest) {
    submit.reset();
    setForm(emptyForm(r.function));
    setOpenFor(openFor === r.report_id ? null : r.report_id);
  }

  return (
    <div className="page-stack">
      {/* ───── 1. What is expected of me ───── */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <ClipboardList size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Від мене чекають
          </span>
          <span className="card-badge badge-gold">{pending.length} запитів</span>
        </div>

        {requests.isLoading && <div className="loading">Завантаження…</div>}
        {requests.isError && (
          <div className="error-msg">{errMessage(requests.error)}</div>
        )}
        {!requests.isLoading && !requests.isError && pending.length === 0 && (
          <div className="loading">
            Наразі від вас не чекають жодного звіту. Коли керівник розбору
            попросить вашу версію подій, запит з'явиться тут.
          </div>
        )}

        {pending.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Кейс</th>
                <th>Стан кейсу</th>
                <th>Функція в запиті</th>
                <th>Запит надіслано</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => (
                <tr key={r.report_id}>
                  <td>
                    {r.case_title}{" "}
                    <span className="mono" style={{ color: "var(--text-muted)" }}>
                      #{r.case_id}
                    </span>
                  </td>
                  <td>
                    <span className={caseChip(r.case_status)}>
                      {CASE_STATUS_LABELS[r.case_status]}
                    </span>
                  </td>
                  <td>{functionLabel(r.function)}</td>
                  <td>{fmtDate(r.requested_at)}</td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      className="secondary"
                      onClick={() => startReport(r)}
                      disabled={IS_DEMO}
                    >
                      {openFor === r.report_id ? "Згорнути" : "Подати звіт"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Inline form — deliberately not a modal: the six answers are long
            and the case title must stay visible while they are written. */}
        {pending
          .filter((r) => r.report_id === openFor)
          .map((r) => (
            <div
              key={r.report_id}
              style={{
                marginTop: 16,
                paddingTop: 16,
                borderTop: "1px solid var(--border)",
              }}
            >
              <div style={{ fontWeight: 500, marginBottom: 4 }}>
                Звіт по кейсу: {r.case_title}
              </div>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 13,
                  marginBottom: 12,
                }}
              >
                Шість питань AAR. Заповнюйте те, що знаєте — порожнє поле краще
                за вигадане.
              </p>

              <div className="form-grid">
                <label>
                  Ваша функція в події
                  <select
                    className="form-input"
                    value={form.function}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        function: e.target.value as ParticipantFunction | "",
                      })
                    }
                  >
                    <option value="">не вказано</option>
                    {FUNCTION_ORDER.map((f) => (
                      <option key={f} value={f}>
                        {FUNCTION_LABELS[f]}
                      </option>
                    ))}
                  </select>
                </label>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={form.anonymous}
                      onChange={(e) =>
                        setForm({ ...form, anonymous: e.target.checked })
                      }
                    />
                    Подати анонімно
                  </label>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    Анонімний звіт приховує ваше ім'я від інших читачів кейсу.
                    Ви й далі бачитимете, що з нього вийшло — бо запит був
                    адресований особисто вам.
                  </span>
                </div>

                {QUESTIONS.map((q) => (
                  <label key={q.key} style={{ gridColumn: "1 / -1" }}>
                    {q.label}
                    <textarea
                      className="form-input"
                      rows={3}
                      value={form[q.key]}
                      onChange={(e) => setForm({ ...form, [q.key]: e.target.value })}
                    />
                  </label>
                ))}
              </div>

              {submit.isError && (
                <div className="error-msg">{errMessage(submit.error)}</div>
              )}

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => submit.mutate({ req: r, body: form })}
                  disabled={
                    submit.isPending ||
                    IS_DEMO ||
                    !QUESTIONS.some((q) => form[q.key].trim())
                  }
                >
                  <Send size={14} /> Надіслати звіт
                </button>
                <button className="secondary" onClick={() => setOpenFor(null)}>
                  Скасувати
                </button>
              </div>
            </div>
          ))}

        {IS_DEMO && (
          <p style={{ color: "var(--accent-gold)", fontSize: 12, marginTop: 12 }}>
            <AlertTriangle size={12} style={{ verticalAlign: "-2px" }} /> Demo-режим:
            подання звіту не зберігається.
          </p>
        )}
      </div>

      {/* ───── 2. What came of it — the point of this page ───── */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Sprout size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Що вийшло з моїх спостережень
          </span>
          <span className="card-badge badge-blue">{obs.length}</span>
        </div>

        {observations.isLoading && <div className="loading">Завантаження…</div>}
        {observations.isError && (
          <div className="error-msg">{errMessage(observations.error)}</div>
        )}
        {!observations.isLoading && !observations.isError && obs.length === 0 && (
          <div className="loading">
            Тут з'являється результат ваших звітів: сформульований урок і
            конкретні зміни процедур, які з нього виросли. Щойно керівник
            опрацює кейс, ви побачите не «звіт прийнято», а що саме змінилося
            через вас.
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {obs.map((o) => (
            <div
              key={o.report_id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: 14,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontWeight: 500 }}>{o.case_title}</span>
                <span className={caseChip(o.case_status)}>
                  {CASE_STATUS_LABELS[o.case_status]}
                </span>
                {o.anonymous && <span className="chip">анонімно</span>}
              </div>

              {/* THE payoff sentence. It is the reason people report twice. */}
              <p
                style={{
                  fontSize: 16,
                  lineHeight: 1.5,
                  fontWeight: 500,
                  color: "var(--text-primary)",
                  margin: "10px 0",
                  paddingLeft: 12,
                  borderLeft: "3px solid var(--accent-green)",
                }}
              >
                {o.outcome_uk}
              </p>

              {o.lesson_identified && (
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  <strong>Урок:</strong> {o.lesson_identified}
                </div>
              )}

              {o.recommendations.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      marginBottom: 6,
                    }}
                  >
                    Зміни, що з цього виросли
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {o.recommendations.map((rec) => (
                      <div
                        key={rec.id}
                        style={{ display: "flex", gap: 8, alignItems: "baseline" }}
                      >
                        <span className={recChip(rec.status)}>
                          {REC_STATUS_LABELS[rec.status]}
                        </span>
                        <span style={{ fontSize: 13 }}>{rec.text}</span>
                        {rec.regressed_at && (
                          <span className="chip chip-error">повторилося</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div
                style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10 }}
              >
                Звіт подано {fmtDate(o.submitted_at)} · кейс #{o.case_id}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
