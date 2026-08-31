import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileBarChart, Download, Calendar } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";
import { downloadFile } from "../lib/download";
import { METRIC, RATING_THRESHOLD_HINT } from "../lib/metrics";

interface DailyRow {
  operator_code: string;
  item_type_code: string;
  launched: number;
  lost: number;
  repaired: number;
  success: number;
}

interface DailyReport {
  report_date: string;
  rows: DailyRow[];
  totals: { launched: number; lost: number; repaired: number; success: number; msr: number };
}

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
}

interface MonthlyReport {
  year: number;
  month: number;
  rows: MonthlyRow[];
  totals: MonthlyRow;
  rating: { operator_code: string; msr_c: number; category: string; rank: number }[];
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function currentMonth(): { y: number; m: number } {
  const d = new Date();
  return { y: d.getFullYear(), m: d.getMonth() + 1 };
}


export default function ReportsPage() {
  const [tab, setTab] = useState<"daily" | "monthly">("monthly");
  const [date, setDate] = useState(today());
  const { y, m } = currentMonth();
  const [year, setYear] = useState(y);
  const [month, setMonth] = useState(m);

  const daily = useQuery({
    queryKey: ["daily", date],
    queryFn: () => apiFetch<DailyReport>(`/reports/daily?date=${date}`),
    enabled: tab === "daily",
  });

  const monthly = useQuery({
    queryKey: ["monthly-page", year, month],
    queryFn: () => apiFetch<MonthlyReport>(`/reports/monthly?year=${year}&month=${month}`),
    enabled: tab === "monthly",
  });

  const ym = `${year}-${String(month).padStart(2, "0")}`;

  // A link cannot carry a bearer token, so downloads go through fetch and a
  // blob. Failures are shown here rather than swallowed — a report that did
  // not download must not look like one that did.
  const [dlBusy, setDlBusy] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);

  async function grab(path: string, filename: string) {
    setDlBusy(filename);
    setDlError(null);
    const res = await downloadFile(path, filename);
    if (!res.ok) setDlError(res.error);
    setDlBusy(null);
  }

  function DownloadButton({ path, filename, label }: {
    path: string; filename: string; label: string;
  }) {
    return (
      <button
        className="btn-link"
        onClick={() => void grab(path, filename)}
        disabled={dlBusy !== null}
      >
        <Download size={14} /> {dlBusy === filename ? "…" : label}
      </button>
    );
  }

  return (
    <div className="page-stack">
      <div className="tabs">
        <button
          className={tab === "monthly" ? "tab tab-active" : "tab"}
          onClick={() => setTab("monthly")}
        >
          Місячний звіт
        </button>
        <button
          className={tab === "daily" ? "tab tab-active" : "tab"}
          onClick={() => setTab("daily")}
        >
          Щоденна довідка
        </button>
      </div>

      {tab === "monthly" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <FileBarChart size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
              Місячна звітність — {ym}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="form-input"
                type="number"
                min="2000"
                max="2100"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                style={{ width: 100 }}
              />
              <select
                className="form-input"
                value={month}
                onChange={(e) => setMonth(Number(e.target.value))}
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((mo) => (
                  <option key={mo} value={mo}>{String(mo).padStart(2, "0")}</option>
                ))}
              </select>
              <DownloadButton
                path={`/reports/monthly.xlsx?year=${year}&month=${month}`}
                filename={`aar-monthly-${ym}.xlsx`}
                label="XLSX"
              />
              <DownloadButton
                path={`/reports/monthly.pdf?year=${year}&month=${month}`}
                filename={`aar-monthly-${ym}.pdf`}
                label="PDF"
              />
            </div>
          </div>
          {dlError && <div className="error-msg">{dlError}</div>}

          {monthly.isLoading && <div className="loading">Завантаження…</div>}
          {monthly.isError && <div className="error-msg">Помилка завантаження</div>}

          {monthly.data && (
            <>
              <div className="stat-row" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
                <div className="stat-item">
                  <div className="stat-label">Запущено</div>
                  <div className="stat-value">{monthly.data.totals.launched}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Успішно</div>
                  <div className="stat-value" style={{ color: "var(--accent-green)" }}>
                    {monthly.data.totals.success}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Втрачено</div>
                  <div className="stat-value" style={{ color: "var(--accent-red)" }}>
                    {monthly.data.totals.lost}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label" title={METRIC.msr.hint}>{METRIC.msr.label}</div>
                  <div className="stat-value">
                    {(monthly.data.totals.msr * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label" title={METRIC.msrC.hint}>{METRIC.msrC.label}</div>
                  <div className="stat-value" style={{ color: "var(--accent-green)" }}>
                    {(monthly.data.totals.msr_c * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              <h3 style={{ margin: "20px 0 12px", fontSize: 14, color: "var(--text-secondary)" }}>
                Розклад за експлуатантом і типом виробу
              </h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Експлуатант</th>
                    <th>Тип</th>
                    <th>Запущено</th>
                    <th>Успішно</th>
                    <th>Втрачено</th>
                    <th>Ремонт</th>
                    <th title={METRIC.msr.hint}>{METRIC.msr.short}</th>
                    <th title={METRIC.msrC.hint}>{METRIC.msrC.short}</th>
                    <th title={METRIC.clr.hint}>{METRIC.clr.short}</th>
                  </tr>
                </thead>
                <tbody>
                  {monthly.data.rows.map((r, i) => (
                    <tr key={i}>
                      <td className="mono">{r.operator_code}</td>
                      <td>{r.item_type_code}</td>
                      <td>{r.launched}</td>
                      <td style={{ color: "var(--accent-green)" }}>{r.success}</td>
                      <td style={{ color: "var(--accent-red)" }}>{r.lost}</td>
                      <td style={{ color: "var(--accent-gold)" }}>{r.repaired}</td>
                      <td>{(r.msr * 100).toFixed(1)}%</td>
                      <td>{(r.msr_c * 100).toFixed(1)}%</td>
                      <td>{(r.clr * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <h3 style={{ margin: "20px 0 12px", fontSize: 14, color: "var(--text-secondary)" }}>
                Рейтинг експлуатантів за успішністю обслуги
              </h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ранг</th>
                    <th>Експлуатант</th>
                    <th title={METRIC.msrC.hint}>{METRIC.msrC.short}</th>
                    <th title={RATING_THRESHOLD_HINT}>Категорія</th>
                  </tr>
                </thead>
                <tbody>
                  {monthly.data.rating.map((r) => (
                    <tr key={r.operator_code}>
                      <td>
                        <span className={`rating-rank rank-${r.rank <= 3 ? r.rank : "n"}`}>
                          {r.rank}
                        </span>
                      </td>
                      <td className="mono">{r.operator_code}</td>
                      <td>{(r.msr_c * 100).toFixed(1)}%</td>
                      <td>
                        <span className={`chip chip-${r.category}`}>{r.category}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {tab === "daily" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <Calendar size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
              Щоденна довідка — {date}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="form-input"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
              <DownloadButton
                path={`/reports/daily.xlsx?date=${date}`}
                filename={`aar-daily-${date}.xlsx`}
                label="XLSX"
              />
              <DownloadButton
                path={`/reports/daily.pdf?date=${date}`}
                filename={`aar-daily-${date}.pdf`}
                label="PDF"
              />
            </div>
          </div>
          {dlError && <div className="error-msg">{dlError}</div>}

          {daily.isLoading && <div className="loading">Завантаження…</div>}
          {daily.isError && <div className="error-msg">Помилка завантаження</div>}

          {daily.data && (
            <>
              <div className="stat-row" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
                <div className="stat-item">
                  <div className="stat-label">Запущено</div>
                  <div className="stat-value">{daily.data.totals.launched}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Успішно</div>
                  <div className="stat-value" style={{ color: "var(--accent-green)" }}>
                    {daily.data.totals.success}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Втрачено</div>
                  <div className="stat-value" style={{ color: "var(--accent-red)" }}>
                    {daily.data.totals.lost}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Ремонт</div>
                  <div className="stat-value" style={{ color: "var(--accent-gold)" }}>
                    {daily.data.totals.repaired}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label" title={METRIC.msr.hint}>{METRIC.msr.label}</div>
                  <div className="stat-value">
                    {(daily.data.totals.msr * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              <h3 style={{ margin: "20px 0 12px", fontSize: 14, color: "var(--text-secondary)" }}>
                Розклад
              </h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Експлуатант</th>
                    <th>Тип виробу</th>
                    <th>Запущено</th>
                    <th>Успіх</th>
                    <th>Втрата</th>
                    <th>Ремонт</th>
                  </tr>
                </thead>
                <tbody>
                  {daily.data.rows.map((r, i) => (
                    <tr key={i}>
                      <td className="mono">{r.operator_code}</td>
                      <td>{r.item_type_code}</td>
                      <td>{r.launched}</td>
                      <td style={{ color: "var(--accent-green)" }}>{r.success}</td>
                      <td style={{ color: "var(--accent-red)" }}>{r.lost}</td>
                      <td style={{ color: "var(--accent-gold)" }}>{r.repaired}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {IS_DEMO && (
        <div className="card" style={{ background: "var(--accent-gold-muted)" }}>
          <p style={{ color: "var(--accent-gold)", fontSize: 13 }}>
            ⓘ Demo-режим: вивантаження XLSX/PDF недоступне — бекенду, який
            формує файли, тут немає. У робочому контурі працює.
          </p>
        </div>
      )}
    </div>
  );
}
