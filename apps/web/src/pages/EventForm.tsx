import { useEffect, useState } from "react";
import { Wifi, WifiOff, RefreshCw } from "lucide-react";
import { allEvents, type QueuedEvent } from "../lib/db";
import { flushQueue, submitEvent } from "../lib/sync";

export default function EventForm() {
  const [serial, setSerial] = useState("");
  const [type, setType] = useState("A");
  const [operator, setOperator] = useState("E-01");
  const [outcome, setOutcome] = useState<"success" | "lost" | "repair">("success");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState("");
  const [queue, setQueue] = useState<QueuedEvent[]>([]);
  const [online, setOnline] = useState(navigator.onLine);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setQueue(await allEvents());
  }

  useEffect(() => {
    void refresh();
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const payload: Record<string, unknown> = {
      item_serial_no: serial,
      item_type_code: type,
      operator_code: operator,
      event_date: date,
      outcome,
    };
    if (outcome === "lost") payload.loss_reason_code = reason;
    if (outcome === "repair") payload.repair_reason_code = reason;
    await submitEvent(payload);
    setSerial("");
    setReason("");
    await refresh();
    setBusy(false);
  }

  async function onSync() {
    setBusy(true);
    await flushQueue();
    await refresh();
    setBusy(false);
  }

  const pending = queue.filter((q) => q.status === "pending").length;
  const synced = queue.filter((q) => q.status === "synced").length;

  return (
    <div className="dashboard-grid">
      <div className="card">
        <div className="card-header">
          <span className="card-title">Подати подію</span>
          <span className={`card-badge ${online ? "badge-green" : "badge-red"}`}>
            {online ? <><Wifi size={12} /> Online</> : <><WifiOff size={12} /> Offline</>}
          </span>
        </div>
        <form onSubmit={onSubmit}>
          <div className="form-grid">
            <label>
              Серійний №
              <input value={serial} onChange={(e) => setSerial(e.target.value)} required placeholder="A-00001" />
            </label>
            <label>
              Тип виробу
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="A">A</option>
                <option value="B">B</option>
              </select>
            </label>
            <label>
              Експлуатант
              <input value={operator} onChange={(e) => setOperator(e.target.value)} required placeholder="E-01" />
            </label>
            <label>
              Дата
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
            <label>
              Результат
              <select value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)}>
                <option value="success">Success</option>
                <option value="lost">Lost</option>
                <option value="repair">Repair</option>
              </select>
            </label>
            {outcome !== "success" && (
              <label>
                Код причини
                <input value={reason} onChange={(e) => setReason(e.target.value)} required placeholder="a" />
              </label>
            )}
          </div>
          <button type="submit" disabled={busy}>Подати</button>
        </form>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Локальна черга</span>
          <span className="card-badge badge-gold">{pending} pending</span>
        </div>
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          <div className="stat-item">
            <div className="stat-label">Pending</div>
            <div className="stat-value" style={{ color: "var(--accent-gold)" }}>{pending}</div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Synced</div>
            <div className="stat-value" style={{ color: "var(--accent-green)" }}>{synced}</div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Total</div>
            <div className="stat-value">{queue.length}</div>
          </div>
        </div>
        <button className="secondary" onClick={onSync} disabled={busy} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <RefreshCw size={14} /> Синхронізувати зараз
        </button>
        <div style={{ marginTop: 12, maxHeight: 300, overflow: "auto" }}>
          {queue.slice(-10).reverse().map((q) => (
            <div
              key={q.client_event_id}
              style={{
                padding: "6px 0",
                borderBottom: "1px solid var(--border-muted)",
                fontSize: 12,
                color: "var(--text-secondary)",
              }}
            >
              <code>{q.client_event_id.slice(0, 8)}</code>
              {" · "}
              <span className={`card-badge ${
                q.status === "synced" ? "badge-green" : q.status === "pending" ? "badge-gold" : "badge-red"
              }`}>
                {q.status}
              </span>
              {q.server_id !== null && ` · #${q.server_id}`}
              {q.last_error && <span style={{ color: "var(--accent-red)" }}> · {q.last_error}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
