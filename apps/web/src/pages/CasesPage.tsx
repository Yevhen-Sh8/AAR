import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { SignalList } from "../components/DashboardWidgets";

interface AARCase {
  id: number;
  title: string;
  status: string;
  trigger: string;
  operator_id: number | null;
  summary: string | null;
  opened_at: string;
  closed_at: string | null;
}

export default function CasesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["cases-all"],
    queryFn: () => apiFetch<AARCase[]>("/aar/cases?limit=50"),
    retry: 1,
  });

  const openCases = data?.filter((c) => c.status === "open") ?? [];
  const closedCases = data?.filter((c) => c.status === "closed") ?? [];

  return (
    <div className="dashboard-grid">
      <div className="card">
        <div className="card-header">
          <span className="card-title">Відкриті кейси</span>
          <span className="card-badge badge-red">{openCases.length}</span>
        </div>
        {isLoading && <div className="loading">Завантаження...</div>}
        {error && <div className="error-msg">{String(error)}</div>}
        <SignalList
          signals={openCases.map((c) => ({
            id: c.id,
            title: c.title.replace(/\[.*\]/, "").trim(),
            trigger: c.trigger,
            meta: `Тригер: ${c.trigger} · ${new Date(c.opened_at).toLocaleDateString("uk")}`,
            severity: (c.trigger === "msr_drop" || c.trigger === "enterprise_drop"
              ? "red"
              : c.trigger === "item_anomaly"
                ? "warning"
                : "info") as "red" | "warning" | "info",
          }))}
        />
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Закриті кейси</span>
          <span className="card-badge badge-green">{closedCases.length}</span>
        </div>
        <table className="rating-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Назва</th>
              <th>Тригер</th>
              <th>Закрито</th>
            </tr>
          </thead>
          <tbody>
            {closedCases.map((c) => (
              <tr key={c.id}>
                <td style={{ color: "var(--text-muted)" }}>{c.id}</td>
                <td style={{ fontWeight: 500 }}>{c.title.replace(/\[.*\]/, "").trim()}</td>
                <td>
                  <span className="card-badge badge-blue">{c.trigger}</span>
                </td>
                <td style={{ color: "var(--text-secondary)", fontSize: 12 }}>
                  {c.closed_at
                    ? new Date(c.closed_at).toLocaleDateString("uk")
                    : "—"}
                </td>
              </tr>
            ))}
            {closedCases.length === 0 && (
              <tr>
                <td colSpan={4} className="loading">Немає закритих кейсів</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
