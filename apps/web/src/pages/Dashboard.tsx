import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import {
  DerivedNote,
  HorizontalBars,
  MetricCard,
  MiniBarChart,
  RatingTable,
  SignalList,
} from "../components/DashboardWidgets";

interface MonthlyRow {
  operator_code: string;
  item_type_code: string;
  launched: number;
  lost: number;
  repaired: number;
  success: number;
  msr: number;
  msr_c: number;
  clr: number;
  delta_msr_pp: number;
}

interface Rating {
  operator_code: string;
  msr_c: number;
  category: string;
  rank: number;
}

interface ZoneSummary {
  zone: string;
  losses: number;
  repairs: number;
  total: number;
  share_of_launched: number;
}

interface Trend {
  operator_code: string;
  msr_prev: number | null;
  msr_this: number;
  trend: string;
}

interface MonthlyReport {
  year: number;
  month: number;
  rows: MonthlyRow[];
  totals: MonthlyRow;
  rating: Rating[];
  zones: ZoneSummary[];
  trends: Trend[];
}

interface AARCase {
  id: number;
  title: string;
  status: string;
  trigger: string;
  opened_at: string;
}

function now() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

// REMOVED: fakeSparkline(). It generated Math.random() noise and drew it as a
// trend line beside real MSR figures. In a defense tool a fabricated trend is
// not decoration — a reader cannot tell it from a measurement. We show a
// sparkline again only when we have an actual per-day series to plot.

export default function Dashboard() {
  const { year, month } = now();

  const monthly = useQuery({
    queryKey: ["monthly", year, month],
    queryFn: () => apiFetch<MonthlyReport>(`/reports/monthly?year=${year}&month=${month}`),
    retry: 1,
  });

  const cases = useQuery({
    queryKey: ["cases-open"],
    queryFn: () => apiFetch<AARCase[]>("/aar/cases?status=open&limit=10"),
    retry: 1,
  });

  const totals = monthly.data?.totals;
  const rating = monthly.data?.rating ?? [];
  const rows = monthly.data?.rows ?? [];
  const zones = monthly.data?.zones ?? [];
  const openCases = cases.data ?? [];

  const msrPct = totals ? (totals.msr * 100).toFixed(1) : "—";
  const msrCPct = totals ? (totals.msr_c * 100).toFixed(1) : "—";
  const clrPct = totals ? (totals.clr * 100).toFixed(1) : "—";

  const operatorItems = rows
    .reduce<Record<string, { launched: number; msr: number; delta: number }>>(
      (acc, r) => {
        const key = r.operator_code;
        if (!acc[key]) acc[key] = { launched: 0, msr: 0, delta: 0 };
        acc[key].launched += r.launched;
        acc[key].msr = r.msr;
        acc[key].delta = r.delta_msr_pp;
        return acc;
      },
      {},
    );

  const barItems = Object.entries(operatorItems)
    .map(([name, d]) => ({
      name,
      value: d.launched,
      pct: d.msr,
      trend: d.delta,
    }))
    .sort((a, b) => b.value - a.value);

  const maxLaunched = Math.max(...barItems.map((b) => b.value), 1);

  const highCount = rating.filter((r) => r.category === "high").length;
  const needsTraining = rating.filter((r) => r.category === "needs_training").length;

  const triggerSignals = openCases.map((c) => ({
    id: c.id,
    title: c.title.replace(/\[.*\]/, "").trim(),
    trigger: c.trigger,
    meta: `Тригер: ${c.trigger} · Відкрито: ${new Date(c.opened_at).toLocaleDateString("uk")}`,
    severity: (c.trigger === "msr_drop" || c.trigger === "enterprise_drop"
      ? "red"
      : c.trigger === "item_anomaly"
        ? "warning"
        : "info") as "red" | "warning" | "info",
  }));

  const zoneBarData = zones
    .filter((z) => z.total > 0)
    .map((z) => ({ name: z.zone, v: z.total }));

  return (
    <div className="dashboard-grid">
      {/* Row 1: Main KPI + Risk signals */}
      <MetricCard
        title="MSR підприємства (η)"
        value={msrPct}
        unit="зі 100"
        badge={totals ? "Стабільність" : "Завантаження..."}
        badgeType={totals && totals.msr >= 0.7 ? "green" : "red"}
        trend={totals?.delta_msr_pp}
        stats={[
          { label: "Запущено", value: totals?.launched ?? "—" },
          { label: "Втрачено", value: totals?.lost ?? "—", color: "var(--accent-red)" },
          { label: "Ремонт", value: totals?.repaired ?? "—", color: "var(--accent-gold)" },
        ]}
      />

      <div className="card">
        <div className="card-header">
          <span className="card-title">Ризик-сигнали</span>
          {openCases.length > 0 && (
            <span className="card-badge badge-red">
              +{openCases.length} активних
            </span>
          )}
        </div>
        <div className="big-number-row">
          <span className="big-number">{openCases.length}</span>
          <span className="big-number-unit">Активних AAR-кейсів</span>
        </div>
        <SignalList signals={triggerSignals.slice(0, 4)} />
      </div>

      {/* Row 2: Operator rating mini + Active types */}
      <MetricCard
        title="Експлуатантів під увагою"
        value={rating.length}
        badge={needsTraining === 0 ? "В межах норми" : `${needsTraining} до підг.`}
        badgeType={needsTraining === 0 ? "green" : "red"}
        stats={[
          { label: "Високий η_c", value: highCount, color: "var(--accent-green)" },
          { label: "До підготовки", value: needsTraining, color: "var(--accent-red)" },
          { label: "Загалом у рейтингу", value: rating.length },
        ]}
      />

      <div className="card">
        <div className="card-header">
          <span className="card-title">Метрики (η_c / λ_c)</span>
          <span className="card-badge badge-blue">
            {year}-{String(month).padStart(2, "0")}
          </span>
        </div>
        <div style={{ display: "flex", gap: 24, marginBottom: 12 }}>
          <div>
            <div className="stat-label">η_c (MSR_c)</div>
            <div className="stat-value" style={{ fontSize: 28, color: "var(--accent-green)" }}>
              {msrCPct}%
            </div>
          </div>
          <div>
            <div className="stat-label">λ_c (CLR)</div>
            <div className="stat-value" style={{ fontSize: 28, color: "var(--accent-red)" }}>
              {clrPct}%
            </div>
          </div>
        </div>
        {zoneBarData.length > 0 && <MiniBarChart data={zoneBarData} color="var(--accent-blue)" />}
        <DerivedNote
          text={
            totals && totals.msr_c > 0.85
              ? `Crew-adjusted MSR (η_c=${msrCPct}%) перевищує поріг високої готовності. Основний внесок у CLR — зона обслуги (${clrPct}%). Рекомендовано зосередити до-підготовку на ${needsTraining} експлуатантах з категорією "needs_training".`
              : "Дані завантажуються або відсутні за поточний місяць. Запустіть seed-скрипт та повторіть."
          }
        />
      </div>

      {/* Row 3: Operator bars + Rating table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Активність по експлуатантах</span>
        </div>
        {barItems.length > 0 ? (
          <HorizontalBars items={barItems} maxValue={maxLaunched} />
        ) : (
          <div className="loading">Немає даних за поточний місяць</div>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Рейтинг експлуатантів за η_c</span>
        </div>
        {rating.length > 0 ? (
          <RatingTable
            rows={rating.map((r) => ({
              rank: r.rank,
              name: r.operator_code,
              msr_c: r.msr_c,
              category: r.category,
            }))}
          />
        ) : (
          <div className="loading">Немає даних</div>
        )}
      </div>
    </div>
  );
}
