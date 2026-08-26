import { useQuery } from "@tanstack/react-query";
import { Activity, Clock, TrendingUp, AlertTriangle, DollarSign, Users } from "lucide-react";
import { apiFetch } from "../lib/api";
import { METRIC } from "../lib/metrics";

interface LoopKPI {
  time_to_validation_days_median: number | null;
  time_to_validation_days_p90: number | null;
  cases_with_validation: number;
  li_to_ll_conversion_pct: number;
  cases_analysed_or_later: number;
  cases_validated_or_closed: number;
  recurrence_rate_pct: number;
  regressed_recommendations: number;
  validated_recommendations: number;
  open_cases_by_opr: Record<string, number>;
  msr_narrow: number;
  msr_full: number;
  launched_count: number;
  aborted_count: number;
  success_count: number;
  cost_per_effect_usd_by_type: Record<string, number>;
  period_from: string;
  period_to: string;
}

function MetaCard({
  icon,
  title,
  value,
  unit,
  note,
  color = "var(--accent-blue)",
}: {
  icon: React.ReactNode;
  title: string;
  value: string | number;
  unit?: string;
  note?: string;
  color?: string;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {icon} {title}
        </span>
      </div>
      <div className="big-number-row" style={{ alignItems: "baseline" }}>
        <span className="big-number" style={{ color }}>
          {value}
        </span>
        {unit && <span className="big-number-unit">{unit}</span>}
      </div>
      {note && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{note}</div>
      )}
    </div>
  );
}

export default function LearningLoopPage() {
  const kpi = useQuery({
    queryKey: ["loop-kpi"],
    queryFn: () => apiFetch<LoopKPI>("/learning/loop-kpi"),
  });

  if (kpi.isLoading) return <div className="loading">Завантаження…</div>;
  if (kpi.isError || !kpi.data) return <div className="error-msg">Помилка завантаження</div>;

  const d = kpi.data;
  const ttv = d.time_to_validation_days_median;
  const p90 = d.time_to_validation_days_p90;

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Activity size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Цикл навчання — мета-KPI
          </span>
          <span className="card-badge badge-blue">
            {new Date(d.period_from).toLocaleDateString("uk")} —{" "}
            {new Date(d.period_to).toLocaleDateString("uk")}
          </span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6 }}>
          Якщо ці числа не вимірюються — програма Lessons Learned помирає. Це причина №2
          провалу LL-систем у світовій літературі. Дашборд показує, чи цикл живий і чи
          приносить вимірювану користь.
        </p>
      </div>

      <div className="dashboard-grid">
        <MetaCard
          icon={<Clock size={16} />}
          title="Час до підтвердження (медіана)"
          value={ttv === null ? "—" : ttv.toFixed(1)}
          unit="днів"
          note={
            ttv === null
              ? "Жодного підтвердженого кейсу за період"
              : `p90 = ${p90?.toFixed(1) ?? "—"} днів · ${d.cases_with_validation} кейсів`
          }
          color="var(--accent-green)"
        />
        <MetaCard
          icon={<TrendingUp size={16} />}
          title="Конверсія LI → LL"
          value={d.li_to_ll_conversion_pct.toFixed(1)}
          unit="%"
          note={`${d.cases_validated_or_closed} з ${d.cases_analysed_or_later} кейсів дійшли до VALIDATED+`}
          color={d.li_to_ll_conversion_pct >= 50 ? "var(--accent-green)" : "var(--accent-gold)"}
        />
        <MetaCard
          icon={<AlertTriangle size={16} />}
          title="Recurrence rate"
          value={d.recurrence_rate_pct.toFixed(1)}
          unit="%"
          note={`${d.regressed_recommendations} рекомендацій регресувало з ${d.validated_recommendations} валідованих`}
          color={d.recurrence_rate_pct <= 10 ? "var(--accent-green)" : "var(--accent-red)"}
        />
        <MetaCard
          icon={<Users size={16} />}
          title="Активні OPR"
          value={Object.keys(d.open_cases_by_opr).length}
          note={`${Object.values(d.open_cases_by_opr).reduce((a, b) => a + b, 0)} відкритих кейсів`}
        />
      </div>

      <div className="dashboard-grid">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Успішність за двома знаменниками</span>
            <span className="card-badge badge-blue">
              {d.launched_count + d.aborted_count} спроб
            </span>
          </div>
          <div style={{ display: "flex", gap: 24, marginBottom: 12 }}>
            <div>
              <div className="stat-label" title={METRIC.msrNarrow.hint}>
                {METRIC.msrNarrow.label}
              </div>
              <div className="stat-value" style={{ fontSize: 28, color: "var(--accent-green)" }}>
                {(d.msr_narrow * 100).toFixed(1)}%
              </div>
              <div className="stat-sub">успішні ÷ запущені</div>
            </div>
            <div>
              <div className="stat-label" title={METRIC.msrFull.hint}>
                {METRIC.msrFull.label}
              </div>
              <div className="stat-value" style={{ fontSize: 28, color: "var(--accent-gold)" }}>
                {(d.msr_full * 100).toFixed(1)}%
              </div>
              <div className="stat-sub">успішні ÷ (запущені + зриви)</div>
            </div>
          </div>
          <div className="stat-row" style={{ marginTop: 8 }}>
            <div className="stat-item">
              <div className="stat-label">Успіх</div>
              <div className="stat-value">{d.success_count}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Запущено</div>
              <div className="stat-value">{d.launched_count}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Зриви</div>
              <div className="stat-value" style={{ color: "var(--accent-gold)" }}>
                {d.aborted_count}
              </div>
            </div>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
            Зрив = спроба, що не дійшла до запуску (РЕБ-перешкоди, погода, передстартова
            відмова техніки). Літературна норма: без зривів ~43%, зі зривами ~20–30% —
            треба відстежувати обидва, інакше керівництво бачить лише оптимістичну картину.
          </p>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <DollarSign size={16} style={{ verticalAlign: "-3px", marginRight: 4 }} />
              Cost-per-effect (USD)
            </span>
          </div>
          {Object.keys(d.cost_per_effect_usd_by_type).length === 0 ? (
            <div className="loading">
              Не задано ціну виробу. Введи unit_cost_usd у довіднику типів.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Тип</th>
                  <th>USD на 1 успіх</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(d.cost_per_effect_usd_by_type).map(([code, cost]) => (
                  <tr key={code}>
                    <td className="mono">{code}</td>
                    <td>
                      {cost.toLocaleString("uk", {
                        style: "currency",
                        currency: "USD",
                        maximumFractionDigits: 0,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
            Цей показник — центральний для «cheap mass»: 100 дешевих виробів можуть бути
            ефективнішими за 1 преміальний, якщо cost-per-effect нижчий.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Навантаження на OPR (відповідальних)</span>
        </div>
        {Object.keys(d.open_cases_by_opr).length === 0 ? (
          <div className="loading">Жодного відкритого кейсу</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>OPR</th>
                <th>Відкритих кейсів</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(d.open_cases_by_opr)
                .sort((a, b) => b[1] - a[1])
                .map(([opr, count]) => (
                  <tr key={opr}>
                    <td>{opr}</td>
                    <td>
                      <span className={count >= 5 ? "chip chip-error" : "chip"}>{count}</span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
