import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderKanban,
  ArrowRight,
  Sparkles,
  Save,
  UserPlus,
  EyeOff,
  Lightbulb,
  Plus,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";
import ParticipantPicker from "../components/ParticipantPicker";
import { FUNCTION_ORDER, functionLabel, type ParticipantFunction } from "../lib/people";

/** Mirrors aar_api.models.aar.DecisionQuality (ADR-024). */
type DecisionQuality = "unassessed" | "sound" | "acceptable" | "flawed";

const DECISION_LABELS: Record<DecisionQuality, string> = {
  unassessed: "не оцінено",
  sound: "правильне рішення",
  acceptable: "прийнятне, але був кращий варіант",
  flawed: "хибне рішення",
};

const DECISION_HINT =
  "Оцінюється РІШЕННЯ на підставі того, що було відомо на той момент, — " +
  "окремо від того, чим усе скінчилось. Правильне рішення може закінчитись " +
  "втратою (обстановка змінилась після пуску), хибне — успіхом (РЕБ того дня " +
  "не працював). Оцінка за наслідком вчить боятися випадковості, а не думати.";

interface AARCase {
  id: number;
  title: string;
  status: string;
  trigger: string;
  operator_id: number | null;
  summary: string | null;
  what_was_planned: string | null;
  what_happened: string | null;
  analysis: string | null;
  lesson_identified: string | null;
  opr: string | null;
  decision_quality: DecisionQuality;
  decision_rationale: string | null;
  analysis_source: string | null;
  analysis_drafted_at: string | null;
  opened_at: string;
  closed_at: string | null;
}

interface CaseReport {
  id: number;
  user_id: number | null;
  requested_for_user_id: number | null;
  anonymous: boolean;
  // All six narrative fields of IndividualReportOut. Showing only two of them
  // (what_happened / why) hid two thirds of the testimony from the manager.
  what_happened: string | null;
  what_worked: string | null;
  what_failed: string | null;
  why: string | null;
  external_factors: string | null;
  what_to_change: string | null;
  requested_at: string | null;
  submitted_at: string | null;
  // Wave 11 snapshots. `function` is what the loss-zone model actually needs
  // (it survives anonymisation, which nulls user_id); `off_roster` records
  // that the person was outside the case operator — a normal, useful fact,
  // never an error. Both are persisted per report, so they must be rendered
  // here rather than living only in the picker's transient state.
  function: string | null;
  off_roster: boolean;
}

const STAGES = [
  { value: "open", label: "Open", note: "Спостереження зафіксовано" },
  { value: "analysed", label: "Analysed", note: "Аналіз зроблено (LI)" },
  { value: "endorsed", label: "Endorsed", note: "Призначено відповідального" },
  { value: "implemented", label: "Implemented", note: "Рекомендацію впроваджено" },
  { value: "validated", label: "Validated", note: "Підтверджено даними (LL)" },
  { value: "closed", label: "Closed", note: "Інституціалізовано" },
] as const;

function stageIndex(status: string): number {
  return STAGES.findIndex((s) => s.value === status);
}

function NextStageButton({
  case_,
  onTransition,
  disabled,
}: {
  case_: AARCase;
  onTransition: (target: string) => void;
  disabled: boolean;
}) {
  const i = stageIndex(case_.status);
  if (i < 0 || i >= STAGES.length - 1) return null;
  const next = STAGES[i + 1];
  return (
    <button
      onClick={() => onTransition(next.value)}
      disabled={disabled}
      title={next.note}
    >
      <ArrowRight size={14} /> {next.label}
    </button>
  );
}

function StageBar({ status }: { status: string }) {
  const i = stageIndex(status);
  return (
    <div className="stage-bar">
      {STAGES.map((s, idx) => (
        <div
          key={s.value}
          className={
            "stage-pill " +
            (idx < i ? "stage-done" : idx === i ? "stage-current" : "stage-todo")
          }
          title={s.note}
        >
          {s.label}
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------
// Recommendations — the IMPLEMENTED stage of the NATO cycle.
//
// There is deliberately NO manual "validated" control: validation is earned
// by services/recommendation_validation.py when the trigger signature stops
// recurring. A clickable "validated" would let a user fake the one metric
// (recurrence_rate_pct / time_to_validation) that proves the loop works.
// --------------------------------------------------------------------------

type RecStatus = "proposed" | "in_progress" | "done" | "validated";

/** Mirrors aar_api.schemas.aar.RecommendationOut. */
interface RecommendationRow {
  id: number;
  case_id?: number;
  text: string;
  status: RecStatus;
  auto_validated_at: string | null;
  regressed_at: string | null;
  validated_at?: string | null;
  evidence_count?: number;
  signature?: string | null;
}

const REC_STATUS_LABELS: Record<RecStatus, string> = {
  proposed: "запропоновано",
  in_progress: "у роботі",
  done: "виконано",
  validated: "підтверджено",
};

const REC_STATUS_CHIP: Record<RecStatus, string> = {
  proposed: "chip",
  in_progress: "chip chip-draft",
  done: "chip chip-mid",
  validated: "chip chip-active",
};

const REC_NEXT: Partial<Record<RecStatus, RecStatus>> = {
  proposed: "in_progress",
  in_progress: "done",
};

const VALIDATION_NOTE =
  "Статус «підтверджено» не виставляється вручну: його присвоює рушій " +
  "повторюваності, коли сигнатура кейсу не повторюється протягом контрольного " +
  "вікна. Ручна кнопка дозволила б підробити саме ту метрику, яка доводить, " +
  "що цикл навчання працює.";

function RecommendationsSection({ caseId }: { caseId: number }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");

  // Reads the real per-case list endpoint. Previously this had to be
  // reconstructed from /aar/my-observations filtered by case_id, which is
  // keyed on the CALLER's own testimony — so a manager who never submitted a
  // report in the case saw nothing, and the manager is exactly who drives
  // this stage.
  const recs = useQuery({
    queryKey: ["case-recommendations", caseId],
    queryFn: () =>
      apiFetch<RecommendationRow[]>(`/aar/cases/${caseId}/recommendations`),
  });

  const rows = recs.data ?? [];

  const addRec = useMutation({
    mutationFn: (body: { text: string }) =>
      apiFetch<RecommendationRow>(`/aar/cases/${caseId}/recommendations`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["case-recommendations", caseId] });
    },
  });

  const setStatus = useMutation({
    mutationFn: (vars: { id: number; status: RecStatus }) =>
      apiFetch<RecommendationRow>(`/aar/recommendations/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: vars.status }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case-recommendations", caseId] });
    },
  });

  return (
    <div style={{ borderTop: "1px solid var(--border-muted)", marginTop: 24, paddingTop: 16 }}>
      <div className="card-header">
        <span className="card-title">
          <Lightbulb size={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />
          Рекомендації
        </span>
        <span className="card-badge badge-blue">{rows.length}</span>
      </div>

      {rows.length === 0 ? (
        <div className="loading">
          Рекомендацій не видно. Додайте першу — саме вона переводить кейс у стадію
          Implemented.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {rows.map((r) => {
            const next = REC_NEXT[r.status];
            return (
              <li
                key={r.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 8,
                  padding: "8px 0",
                  borderBottom: "1px solid var(--border-muted)",
                }}
              >
                <span style={{ flex: 1 }}>{r.text}</span>
                <span className={REC_STATUS_CHIP[r.status]} title={VALIDATION_NOTE}>
                  {REC_STATUS_LABELS[r.status]}
                </span>
                {r.auto_validated_at && (
                  <span
                    className="chip chip-active"
                    title={`${new Date(r.auto_validated_at).toLocaleString("uk")} — ${VALIDATION_NOTE}`}
                  >
                    підтверджено автоматично
                  </span>
                )}
                {r.regressed_at && (
                  <span
                    className="chip chip-error"
                    title={`Сигнатура повторилася ${new Date(r.regressed_at).toLocaleString("uk")} — рекомендація повернута в роботу`}
                  >
                    повторилося
                  </span>
                )}
                {next && (
                  <button
                    className="secondary"
                    onClick={() => setStatus.mutate({ id: r.id, status: next })}
                    disabled={setStatus.isPending || IS_DEMO}
                    title={`Перевести у стан «${REC_STATUS_LABELS[next]}». ${VALIDATION_NOTE}`}
                  >
                    <ArrowRight size={12} /> {REC_STATUS_LABELS[next]}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          className="form-input"
          style={{ flex: 1 }}
          value={text}
          placeholder="Додати рекомендацію…"
          onChange={(e) => setText(e.target.value)}
          disabled={IS_DEMO}
        />
        <button
          onClick={() => addRec.mutate({ text: text.trim() })}
          disabled={addRec.isPending || IS_DEMO || text.trim().length === 0}
          title="POST /aar/cases/{id}/recommendations"
        >
          <Plus size={14} /> Додати рекомендацію
        </button>
      </div>

      <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
        Статус ведеться вручну лише до «виконано». {VALIDATION_NOTE}
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Report coverage — whose voice is present. GET /aar/report-coverage?case_id=N
// --------------------------------------------------------------------------

type Zone = "operator" | "manufacturer" | "external" | "unknown";

const ZONE_LABELS: Record<Zone, string> = {
  operator: "експлуатант",
  manufacturer: "виробник",
  external: "зовнішня",
  unknown: "невідомо",
};

/** Mirrors aar_api.schemas.aar.ReportCoverageOut. */
interface ReportCoverage {
  case_id: number;
  submitted: number;
  pending: number;
  functions: Record<string, number>;
  zones_covered: string[];
  zones_missing: string[];
  off_roster_count: number;
  single_function_only: boolean;
  anonymity_floor: number;
}

function zoneLabel(z: string): string {
  return ZONE_LABELS[z as Zone] ?? z;
}

function CoverageStrip({ caseId }: { caseId: number }) {
  const coverage = useQuery({
    queryKey: ["report-coverage", caseId],
    queryFn: () => apiFetch<ReportCoverage>(`/aar/report-coverage?case_id=${caseId}`),
  });
  const c = coverage.data;
  if (!c) return null;

  const functionKeys = [
    ...FUNCTION_ORDER.filter((f) => c.functions[f]),
    ...Object.keys(c.functions).filter(
      (k) => !(FUNCTION_ORDER as string[]).includes(k),
    ),
  ];

  return (
    <div
      style={{
        border: "1px solid var(--border-muted)",
        borderRadius: 8,
        padding: 10,
        marginBottom: 12,
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 8,
        fontSize: 12,
      }}
    >
      <span style={{ color: "var(--text-muted)" }}>Кого почули:</span>
      {functionKeys.length === 0 && (
        <span style={{ color: "var(--text-muted)" }}>нікого</span>
      )}
      {functionKeys.map((f) => (
        <span key={f} className="chip chip-mid">
          {functionLabel(f === "unknown" ? null : f)} · {c.functions[f]}
        </span>
      ))}
      {c.off_roster_count > 0 && (
        <span className="chip" title="Свідчення поза складом експлуатанта">
          поза складом · {c.off_roster_count}
        </span>
      )}

      {c.zones_missing.length > 0 && (
        <span style={{ color: "var(--accent-red)", fontWeight: 600 }}>
          Не почуто: {c.zones_missing.map(zoneLabel).join(", ")}
        </span>
      )}
      {c.zones_missing.length === 0 && c.zones_covered.length > 0 && (
        <span style={{ color: "var(--accent-green)" }}>
          Зони покрито: {c.zones_covered.map(zoneLabel).join(", ")}
        </span>
      )}

      {c.single_function_only && (
        <span style={{ width: "100%", color: "var(--accent-red)" }}>
          <ShieldAlert size={12} style={{ verticalAlign: "-2px", marginRight: 4 }} />
          свідчення лише від однієї функції — атрибуція зони втрати ненадійна
        </span>
      )}
      {c.anonymity_floor > 0 && c.anonymity_floor <= 3 && (
        <span style={{ width: "100%", color: "var(--accent-gold)" }}>
          анонімність ілюзорна при {c.anonymity_floor} учасниках
        </span>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------

const NARRATIVE_FIELDS: { key: keyof CaseReport; label: string }[] = [
  { key: "what_happened", label: "Що сталось" },
  { key: "what_worked", label: "Що спрацювало" },
  { key: "what_failed", label: "Що не спрацювало" },
  { key: "why", label: "Чому" },
  { key: "external_factors", label: "Зовнішні чинники" },
  { key: "what_to_change", label: "Що змінити" },
];

function ReportRow({ r }: { r: CaseReport }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td className="mono">
          <button
            className="secondary"
            style={{ padding: "2px 6px", marginRight: 4 }}
            onClick={() => setOpen((v) => !v)}
            title={open ? "Згорнути свідчення" : "Показати всі шість полів свідчення"}
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
          {r.id}
        </td>
        <td>
          {r.anonymous ? (
            <span style={{ color: "var(--accent-gold)" }}>
              <EyeOff size={12} style={{ verticalAlign: "-2px" }} /> анонімно
            </span>
          ) : r.user_id ? (
            <span className="mono">user #{r.user_id}</span>
          ) : (
            <span style={{ color: "var(--text-muted)" }}>
              (запит #{r.requested_for_user_id})
            </span>
          )}
          {r.off_roster && (
            <span
              className="chip chip-mid"
              style={{ marginLeft: 6 }}
              title="Свідчення поза складом експлуатанта — це нормально й підвищує якість атрибуції"
            >
              поза складом
            </span>
          )}
        </td>
        <td>{functionLabel(r.function as ParticipantFunction | null)}</td>
        <td style={{ maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {r.what_happened ?? "—"}
        </td>
        <td style={{ maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {r.why ?? "—"}
        </td>
        <td>
          <span className={r.submitted_at ? "chip chip-active" : "chip chip-draft"}>
            {r.submitted_at ? "submitted" : "pending"}
          </span>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6}>
            <div className="nato-grid" style={{ padding: "8px 0" }}>
              {NARRATIVE_FIELDS.map((f) => (
                <div key={f.key as string}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{f.label}</div>
                  <div style={{ whiteSpace: "pre-wrap" }}>
                    {(r[f.key] as string | null) ?? "—"}
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function CasesPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<AARCase | null>(null);
  const [draft, setDraft] = useState<Partial<AARCase>>({});

  const cases = useQuery({
    queryKey: ["cases-all"],
    queryFn: () => apiFetch<AARCase[]>("/aar/cases?limit=100"),
  });

  const patchCase = useMutation({
    mutationFn: (vars: { id: number; body: Partial<AARCase> }) =>
      apiFetch<AARCase>(`/aar/cases/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify(vars.body),
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["cases-all"] });
      setSelected(data);
      setDraft({});
    },
  });

  const transition = useMutation({
    mutationFn: (vars: { id: number; to: string }) =>
      apiFetch<AARCase>(`/aar/cases/${vars.id}/transition`, {
        method: "POST",
        body: JSON.stringify({ to: vars.to }),
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["cases-all"] });
      setSelected(data);
    },
  });

  const draftAnalysis = useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ markdown: string }>(`/llm/cases/${id}/draft-analysis`, {
        method: "POST",
      }),
    onSuccess: (data) => {
      if (selected) {
        setDraft({ ...draft, analysis: data.markdown });
      }
      qc.invalidateQueries({ queryKey: ["cases-all"] });
    },
  });

  const reports = useQuery({
    queryKey: ["case-reports", selected?.id],
    queryFn: () =>
      apiFetch<CaseReport[]>(`/aar/cases/${selected!.id}/reports`),
    enabled: !!selected,
  });

  // The LLM draft must rest on actual testimony: the server refuses with 409
  // when nothing has been submitted, so mirror that in the UI instead of
  // letting the user press a button that cannot succeed.
  const caseReports = reports.data ?? [];
  const submittedCount = caseReports.filter((r) => r.submitted_at).length;
  const pendingCount = caseReports.filter((r) => !r.submitted_at).length;

  const rows = cases.data ?? [];
  const grouped = STAGES.map((s) => ({
    stage: s,
    items: rows.filter((c) => c.status === s.value),
  }));
  const current = selected ?? rows[0] ?? null;
  const value = (k: keyof AARCase): string =>
    (draft[k] as string | undefined) ?? (current?.[k] as string | null) ?? "";

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <FolderKanban size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            AAR-кейси за NATO-циклом
          </span>
          <span className="card-badge badge-blue">{rows.length} разом</span>
        </div>
        <div className="stage-columns">
          {grouped.map((g) => (
            <div key={g.stage.value} className="stage-col">
              <div className="stage-col-head">
                {g.stage.label}
                <span style={{ color: "var(--text-muted)", marginLeft: 4 }}>
                  {g.items.length}
                </span>
              </div>
              {g.items.map((c) => (
                <div
                  key={c.id}
                  className={
                    current?.id === c.id ? "case-card case-selected" : "case-card"
                  }
                  onClick={() => {
                    setSelected(c);
                    setDraft({});
                  }}
                >
                  <div className="case-title">
                    {c.title.replace(/\[.*\]/, "").trim()}
                  </div>
                  <div className="case-meta">
                    {c.trigger} · {new Date(c.opened_at).toLocaleDateString("uk")}
                  </div>
                </div>
              ))}
              {g.items.length === 0 && (
                <div className="case-empty">—</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {current && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              #{current.id} · {current.title.replace(/\[.*\]/, "").trim()}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="secondary"
                onClick={() => draftAnalysis.mutate(current.id)}
                disabled={draftAnalysis.isPending || IS_DEMO || submittedCount === 0}
                title={
                  submittedCount === 0
                    ? `Спершу зберіть свідчення: ${pendingCount} звіт(ів) очікує. ` +
                      "Аналіз без жодного поданого звіту синтезувався б лише з цифр подій."
                    : `LLM-чернетка аналізу на основі ${submittedCount} поданих звітів; ` +
                      "зберігається в кейс"
                }
              >
                <Sparkles size={14} /> Згенерувати аналіз (LLM)
              </button>
              <NextStageButton
                case_={current}
                onTransition={(to) => transition.mutate({ id: current.id, to })}
                disabled={transition.isPending || IS_DEMO}
              />
            </div>
          </div>

          <StageBar status={current.status} />

          <div className="nato-grid">
            <label>
              Що планувалось (What was planned)
              <textarea
                className="form-input"
                rows={2}
                value={value("what_was_planned")}
                onChange={(e) => setDraft({ ...draft, what_was_planned: e.target.value })}
              />
            </label>
            <label>
              Що сталось (What happened)
              <textarea
                className="form-input"
                rows={2}
                value={value("what_happened")}
                onChange={(e) => setDraft({ ...draft, what_happened: e.target.value })}
              />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>
              Чому (Analysis · the "why" — обов'язкове за NATO)
              <textarea
                className="form-input"
                rows={4}
                value={value("analysis")}
                onChange={(e) => setDraft({ ...draft, analysis: e.target.value })}
              />
              {current.analysis_source && (
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  Джерело: {current.analysis_source}
                  {current.analysis_drafted_at &&
                    ` · ${new Date(current.analysis_drafted_at).toLocaleString("uk")}`}
                </span>
              )}
            </label>
            <label>
              Урок (Lesson Identified)
              <textarea
                className="form-input"
                rows={3}
                value={value("lesson_identified")}
                onChange={(e) => setDraft({ ...draft, lesson_identified: e.target.value })}
              />
            </label>
            <label>
              Якість рішення
              <select
                className="form-input"
                value={(draft.decision_quality ?? current.decision_quality) as string}
                onChange={(e) =>
                  setDraft({ ...draft, decision_quality: e.target.value as DecisionQuality })
                }
              >
                {(Object.keys(DECISION_LABELS) as DecisionQuality[]).map((q) => (
                  <option key={q} value={q}>{DECISION_LABELS[q]}</option>
                ))}
              </select>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{DECISION_HINT}</span>
            </label>
            <label>
              Що було відомо на момент рішення
              <textarea
                className="form-input"
                rows={2}
                value={value("decision_rationale")}
                onChange={(e) => setDraft({ ...draft, decision_rationale: e.target.value })}
                placeholder="без цього оцінка — це заднім числом"
              />
            </label>
            <label>
              Відповідальний (OPR · Office of Primary Responsibility)
              <input
                className="form-input"
                value={value("opr")}
                onChange={(e) => setDraft({ ...draft, opr: e.target.value })}
                placeholder="напр.: Технічна служба"
              />
            </label>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button
              onClick={() => patchCase.mutate({ id: current.id, body: draft })}
              disabled={patchCase.isPending || IS_DEMO || Object.keys(draft).length === 0}
            >
              <Save size={14} /> Зберегти
            </button>
            <button
              className="secondary"
              onClick={() => setDraft({})}
              disabled={Object.keys(draft).length === 0}
            >
              Скасувати зміни
            </button>
          </div>

          {IS_DEMO && (
            <p style={{ color: "var(--accent-gold)", fontSize: 12, marginTop: 12 }}>
              ⓘ Demo-режим: збереження і переходи не пишуться у БД.
            </p>
          )}

          <div style={{ borderTop: "1px solid var(--border-muted)", marginTop: 24, paddingTop: 16 }}>
            <div className="card-header">
              <span className="card-title">
                <UserPlus size={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />
                Індивідуальні звіти учасників
              </span>
              <span className="card-badge badge-blue">
                {submittedCount} надано · {pendingCount} очікує
              </span>
            </div>

            <CoverageStrip caseId={current.id} />

            <div
              style={{
                border: "1px solid var(--border-muted)",
                borderRadius: 8,
                padding: 12,
                marginBottom: 16,
              }}
            >
              <ParticipantPicker
                key={current.id}
                caseId={current.id}
                caseOperatorId={current.operator_id}
                onRequested={() => reports.refetch()}
              />
            </div>

            {(reports.data ?? []).length === 0 ? (
              <div className="loading">Звітів немає — розішли запити учасникам.</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Від</th>
                    <th>Функція</th>
                    <th>Що сталось</th>
                    <th>Чому</th>
                    <th>Стан</th>
                  </tr>
                </thead>
                <tbody>
                  {(reports.data ?? []).map((r) => (
                    <ReportRow key={r.id} r={r} />
                  ))}
                </tbody>
              </table>
            )}

            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
              Учасник може подати звіт анонімно — поле «Від» показуватиме «анонімно»,
              але audit-ланцюг збереже originator для адміна (TC 25-20).
            </p>
          </div>

          <RecommendationsSection key={current.id} caseId={current.id} />
        </div>
      )}
    </div>
  );
}
