import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { apiFetch } from "../lib/api";

interface DictRow {
  id?: number;
  code: string;
  name?: string;
  zone?: string;
}

function Section({
  title,
  url,
  showZone = false,
}: {
  title: string;
  url: string;
  showZone?: boolean;
}) {
  const q = useQuery({
    queryKey: ["dict", url],
    queryFn: () => apiFetch<DictRow[]>(url),
  });

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{title}</span>
        <span className="card-badge badge-blue">{q.data?.length ?? "—"} записів</span>
      </div>
      {q.isLoading && <div className="loading">Завантаження…</div>}
      {q.isError && <div className="error-msg">Помилка</div>}
      {q.data && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Код</th>
              <th>Назва</th>
              {showZone && <th>Зона</th>}
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.code}>
                <td className="mono">{r.code}</td>
                <td>{r.name ?? "—"}</td>
                {showZone && <td>{r.zone ?? "—"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function DictionariesPage() {
  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <BookOpen size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Довідники системи
          </span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          Базові класифікатори, що використовуються у формах і звітності. Редагування довідників
          доступне через CLI / адмін-API; UI для CRUD заплановано в Stage 12.
        </p>
      </div>

      <Section title="Типи виробів" url="/dictionaries/item-types" />
      <Section title="Експлуатанти" url="/dictionaries/operators" />
      <Section title="Причини втрат (а–д)" url="/dictionaries/loss-reasons" showZone />
      <Section title="Причини повернень у ремонт (а–р)" url="/dictionaries/repair-reasons" showZone />
    </div>
  );
}
