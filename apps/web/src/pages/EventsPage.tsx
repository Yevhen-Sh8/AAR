import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { OUTCOME_UK, outcomeBadge, type UsageEventRow } from "../lib/events";

export default function EventsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["events"],
    queryFn: () => apiFetch<UsageEventRow[]>("/events?limit=50"),
    retry: 1,
  });

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Останні події використання</span>
        <span className="card-badge badge-blue">{data?.length ?? 0} записів</span>
      </div>
      {isLoading && <div className="loading">Завантаження...</div>}
      {error && <div className="error-msg">Помилка: {String(error)}</div>}
      {data && (
        <table className="rating-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Дата</th>
              {/* Was «Item» / «Operator» showing row ids — see lib/events.ts. */}
              <th>Серійний №</th>
              <th>Тип</th>
              <th>Експлуатант</th>
              <th>Результат</th>
              <th>Причина</th>
              <th>Примітка</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id}>
                <td style={{ color: "var(--text-muted)" }}>{e.id}</td>
                <td>{e.event_date}</td>
                <td className="mono">{e.item_serial_no}</td>
                <td>{e.item_type_code}</td>
                <td>{e.operator_code}</td>
                <td>
                  <span className={`card-badge ${outcomeBadge(e.outcome)}`}>
                    {OUTCOME_UK[e.outcome]}
                  </span>
                  {e.aborted && (
                    <span className="card-badge badge-gold" style={{ marginLeft: 4 }}>
                      зрив
                    </span>
                  )}
                </td>
                <td className="mono" style={{ fontSize: 12 }}>
                  {e.loss_reason_code ?? e.repair_reason_code ?? "—"}
                </td>
                <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>
                  {e.notes || e.abort_reason || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
