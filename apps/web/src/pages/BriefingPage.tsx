import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Printer, Search } from "lucide-react";
import { apiFetch } from "../lib/api";

interface ProfileStats {
  window_days: number;
  launched: number;
  success: number;
  lost: number;
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

function Section({ title, items, accent }: {
  title: string;
  items: BriefItem[];
  accent: string;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{title}</span>
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
  const [params, setParams] = useState<string | null>(null);

  const brief = useQuery({
    queryKey: ["mission-brief", params],
    queryFn: () => apiFetch<MissionBrief>(`/briefing/mission?${params}`),
    enabled: params !== null,
  });

  function build() {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    if (itemType) p.set("item_type_code", itemType);
    if (operator.trim()) p.set("operator_code", operator.trim());
    setParams(p.toString());
  }

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
            <button className="secondary" onClick={() => window.print()}>
              <Printer size={14} /> Друк
            </button>
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
              <option value="A">A</option>
              <option value="B">B</option>
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
                <div className="stat-label">η (MSR)</div>
                <div className="stat-value" style={{ color: "var(--accent-green)" }}>{msrPct}%</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Запущено</div>
                <div className="stat-value">{d.stats.launched}</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Втрачено</div>
                <div className="stat-value" style={{ color: "var(--accent-red)" }}>{d.stats.lost}</div>
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

          <Section
            title="⚠ Активні сигнали (врахуй до вильоту)"
            items={d.signals}
            accent="var(--accent-gold)"
          />
          <Section
            title="✓ Валідовані уроки з бази досвіду"
            items={d.validated_lessons}
            accent="var(--accent-green)"
          />
          <Section
            title="Уроки з завершених AAR-кейсів"
            items={d.case_lessons}
            accent="var(--accent-blue)"
          />
          <Section
            title="Відкриті рекомендації (ще не впроваджено)"
            items={d.open_recommendations}
            accent="var(--accent-red)"
          />
        </>
      )}
    </div>
  );
}
