import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, ScrollText } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";
import { downloadFile } from "../lib/download";
import { OUTCOME_UK, type UsageEventRow } from "../lib/events";

/**
 * Order #440 forms.
 *
 * The generators have existed on the API since the mod440 service landed, and
 * «Налаштування» listed them as a shipped feature — but nothing in the UI ever
 * linked to them. Reaching an inventory sheet or a write-off act meant hand-
 * crafting a request. A form nobody can press is not a delivered feature.
 */

const UNIT_KEY = "aar.mod440.unit_name";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthStartISO(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

/** One labelled text input. */
function Field({
  label, value, onChange, placeholder, type = "text", hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  hint?: string;
}) {
  return (
    <label>
      {label}
      <input
        className="form-input"
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {hint && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{hint}</span>}
    </label>
  );
}

/** Picks the event an act is written about. Serial number first — that is what identifies it. */
function EventPicker({
  outcome, value, onChange,
}: {
  outcome: "lost" | "repair";
  value: string;
  onChange: (v: string) => void;
}) {
  const q = useQuery({
    queryKey: ["events", "for-act", outcome],
    queryFn: () => apiFetch<UsageEventRow[]>(`/events?outcome=${outcome}&limit=200`),
  });
  // The act generator refuses an event with no reason code (400), so an entry
  // that cannot produce a document is not offered as if it could.
  const rows = (q.data ?? []).filter((e) =>
    outcome === "lost" ? e.loss_reason_code : e.repair_reason_code,
  );

  return (
    <label>
      Подія
      <select
        className="form-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={q.isLoading || q.isError || rows.length === 0}
      >
        <option value="">
          {q.isLoading
            ? "завантаження…"
            : q.isError
              ? "не вдалося прочитати події"
              : rows.length === 0
                ? `немає подій «${OUTCOME_UK[outcome]}» з причиною`
                : "— оберіть подію —"}
        </option>
        {rows.map((e) => (
          <option key={e.id} value={String(e.id)}>
            {e.event_date} · {e.item_serial_no} ({e.item_type_code}) · {e.operator_code} ·
            причина {outcome === "lost" ? e.loss_reason_code : e.repair_reason_code}
          </option>
        ))}
      </select>
      {q.isError && (
        <span style={{ fontSize: 11, color: "var(--accent-red)" }}>
          Список подій недоступний — акт сформувати не можна.
        </span>
      )}
      {!q.isError && !q.isLoading && rows.length === 0 && (
        <span style={{ fontSize: 11, color: "var(--accent-gold)" }}>
          Акт формується лише за подією з проставленою причиною.
        </span>
      )}
    </label>
  );
}

export default function Mod440Page() {
  const [unit, setUnit] = useState("в/ч");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // The unit name is the same on every form; retyping it each time is how two
  // documents from one unit end up with two different unit names.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(UNIT_KEY);
      if (saved) setUnit(saved);
    } catch {
      /* private mode — fall back to the default */
    }
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(UNIT_KEY, unit);
    } catch {
      /* ignore */
    }
  }, [unit]);

  const [asOf, setAsOf] = useState(todayISO());
  const [from, setFrom] = useState(monthStartISO());
  const [to, setTo] = useState(todayISO());

  const [lossEvent, setLossEvent] = useState("");
  const [lossActNo, setLossActNo] = useState("");
  const [responsible, setResponsible] = useState("");
  const [circumstances, setCircumstances] = useState("");

  const [repairEvent, setRepairEvent] = useState("");
  const [repairActNo, setRepairActNo] = useState("");
  const [sender, setSender] = useState("");
  const [receiver, setReceiver] = useState("");
  const [defect, setDefect] = useState("");

  async function grab(key: string, path: string, filename: string) {
    setBusy(key);
    setError(null);
    const res = await downloadFile(path, filename);
    if (!res.ok) setError(res.error);
    setBusy(null);
  }

  const u = encodeURIComponent(unit);
  // The API substitutes its own placeholder when a field is left blank, so an
  // empty box means "leave a blank to fill in by hand", not a broken request.
  const opt = (name: string, v: string) => (v.trim() ? `&${name}=${encodeURIComponent(v.trim())}` : "");

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <ScrollText size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Форми за наказом Міноборони № 440
          </span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 0 }}>
          Документи формуються з уже поданих подій — нічого вводити повторно не
          треба. Порожні поля друкуються як пропуски для заповнення від руки.
        </p>
        <div className="form-grid">
          <Field
            label="Найменування військової частини"
            value={unit}
            onChange={setUnit}
            placeholder="в/ч А0000"
            hint="Підставляється в усі форми нижче й запамʼятовується."
          />
        </div>
        {error && <div className="error-msg" style={{ marginTop: 12 }}>{error}</div>}
        {IS_DEMO && (
          <p style={{ color: "var(--accent-gold)", fontSize: 12, marginTop: 12 }}>
            Demo-режим: файли не формуються — бекенду тут немає.
          </p>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <FileText size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Відомість наявності
          </span>
        </div>
        <div className="form-grid">
          <Field label="Станом на" type="date" value={asOf} onChange={setAsOf} />
        </div>
        <button
          className="secondary"
          disabled={busy !== null || IS_DEMO}
          onClick={() =>
            void grab(
              "inventory",
              `/exports/mod440/inventory.xlsx?unit_name=${u}&as_of=${asOf}`,
              `inventory-${asOf}.xlsx`,
            )
          }
        >
          <Download size={14} /> {busy === "inventory" ? "Формується…" : "XLSX"}
        </button>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <FileText size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Журнал руху
          </span>
        </div>
        <div className="form-grid">
          <Field label="Період з" type="date" value={from} onChange={setFrom} />
          <Field label="по" type="date" value={to} onChange={setTo} />
        </div>
        <button
          className="secondary"
          disabled={busy !== null || IS_DEMO || from > to}
          onClick={() =>
            void grab(
              "movement",
              `/exports/mod440/movement.xlsx?unit_name=${u}&date_from=${from}&date_to=${to}`,
              `movement-${from}_${to}.xlsx`,
            )
          }
        >
          <Download size={14} /> {busy === "movement" ? "Формується…" : "XLSX"}
        </button>
        {from > to && (
          <span style={{ fontSize: 11, color: "var(--accent-red)", marginLeft: 8 }}>
            Початок періоду пізніший за кінець.
          </span>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Акт списання (втрата)</span>
        </div>
        <div className="form-grid">
          <EventPicker outcome="lost" value={lossEvent} onChange={setLossEvent} />
          <Field
            label="№ акта"
            value={lossActNo}
            onChange={setLossActNo}
            placeholder="авто"
            hint="Порожньо — номер складеться з id події та року."
          />
          <Field
            label="Відповідальна особа"
            value={responsible}
            onChange={setResponsible}
            placeholder="ПІБ"
          />
          <label style={{ gridColumn: "1 / -1" }}>
            Обставини
            <textarea
              className="form-input"
              rows={2}
              value={circumstances}
              onChange={(e) => setCircumstances(e.target.value)}
              placeholder="за яких обставин сталася втрата"
            />
          </label>
        </div>
        <button
          className="secondary"
          disabled={busy !== null || IS_DEMO || !lossEvent}
          onClick={() =>
            void grab(
              "loss",
              `/exports/mod440/loss-act/${lossEvent}.docx?unit_name=${u}` +
                opt("act_no", lossActNo) +
                opt("responsible_person", responsible) +
                opt("circumstances", circumstances),
              `loss-act-${lossEvent}.docx`,
            )
          }
        >
          <Download size={14} /> {busy === "loss" ? "Формується…" : "DOCX"}
        </button>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Акт передачі в ремонт</span>
        </div>
        <div className="form-grid">
          <EventPicker outcome="repair" value={repairEvent} onChange={setRepairEvent} />
          <Field
            label="№ акта"
            value={repairActNo}
            onChange={setRepairActNo}
            placeholder="авто"
          />
          <Field label="Здавальник" value={sender} onChange={setSender} placeholder="ПІБ" />
          <Field label="Приймальник" value={receiver} onChange={setReceiver} placeholder="ПІБ" />
          <label style={{ gridColumn: "1 / -1" }}>
            Опис дефекту
            <textarea
              className="form-input"
              rows={2}
              value={defect}
              onChange={(e) => setDefect(e.target.value)}
            />
          </label>
        </div>
        <button
          className="secondary"
          disabled={busy !== null || IS_DEMO || !repairEvent}
          onClick={() =>
            void grab(
              "repair",
              `/exports/mod440/repair-act/${repairEvent}.docx?unit_name=${u}` +
                opt("act_no", repairActNo) +
                opt("sender", sender) +
                opt("receiver", receiver) +
                opt("defect_description", defect),
              `repair-act-${repairEvent}.docx`,
            )
          }
        >
          <Download size={14} /> {busy === "repair" ? "Формується…" : "DOCX"}
        </button>
      </div>
    </div>
  );
}
