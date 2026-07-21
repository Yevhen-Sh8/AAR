import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plug, Trash2, RefreshCw, PlusCircle } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";

interface Subscription {
  id: number;
  name: string;
  kind: string;
  target_url: string;
  events: string[];
  active: boolean;
  created_at: string;
}

interface Delivery {
  id: number;
  subscription_id: number;
  event_kind: string;
  status: string;
  status_code: number | null;
  attempt: number;
  error: string | null;
  dispatched_at: string;
}

interface ConnectorsInfo {
  kinds: string[];
  events: string[];
  excluded: string[];
  notes: Record<string, string>;
}

const EMPTY_FORM = {
  name: "",
  kind: "generic",
  target_url: "",
  secret: "",
  events: ["usage_event_created"] as string[],
  active: true,
};

export default function IntegrationsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const subs = useQuery({
    queryKey: ["integrations-subs"],
    queryFn: () => apiFetch<Subscription[]>("/integrations/subscriptions"),
  });

  const deliveries = useQuery({
    queryKey: ["integrations-deliveries"],
    queryFn: () => apiFetch<Delivery[]>("/integrations/deliveries?limit=50"),
  });

  const connectors = useQuery({
    queryKey: ["integrations-connectors"],
    queryFn: () => apiFetch<ConnectorsInfo>("/integrations/connectors"),
  });

  const create = useMutation({
    mutationFn: (body: typeof EMPTY_FORM) =>
      apiFetch<Subscription>("/integrations/subscriptions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations-subs"] });
      setShowForm(false);
      setForm(EMPTY_FORM);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/integrations/subscriptions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations-subs"] }),
  });

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Plug size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Підписки на webhook
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="secondary" onClick={() => subs.refetch()}>
              <RefreshCw size={14} /> Оновити
            </button>
            <button onClick={() => setShowForm(!showForm)} disabled={IS_DEMO}>
              <PlusCircle size={14} /> {showForm ? "Скасувати" : "Нова підписка"}
            </button>
          </div>
        </div>

        {showForm && (
          <div className="form-grid" style={{ marginBottom: 16 }}>
            <label>
              Назва
              <input
                className="form-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="prod-delta"
              />
            </label>
            <label>
              Тип конектора
              <select
                className="form-input"
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
              >
                {connectors.data?.kinds.map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </label>
            <label style={{ gridColumn: "1 / -1" }}>
              {form.kind === "telegram" ? "Chat ID (куди слати)" : "Target URL"}
              <input
                className="form-input"
                value={form.target_url}
                onChange={(e) => setForm({ ...form, target_url: e.target.value })}
                placeholder={
                  form.kind === "telegram"
                    ? "-1001234567890 або @channel"
                    : "https://partner.example.com/hooks/aar"
                }
              />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>
              {form.kind === "telegram" ? "Токен бота" : "HMAC secret"}
              <input
                className="form-input"
                type="password"
                value={form.secret}
                onChange={(e) => setForm({ ...form, secret: e.target.value })}
                placeholder={
                  form.kind === "telegram"
                    ? "123456:AA... (від @BotFather)"
                    : "використовується для X-AAR-Signature"
                }
              />
            </label>
            {form.kind === "telegram" && (
              <p style={{ gridColumn: "1 / -1", fontSize: 12, color: "var(--text-muted)", marginTop: -6 }}>
                ⓘ Створіть бота через @BotFather, додайте його в чат/канал, а
                chat_id отримайте (напр. через @getidsbot). Токен зберігається
                як secret і не потрапляє в журнал доставок.
              </p>
            )}
            <div style={{ gridColumn: "1 / -1" }}>
              <button
                onClick={() => create.mutate(form)}
                disabled={create.isPending || !form.name || !form.target_url}
              >
                {create.isPending ? "Створюємо…" : "Створити підписку"}
              </button>
            </div>
          </div>
        )}

        {subs.isLoading && <div className="loading">Завантаження…</div>}
        {subs.data && subs.data.length === 0 && (
          <div className="loading">Підписок ще немає — створіть першу.</div>
        )}

        {subs.data && subs.data.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Назва</th>
                <th>Тип</th>
                <th>URL</th>
                <th>Події</th>
                <th>Стан</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {subs.data.map((s) => (
                <tr key={s.id}>
                  <td className="mono">{s.id}</td>
                  <td>{s.name}</td>
                  <td><span className="chip">{s.kind}</span></td>
                  <td className="mono" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {s.target_url}
                  </td>
                  <td>{s.events.join(", ")}</td>
                  <td>
                    <span className={s.active ? "chip chip-active" : "chip"}>
                      {s.active ? "active" : "off"}
                    </span>
                  </td>
                  <td>
                    <button
                      className="icon-btn"
                      onClick={() => remove.mutate(s.id)}
                      disabled={IS_DEMO}
                      title="Видалити"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Доступні конектори</span>
        </div>
        {connectors.data && (
          <div className="connector-grid">
            {connectors.data.kinds.map((k) => (
              <div key={k} className="connector-card">
                <div className="connector-name">{k}</div>
                <div className="connector-note">{connectors.data!.notes[k] ?? "—"}</div>
              </div>
            ))}
            {connectors.data.excluded.map((k) => (
              <div key={k} className="connector-card connector-excluded">
                <div className="connector-name">{k} (виключено)</div>
                <div className="connector-note">Таємна система — не інтегрується.</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Останні відправки (delivery log)</span>
          <button className="secondary" onClick={() => deliveries.refetch()}>
            <RefreshCw size={14} /> Оновити
          </button>
        </div>
        {deliveries.isLoading && <div className="loading">Завантаження…</div>}
        {deliveries.data && deliveries.data.length === 0 && (
          <div className="loading">Жодної відправки.</div>
        )}
        {deliveries.data && deliveries.data.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Sub</th>
                <th>Подія</th>
                <th>Стан</th>
                <th>HTTP</th>
                <th>Спроба</th>
                <th>Час</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.data.map((d) => (
                <tr key={d.id}>
                  <td className="mono">{d.id}</td>
                  <td className="mono">{d.subscription_id}</td>
                  <td>{d.event_kind}</td>
                  <td>
                    <span className={d.status === "success" ? "chip chip-active" : "chip chip-error"}>
                      {d.status}
                    </span>
                  </td>
                  <td className="mono">{d.status_code ?? "—"}</td>
                  <td>{d.attempt}</td>
                  <td>{new Date(d.dispatched_at).toLocaleString("uk")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
