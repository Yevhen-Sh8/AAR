import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { apiFetch, IS_DEMO } from "../lib/api";

type Zone = "operator" | "manufacturer" | "external" | "unknown";

const ZONE_LABELS: Record<Zone, string> = {
  operator: "експлуатант",
  manufacturer: "виробник",
  external: "зовнішня",
  unknown: "невідомо",
};

interface DictRow {
  id: number;
  code: string;
  name_uk: string;
  zone?: Zone;
  unit_cost_usd?: string | null;
}

interface FieldSpec {
  hasZone: boolean;
  hasCost: boolean;
}

const SECTIONS: { title: string; url: string; spec: FieldSpec }[] = [
  { title: "Типи виробів", url: "/dictionaries/item-types", spec: { hasZone: false, hasCost: true } },
  { title: "Експлуатанти", url: "/dictionaries/operators", spec: { hasZone: false, hasCost: false } },
  { title: "Причини втрат (а–д)", url: "/dictionaries/loss-reasons", spec: { hasZone: true, hasCost: false } },
  { title: "Причини повернень у ремонт (а–р)", url: "/dictionaries/repair-reasons", spec: { hasZone: true, hasCost: false } },
];

// apiFetch throws Error("API 409: ...detail..."); pull a human message out.
function errMessage(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/"detail":"([^"]+)"/);
  if (m) return m[1];
  if (raw.includes("409")) return "Конфлікт: код уже існує або запис використовується.";
  return "Помилка. Спробуйте ще раз.";
}

function DictSection({ title, url, spec }: { title: string; url: string; spec: FieldSpec }) {
  const qc = useQueryClient();
  const key = ["dict", url];
  const q = useQuery({ queryKey: key, queryFn: () => apiFetch<DictRow[]>(url) });

  const [addCode, setAddCode] = useState("");
  const [addName, setAddName] = useState("");
  const [addZone, setAddZone] = useState<Zone>("operator");
  const [addCost, setAddCost] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editZone, setEditZone] = useState<Zone>("operator");
  const [editCost, setEditCost] = useState("");
  const [err, setErr] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const create = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { code: addCode.trim(), name_uk: addName.trim() };
      if (spec.hasZone) body.zone = addZone;
      if (spec.hasCost) body.unit_cost_usd = addCost.trim() ? addCost.trim() : null;
      return apiFetch<DictRow>(url, { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: () => {
      invalidate();
      setAddCode(""); setAddName(""); setAddCost(""); setAddZone("operator"); setErr("");
    },
    onError: (e) => setErr(errMessage(e)),
  });

  const update = useMutation({
    mutationFn: (id: number) => {
      const body: Record<string, unknown> = { name_uk: editName.trim() };
      if (spec.hasZone) body.zone = editZone;
      if (spec.hasCost) body.unit_cost_usd = editCost.trim() ? editCost.trim() : null;
      return apiFetch<DictRow>(`${url}/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    },
    onSuccess: () => { invalidate(); setEditId(null); setErr(""); },
    onError: (e) => setErr(errMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiFetch<{ deleted: number }>(`${url}/${id}`, { method: "DELETE" }),
    onSuccess: () => { invalidate(); setErr(""); },
    onError: (e) => setErr(errMessage(e)),
  });

  function startEdit(r: DictRow) {
    setEditId(r.id);
    setEditName(r.name_uk);
    setEditZone(r.zone ?? "operator");
    setEditCost(r.unit_cost_usd ?? "");
    setErr("");
  }

  const cols = 2 + (spec.hasZone ? 1 : 0) + (spec.hasCost ? 1 : 0) + 1;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{title}</span>
        <span className="card-badge badge-blue">{q.data?.length ?? "—"} записів</span>
      </div>

      {err && <div className="error-msg" style={{ marginBottom: 10 }}>{err}</div>}
      {q.isLoading && <div className="loading">Завантаження…</div>}
      {q.isError && <div className="error-msg">Помилка завантаження</div>}

      {q.data && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Код</th>
              <th>Назва</th>
              {spec.hasZone && <th>Зона</th>}
              {spec.hasCost && <th>Вартість, USD</th>}
              <th style={{ width: 90, textAlign: "right" }}>Дії</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) =>
              editId === r.id ? (
                <tr key={r.id}>
                  <td className="mono">{r.code}</td>
                  <td>
                    <input className="form-input" value={editName}
                      onChange={(e) => setEditName(e.target.value)} />
                  </td>
                  {spec.hasZone && (
                    <td>
                      <select className="form-input" value={editZone}
                        onChange={(e) => setEditZone(e.target.value as Zone)}>
                        {Object.entries(ZONE_LABELS).map(([v, l]) => (
                          <option key={v} value={v}>{l}</option>
                        ))}
                      </select>
                    </td>
                  )}
                  {spec.hasCost && (
                    <td>
                      <input className="form-input" value={editCost} inputMode="decimal"
                        placeholder="—" onChange={(e) => setEditCost(e.target.value)} />
                    </td>
                  )}
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="icon-btn" title="Зберегти"
                      disabled={update.isPending || !editName.trim()}
                      onClick={() => update.mutate(r.id)}><Check size={16} /></button>
                    <button className="icon-btn" title="Скасувати"
                      onClick={() => { setEditId(null); setErr(""); }}><X size={16} /></button>
                  </td>
                </tr>
              ) : (
                <tr key={r.id}>
                  <td className="mono">{r.code}</td>
                  <td>{r.name_uk}</td>
                  {spec.hasZone && <td>{r.zone ? ZONE_LABELS[r.zone] : "—"}</td>}
                  {spec.hasCost && <td>{r.unit_cost_usd ?? "—"}</td>}
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="icon-btn" title="Редагувати" disabled={IS_DEMO}
                      onClick={() => startEdit(r)}><Pencil size={15} /></button>
                    <button className="icon-btn" title="Видалити" disabled={IS_DEMO || remove.isPending}
                      onClick={() => {
                        if (confirm(`Видалити «${r.code}»?`)) remove.mutate(r.id);
                      }}><Trash2 size={15} /></button>
                  </td>
                </tr>
              ),
            )}
            {/* add row */}
            <tr>
              <td>
                <input className="form-input" value={addCode} placeholder="код"
                  disabled={IS_DEMO} onChange={(e) => setAddCode(e.target.value)} />
              </td>
              <td>
                <input className="form-input" value={addName} placeholder="назва"
                  disabled={IS_DEMO} onChange={(e) => setAddName(e.target.value)} />
              </td>
              {spec.hasZone && (
                <td>
                  <select className="form-input" value={addZone} disabled={IS_DEMO}
                    onChange={(e) => setAddZone(e.target.value as Zone)}>
                    {Object.entries(ZONE_LABELS).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </td>
              )}
              {spec.hasCost && (
                <td>
                  <input className="form-input" value={addCost} placeholder="—" inputMode="decimal"
                    disabled={IS_DEMO} onChange={(e) => setAddCost(e.target.value)} />
                </td>
              )}
              <td style={{ textAlign: "right" }}>
                <button className="icon-btn" title="Додати"
                  disabled={IS_DEMO || create.isPending || !addCode.trim() || !addName.trim()}
                  onClick={() => create.mutate()}><Plus size={16} /></button>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr><td colSpan={cols} style={{ height: 0, padding: 0 }} /></tr>
          </tfoot>
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
          Базові класифікатори форм і звітності. Додавання/редагування/видалення —
          для адміністратора. Код запису незмінний після створення (редагуйте назву,
          зону чи вартість). Видалення заборонено, поки код використовується у подіях
          або кейсах.{IS_DEMO && " У режимі демо редагування вимкнено."}
        </p>
      </div>

      {SECTIONS.map((s) => (
        <DictSection key={s.url} title={s.title} url={s.url} spec={s.spec} />
      ))}
    </div>
  );
}
