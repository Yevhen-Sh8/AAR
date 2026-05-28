import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

interface UsageEvent {
  id: number;
  client_event_id: string | null;
  item_id: number;
  operator_id: number;
  event_date: string;
  outcome: string;
  loss_reason_id: number | null;
  repair_reason_id: number | null;
  notes: string | null;
  recorded_at: string;
}

export default function EventsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["events"],
    queryFn: () => apiFetch<UsageEvent[]>("/events?limit=50"),
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
              <th>Item</th>
              <th>Operator</th>
              <th>Outcome</th>
              <th>Примітка</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id}>
                <td style={{ color: "var(--text-muted)" }}>{e.id}</td>
                <td>{e.event_date}</td>
                <td>#{e.item_id}</td>
                <td>#{e.operator_id}</td>
                <td>
                  <span
                    className={`card-badge ${
                      e.outcome === "success"
                        ? "badge-green"
                        : e.outcome === "lost"
                          ? "badge-red"
                          : "badge-gold"
                    }`}
                  >
                    {e.outcome}
                  </span>
                </td>
                <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>
                  {e.notes || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
