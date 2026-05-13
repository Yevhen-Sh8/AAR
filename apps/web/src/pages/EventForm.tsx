import { useEffect, useState } from "react";
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
    await flushQueue();
    await refresh();
  }

  return (
    <section>
      <h2>Подія використання</h2>
      <p>
        Стан мережі: <strong>{online ? "online" : "offline"}</strong>
      </p>
      <form onSubmit={onSubmit}>
        <label>
          Серійний № <input value={serial} onChange={(e) => setSerial(e.target.value)} required />
        </label>{" "}
        <label>
          Тип{" "}
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="A">A</option>
            <option value="B">B</option>
          </select>
        </label>{" "}
        <label>
          Експл.{" "}
          <input value={operator} onChange={(e) => setOperator(e.target.value)} required />
        </label>{" "}
        <label>
          Дата <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>{" "}
        <label>
          Результат{" "}
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as typeof outcome)}
          >
            <option value="success">success</option>
            <option value="lost">lost</option>
            <option value="repair">repair</option>
          </select>
        </label>{" "}
        {outcome !== "success" && (
          <label>
            Причина <input value={reason} onChange={(e) => setReason(e.target.value)} required />
          </label>
        )}{" "}
        <button type="submit" disabled={busy}>
          Подати
        </button>
      </form>

      <h3>Локальна черга ({queue.length})</h3>
      <button onClick={onSync} disabled={busy}>
        Синхронізувати зараз
      </button>
      <ul>
        {queue.map((q) => (
          <li key={q.client_event_id}>
            <code>{q.client_event_id.slice(0, 8)}</code> · {q.status}
            {q.server_id !== null ? ` · server #${q.server_id}` : ""}
            {q.last_error ? ` · err: ${q.last_error}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
