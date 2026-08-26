import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  FolderKanban,
  ListChecks,
  Printer,
  Search,
  Sparkles,
} from "lucide-react";
import { METRIC } from "../lib/metrics";
import { apiFetch, IS_DEMO } from "../lib/api";

interface ProfileStats {
  window_days: number;
  launched: number;
  success: number;
  lost: number;
  lost_during_abort: number;
  repaired: number;
  aborted: number;
  msr: number;
  top_loss_reasons: string[];
}

interface BriefItem {
  id: number;
  title: string;
  detail: string | null;
  meta: string;
  relevance: number;
}

interface MissionBrief {
  query: string;
  item_type_code: string | null;
  operator_code: string | null;
  stats: ProfileStats;
  signals: BriefItem[];
  validated_lessons: BriefItem[];
  case_lessons: BriefItem[];
  open_recommendations: BriefItem[];
}

interface ItemTypeRow {
  code: string;
  name_uk?: string;
}

interface SynthRisk {
  risk: string;
  evidence: string;
  mitigation: string;
}

interface MissionSynthesis {
  headline: string;
  key_risks: SynthRisk[];
  precautions: string[];
  confidence_note: string;
}

function Section({ title, icon, items, accent }: {
  title: string;
  icon: React.ReactNode;
  items: BriefItem[];
  accent: string;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {icon} {title}
        </span>
        <span className="card-badge badge-blue">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <div className="loading">Нічого релевантного не знайдено</div>
      ) : (
        <div className="signal-cards">
          {items.map((it) => (
            <div
              key={it.id}
              className="signal-review-card"
              style={{ borderLeft: `3px solid ${accent}` }}
            >
              <div style={{ fontWeight: 500 }}>{it.title}</div>
              {it.detail && (
                <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
                  {it.detail}
                </div>
              )}
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                {it.meta}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BriefingPage() {
  const [q, setQ] = useState("");
  const [itemType, setItemType] = useState("");
  const [operator, setOperator] = useState("");
  // In demo mode auto-run one fetch on mount so the static showcase has
  // content immediately, matching sibling demo pages; live mode waits for
  // the planner to enter a profile first.
  const [params, setParams] = useState<string | null>(IS_DEMO ? "" : null);

  const itemTypes = useQuery({
    queryKey: ["dict", "/dictionaries/item-types"],
    queryFn: () => apiFetch<ItemTypeRow[]>("/dictionaries/item-types"),
  });

  const brief = useQuery({
    queryKey: ["mission-brief", params],
    queryFn: () => apiFetch<MissionBrief>(`/briefing/mission?${params}`),
    enabled: params !== null,
  });

  // LLM synthesis is triggered explicitly (it costs tokens/latency); enabled
  // only once the planner asks for it, keyed by the same profile params.
  const [synthOn, setSynthOn] = useState(false);
  const synth = useQuery({
    queryKey: ["mission-synth", params],
    queryFn: () => apiFetch<MissionSynthesis>(`/briefing/mission/synthesis?${params}`),
    enabled: synthOn && params !== null,
    retry: false,
  });

  function build() {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    if (itemType) p.set("item_type_code", itemType);
    if (operator.trim()) p.set("operator_code", operator.trim());
    setSynthOn(false);
    setParams(p.toString());
  }

  const synthError =
    synth.error instanceof Error && synth.error.message.includes("503")
      ? "ШІ вимкнено на сервері (AAR_LLM_ENABLED). Синтез недоступний."
      : synth.isError
        ? "Не вдалося сформувати синтез."
        : null;

  const d = brief.data;
  const msrPct = d ? (d.stats.msr * 100).toFixed(1) : "—";

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <ClipboardList size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Брифінг підготовки місії
          </span>
          {d && (
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => setSynthOn(true)}
                disabled={synth.isFetching}
              >
                <Sparkles size={14} />{" "}
                {synth.isFetching ? "ШІ синтезує…" : "Синтез ШІ"}
              </button>
              <button className="secondary" onClick={() => window.print()}>
                <Printer size={14} /> Друк
              </button>
            </div>
          )}
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16 }}>
          Задай профіль завдання — система збере все, що організація вже знає:
          активні попередження, валідовані уроки, невпроваджені рекомендації та
          об'єктивну статистику виробів. AAR стає входом у планування, а не
          звітом після.
        </p>
        <div className="form-grid">
          <label style={{ gridColumn: "1 / -1" }}>
            Профіль завдання (ключові слова)
            <input
              className="form-input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="напр.: нічний виліт сектор Б"
              onKeyDown={(e) => e.key === "Enter" && build()}
            />
          </label>
          <label>
            Тип виробу
            <select
              className="form-input"
              value={itemType}
              onChange={(e) => setItemType(e.target.value)}
            >
              <option value="">Будь-який</option>
              {(itemTypes.data ?? []).map((it) => (
                <option key={it.code} value={it.code}>
                  {it.code}
                  {it.name_uk ? ` — ${it.name_uk}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            Експлуатант
            <input
              className="form-input"
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              placeholder="E-01 (необов'язково)"
            />
          </label>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button onClick={build} disabled={brief.isFetching}>
              <Search size={14} />{" "}
              {brief.isFetching ? "Збираємо…" : "Сформувати брифінг"}
            </button>
          </div>
        </div>
      </div>

      {brief.isError && (
        <div className="card"><div className="error-msg">Помилка формування брифінгу</div></div>
      )}

      {d && (
        <>
          <div className="card">
            <div className="card-header">
              <span className="card-title">
                Статистика профілю (останні {d.stats.window_days} днів)
              </span>
              <span className="card-badge badge-gold">
                {d.item_type_code ? `тип ${d.item_type_code}` : "усі типи"}
                {d.operator_code ? ` · ${d.operator_code}` : ""}
              </span>
            </div>
            <div className="stat-row" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
              <div className="stat-item">
                <div className="stat-label" title={METRIC.msr.hint}>{METRIC.msr.label}</div>
                <div className="stat-value" style={{ color: "var(--accent-green)" }}>{msrPct}%</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Запущено</div>
                <div className="stat-value">{d.stats.launched}</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Втрачено</div>
                <div className="stat-value" style={{ color: "var(--accent-red)" }}>
                  {d.stats.lost}
                  {d.stats.lost_during_abort > 0 && (
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {" "}(+{d.stats.lost_during_abort} під час абортів)
                    </span>
                  )}
                </div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Ремонт</div>
                <div className="stat-value" style={{ color: "var(--accent-gold)" }}>{d.stats.repaired}</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Аборти</div>
                <div className="stat-value">{d.stats.aborted}</div>
              </div>
            </div>
            {d.stats.top_loss_reasons.length > 0 && (
              <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 12 }}>
                Топ-причини втрат за профілем:{" "}
                <span className="mono">{d.stats.top_loss_reasons.join(", ")}</span>
              </p>
            )}
          </div>

          {(synthOn || synth.data) && (
            <div className="card" style={{ borderColor: "var(--accent-purple)" }}>
              <div className="card-header">
                <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Sparkles size={15} style={{ color: "var(--accent-purple)" }} />
                  Синтез ШІ — тезовий брифінг
                </span>
              </div>
              {synth.isFetching && <div className="loading">ШІ формує брифінг…</div>}
              {synthError && <div className="error-msg">{synthError}</div>}
              {synth.data && (
                <>
                  <p style={{ fontSize: 15, fontWeight: 500, marginBottom: 14 }}>
                    {synth.data.headline}
                  </p>

                  {synth.data.key_risks.length > 0 && (
                    <>
                      <div className="synth-subhead">Ключові ризики</div>
                      <div className="signal-cards" style={{ marginBottom: 14 }}>
                        {synth.data.key_risks.map((r, i) => (
                          <div
                            key={i}
                            className="signal-review-card"
                            style={{ borderLeft: "3px solid var(--accent-red)" }}
                          >
                            <div style={{ fontWeight: 500 }}>{r.risk}</div>
                            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                              Підстава: {r.evidence}
                            </div>
                            <div style={{ fontSize: 13, color: "var(--accent-green)", marginTop: 4 }}>
                              → {r.mitigation}
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}

                  {synth.data.precautions.length > 0 && (
                    <>
                      <div className="synth-subhead">Застереження до вильоту</div>
                      <ul className="synth-list">
                        {synth.data.precautions.map((p, i) => (
                          <li key={i}>{p}</li>
                        ))}
                      </ul>
                    </>
                  )}

                  {synth.data.confidence_note && (
                    <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
                      ⓘ {synth.data.confidence_note}
                    </p>
                  )}
                  <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
                    Згенеровано ШІ на основі пакета підготовки — перевір перед рішенням.
                  </p>
                </>
              )}
            </div>
          )}

          <Section
            title="Активні сигнали (врахуй до вильоту)"
            icon={<AlertTriangle size={15} style={{ color: "var(--accent-gold)" }} />}
            items={d.signals}
            accent="var(--accent-gold)"
          />
          <Section
            title="Валідовані уроки з бази досвіду"
            icon={<CheckCircle2 size={15} style={{ color: "var(--accent-green)" }} />}
            items={d.validated_lessons}
            accent="var(--accent-green)"
          />
          <Section
            title="Уроки з завершених AAR-кейсів"
            icon={<FolderKanban size={15} style={{ color: "var(--accent-blue)" }} />}
            items={d.case_lessons}
            accent="var(--accent-blue)"
          />
          <Section
            title="Відкриті рекомендації (ще не впроваджено)"
            icon={<ListChecks size={15} style={{ color: "var(--accent-red)" }} />}
            items={d.open_recommendations}
            accent="var(--accent-red)"
          />
        </>
      )}
    </div>
  );
}
