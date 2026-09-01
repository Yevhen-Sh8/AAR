import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Wifi, WifiOff, RefreshCw, RotateCcw, AlertTriangle } from "lucide-react";
import { apiFetch } from "../lib/api";
import { allEvents, requeueEntry, type QueuedEvent } from "../lib/db";
import { flushQueue, retryFailed, submitEvent } from "../lib/sync";

const STATUS_LABELS: Record<QueuedEvent["status"], string> = {
  pending: "у черзі",
  syncing: "надсилається",
  synced: "на сервері",
  failed: "відхилено",
};

type Zone = "operator" | "manufacturer" | "external" | "unknown";

const ZONE_LABELS: Record<Zone, string> = {
  operator: "обслуга",
  manufacturer: "виробник",
  external: "зовнішня",
  unknown: "невідомо",
};

interface DictRow {
  id: number;
  code: string;
  name_uk: string;
  zone?: Zone;
}

const OUTCOME_LABELS = {
  success: "Успіх — завдання виконано",
  lost: "Втрата — безповоротна",
  repair: "Повернення в ремонт",
} as const;

type Outcome = keyof typeof OUTCOME_LABELS;

function useDict(url: string) {
  return useQuery({
    queryKey: ["dict", url],
    queryFn: () => apiFetch<DictRow[]>(url),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * One dictionary-backed picker.
 *
 * The form used to hardcode `A` / `B` for item types and take the operator as
 * free text. Any unit whose real codes were not literally "A" and "E-01" could
 * not file an event at all: the server rejected the code, and (before the queue
 * fix) the event then vanished. A classifier the admin can edit is only useful
 * if the form that writes against it reads it.
 *
 * An empty or unreachable dictionary is stated out loud rather than rendered as
 * an empty dropdown that looks like the operator's own fault.
 */
function DictSelect({
  label, url, value, onChange, required = true, hint,
}: {
  label: string;
  url: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  hint?: string;
}) {
  const q = useDict(url);
  const rows = q.data ?? [];
  return (
    <label>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        disabled={q.isLoading || q.isError || rows.length === 0}
      >
        <option value="">
          {q.isLoading
            ? "завантаження…"
            : q.isError
              ? "довідник недоступний"
              : rows.length === 0
                ? "довідник порожній"
                : "— оберіть —"}
        </option>
        {rows.map((r) => (
          <option key={r.id} value={r.code}>
            {r.code} — {r.name_uk}
            {r.zone ? ` (зона: ${ZONE_LABELS[r.zone]})` : ""}
          </option>
        ))}
      </select>
      {q.isError && (
        <span style={{ fontSize: 11, color: "var(--accent-red)" }}>
          Не вдалося прочитати довідник — подавати подію зараз не можна.
        </span>
      )}
      {!q.isError && !q.isLoading && rows.length === 0 && (
        <span style={{ fontSize: 11, color: "var(--accent-gold)" }}>
          Порожньо. Адміністратор має заповнити його в розділі «Довідники».
        </span>
      )}
      {hint && !q.isError && (
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{hint}</span>
      )}
    </label>
  );
}

export default function EventForm() {
  const [serial, setSerial] = useState("");
  const [type, setType] = useState("");
  const [operator, setOperator] = useState("");
  const [outcome, setOutcome] = useState<Outcome>("success");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [aborted, setAborted] = useState(false);
  const [abortReason, setAbortReason] = useState("");
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
      aborted,
    };
    if (outcome === "lost") payload.loss_reason_code = reason;
    if (outcome === "repair") payload.repair_reason_code = reason;
    if (notes.trim()) payload.notes = notes.trim();
    if (aborted && abortReason.trim()) payload.abort_reason = abortReason.trim();
    await submitEvent(payload);
    // Keep type/operator/date: an operator files a run of events from the same
    // sortie, and re-picking the unit every time is how typos get in.
    setSerial("");
    setReason("");
    setNotes("");
    setAbortReason("");
    setAborted(false);
    await refresh();
    setBusy(false);
  }

  async function onSync() {
    setBusy(true);
    await flushQueue();
    await refresh();
    setBusy(false);
  }

  async function onRetryFailed() {
    setBusy(true);
    await retryFailed();
    await refresh();
    setBusy(false);
  }

  async function onRetryOne(id: string) {
    setBusy(true);
    await requeueEntry(id);
    await flushQueue();
    await refresh();
    setBusy(false);
  }

  const pending = queue.filter((q) => q.status === "pending").length;
  const synced = queue.filter((q) => q.status === "synced").length;
  const failed = queue.filter((q) => q.status === "failed").length;

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
            <DictSelect
              label="Тип виробу"
              url="/dictionaries/item-types"
              value={type}
              onChange={setType}
            />
            <DictSelect
              label="Експлуатант"
              url="/dictionaries/operators"
              value={operator}
              onChange={setOperator}
            />
            <label>
              Дата
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
            <label>
              Результат
              <select value={outcome} onChange={(e) => { setOutcome(e.target.value as Outcome); setReason(""); }}>
                {(Object.keys(OUTCOME_LABELS) as Outcome[]).map((o) => (
                  <option key={o} value={o}>{OUTCOME_LABELS[o]}</option>
                ))}
              </select>
            </label>
            {outcome === "lost" && (
              <DictSelect
                label="Причина втрати"
                url="/dictionaries/loss-reasons"
                value={reason}
                onChange={setReason}
                hint="Зона причини вирішує, чи піде втрата в рахунок обслуги."
              />
            )}
            {outcome === "repair" && (
              <DictSelect
                label="Причина повернення в ремонт"
                url="/dictionaries/repair-reasons"
                value={reason}
                onChange={setReason}
                hint="Зона причини вирішує, чи піде ремонт у рахунок обслуги."
              />
            )}

            <div style={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={aborted}
                  onChange={(e) => setAborted(e.target.checked)}
                />
                Зрив до запуску
              </label>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Спроба не дійшла до запуску (РЕБ, погода, передстартова відмова).
                Без цієї позначки зриви не потрапляють у знаменник «успішності з
                урахуванням зривів» — і картина виглядає кращою, ніж є.
              </span>
            </div>
            {aborted && (
              <label style={{ gridColumn: "1 / -1" }}>
                Причина зриву
                <input
                  value={abortReason}
                  onChange={(e) => setAbortReason(e.target.value)}
                  placeholder="напр. РЕБ на позиції"
                />
              </label>
            )}

            <label style={{ gridColumn: "1 / -1" }}>
              Примітка (не обовʼязково)
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="що варто знати про цю подію"
              />
            </label>
          </div>
          <button type="submit" disabled={busy || !type || !operator}>Подати</button>
        </form>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Локальна черга</span>
          <span className={`card-badge ${failed > 0 ? "badge-red" : "badge-gold"}`}>
            {failed > 0 ? `${failed} відхилено` : `${pending} у черзі`}
          </span>
        </div>
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          <div className="stat-item">
            <div className="stat-label" title="Ще не на сервері. Повторюється автоматично.">
              У черзі
            </div>
            <div className="stat-value" style={{ color: "var(--accent-gold)" }}>{pending}</div>
          </div>
          <div className="stat-item">
            <div className="stat-label">На сервері</div>
            <div className="stat-value" style={{ color: "var(--accent-green)" }}>{synced}</div>
          </div>
          <div className="stat-item">
            <div
              className="stat-label"
              title="Сервер відмовився прийняти ці події. Автоматично вони не підуть — треба виправити причину."
            >
              Відхилено
            </div>
            <div
              className="stat-value"
              style={{ color: failed > 0 ? "var(--accent-red)" : undefined }}
            >
              {failed}
            </div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Усього</div>
            <div className="stat-value">{queue.length}</div>
          </div>
        </div>

        {/* The state that used to be invisible. A rejected event is data the
            operator believes was recorded — say so, out loud. */}
        {failed > 0 && (
          <div
            className="error-msg"
            style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}
          >
            <AlertTriangle size={14} />
            <span style={{ flex: 1 }}>
              {failed} {failed === 1 ? "подію" : "подій"} сервер не прийняв. Вони НЕ
              на сервері й автоматично не повторюються — подивіться причину нижче.
            </span>
            <button className="secondary" onClick={onRetryFailed} disabled={busy}>
              <RotateCcw size={14} /> Повторити всі
            </button>
          </div>
        )}
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
                {STATUS_LABELS[q.status]}
              </span>
              {q.server_id !== null && ` · #${q.server_id}`}
              {q.attempts > 1 && ` · спроб: ${q.attempts}`}
              {q.last_error && <span style={{ color: "var(--accent-red)" }}> · {q.last_error}</span>}
              {q.status === "failed" && (
                <button
                  className="secondary"
                  style={{ marginLeft: 8, padding: "1px 8px", fontSize: 11 }}
                  onClick={() => void onRetryOne(q.client_event_id)}
                  disabled={busy}
                >
                  Повторити
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
