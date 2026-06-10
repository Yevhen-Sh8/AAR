import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, ArrowRight, Sparkles, Save, UserPlus, EyeOff } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";

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
  what_happened: string | null;
  why: string | null;
  requested_at: string | null;
  submitted_at: string | null;
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

export default function CasesPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<AARCase | null>(null);
  const [draft, setDraft] = useState<Partial<AARCase>>({});
  const [requestUserIds, setRequestUserIds] = useState("");

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

  const requestReports = useMutation({
    mutationFn: (vars: { id: number; user_ids: number[] }) =>
      apiFetch<{ requested_count: number; skipped_existing: number }>(
        `/aar/cases/${vars.id}/request-reports`,
        { method: "POST", body: JSON.stringify({ user_ids: vars.user_ids }) },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case-reports"] });
      setRequestUserIds("");
    },
  });

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
                disabled={draftAnalysis.isPending || IS_DEMO}
                title="LLM-чернетка аналізу зберігається в кейс"
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
                {(reports.data ?? []).filter((r) => r.submitted_at).length} надано ·{" "}
                {(reports.data ?? []).filter((r) => !r.submitted_at).length} очікує
              </span>
            </div>

            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <input
                className="form-input"
                placeholder="user_ids через кому, напр. 1,2,3"
                value={requestUserIds}
                onChange={(e) => setRequestUserIds(e.target.value)}
                style={{ flex: 1 }}
              />
              <button
                onClick={() => {
                  const ids = requestUserIds
                    .split(",")
                    .map((s) => parseInt(s.trim(), 10))
                    .filter((n) => !isNaN(n));
                  if (ids.length > 0) {
                    requestReports.mutate({ id: current.id, user_ids: ids });
                  }
                }}
                disabled={requestReports.isPending || IS_DEMO || !requestUserIds.trim()}
              >
                Розіслати запити
              </button>
            </div>

            {(reports.data ?? []).length === 0 ? (
              <div className="loading">Звітів немає — розішли запити учасникам.</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Від</th>
                    <th>Що сталось</th>
                    <th>Чому</th>
                    <th>Стан</th>
                  </tr>
                </thead>
                <tbody>
                  {(reports.data ?? []).map((r) => (
                    <tr key={r.id}>
                      <td className="mono">{r.id}</td>
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
                      </td>
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
                  ))}
                </tbody>
              </table>
            )}

            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
              Учасник може подати звіт анонімно — поле «Від» показуватиме «анонімно»,
              але audit-ланцюг збереже originator для адміна (TC 25-20).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
