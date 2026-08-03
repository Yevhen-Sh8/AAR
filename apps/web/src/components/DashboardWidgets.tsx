import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface MetricCardProps {
  title: string;
  value: number | string;
  unit?: string;
  badge?: string;
  badgeType?: "green" | "red" | "gold" | "blue";
  trend?: number;
  sparkData?: { v: number }[];
  stats?: { label: string; value: string | number; sub?: string; color?: string }[];
}

export function MetricCard({
  title, value, unit, badge, badgeType = "green", trend, sparkData, stats,
}: MetricCardProps) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{title}</span>
        {badge && <span className={`card-badge badge-${badgeType}`}>{badge}</span>}
      </div>
      <div className="big-number-row">
        <span className="big-number">{value}</span>
        {unit && <span className="big-number-unit">{unit}</span>}
        {trend !== undefined && <TrendBadge value={trend} />}
      </div>
      {sparkData && sparkData.length > 0 && (
        <div className="sparkline-wrap">
          <ResponsiveContainer width="100%" height={40}>
            <AreaChart data={sparkData}>
              <defs>
                <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent-green)" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="var(--accent-green)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone" dataKey="v" stroke="var(--accent-green)"
                fill="url(#sparkGrad)" strokeWidth={2} dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      {stats && (
        <div className="stat-row">
          {stats.map((s) => (
            <div className="stat-item" key={s.label}>
              <div className="stat-label">{s.label}</div>
              <div className="stat-value" style={s.color ? { color: s.color } : undefined}>
                {s.value}
              </div>
              {s.sub && <div className="stat-sub">{s.sub}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TrendBadge({ value }: { value: number }) {
  if (value > 0)
    return <span className="trend trend-up"><TrendingUp size={14} /> +{value.toFixed(1)}</span>;
  if (value < 0)
    return <span className="trend trend-down"><TrendingDown size={14} /> {value.toFixed(1)}</span>;
  return <span className="trend trend-flat"><Minus size={14} /> 0</span>;
}

interface BarItem {
  name: string;
  value: number;
  pct: number;
  trend?: number;
}

export function HorizontalBars({ items, maxValue }: { items: BarItem[]; maxValue: number }) {
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div className="bar-row" key={item.name}>
          <span className="bar-name">{item.name}</span>
          <span className="bar-pct">{(item.pct * 100).toFixed(1)}%</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${(item.value / maxValue) * 100}%` }}
            />
          </div>
          <span className="bar-value">{item.value}</span>
          <span className="bar-trend">
            {item.trend !== undefined && <TrendBadge value={item.trend} />}
          </span>
        </div>
      ))}
    </div>
  );
}

interface RatingRow {
  rank: number;
  name: string;
  msr_c: number;
  category: string;
  sparkData?: { v: number }[];
}

export function RatingTable({ rows }: { rows: RatingRow[] }) {
  return (
    <table className="rating-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Експлуатант</th>
          <th>Spark</th>
          <th>η_c</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name}>
            <td>
              <div className={`rating-rank ${r.rank <= 3 ? `rank-${r.rank}` : ""}`}>{r.rank}</div>
            </td>
            <td style={{ fontWeight: 500 }}>{r.name}</td>
            <td style={{ width: 80 }}>
              {r.sparkData && (
                <ResponsiveContainer width={70} height={24}>
                  <AreaChart data={r.sparkData}>
                    <Area
                      type="monotone" dataKey="v" stroke="var(--accent-green)"
                      fill="none" strokeWidth={1.5} dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </td>
            <td style={{ fontWeight: 700 }}>{(r.msr_c * 100).toFixed(0)}</td>
            <td>
              <span className={`card-badge badge-${
                r.category === "high" ? "green" : r.category === "ok" ? "gold" : "red"
              }`}>
                {r.category === "high" ? "Високий" : r.category === "ok" ? "Стабільно" : "До підг."}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface Signal {
  id: number;
  title: string;
  trigger: string;
  meta: string;
  severity: "red" | "warning" | "info";
}

export function SignalList({ signals }: { signals: Signal[] }) {
  return (
    <div className="signal-list">
      {signals.map((s) => (
        <div className={`signal-item ${s.severity}`} key={s.id}>
          <div className="signal-title">{s.title}</div>
          <div className="signal-meta">{s.meta}</div>
        </div>
      ))}
      {signals.length === 0 && (
        <div className="loading">Немає активних сигналів</div>
      )}
    </div>
  );
}

/**
 * A sentence COMPUTED from the figures already on this screen.
 *
 * Was `AIInsight`, labelled «Кореляційний інсайт» and stamped with a hardcoded
 * «Довіра 0.84». Both were untrue: no model produced the text (it is a
 * template over msr_c / clr / needs_training) and no confidence was ever
 * calculated. A fabricated certainty score standing beside real MSR numbers
 * costs the reader's trust in every genuine figure on the page — and it
 * contradicts our own posture that AI never asserts and humans validate
 * (ADR-008). Real LLM output lives on the mission brief, where it carries
 * evidence and is labelled as a draft.
 */
export function DerivedNote({ text }: { text: string }) {
  return (
    <div className="ai-insight">
      <div className="ai-insight-header">
        <span>Σ</span>
        Розраховано з показників вище
      </div>
      <p>{text}</p>
    </div>
  );
}

export function MiniBarChart({
  data, dataKey = "v", color = "var(--accent-green)",
}: { data: { name: string; v: number }[]; dataKey?: string; color?: string }) {
  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={data} barSize={8}>
        <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
        <YAxis hide />
        <Tooltip
          contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8 }}
          labelStyle={{ color: "var(--text-secondary)" }}
        />
        <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
