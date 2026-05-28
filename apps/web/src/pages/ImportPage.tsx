import { useState } from "react";
import { Upload, FileCheck, AlertCircle, FileText } from "lucide-react";

interface ImportRowError {
  row: number;
  message: string;
}

interface ImportSummary {
  total_rows: number;
  parsed: number;
  imported: number;
  duplicates: number;
  failed: number;
  parse_errors: ImportRowError[];
  persist_errors: ImportRowError[];
  dry_run: boolean;
}

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch(`/api/events/import?dry_run=${dryRun}`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
      setSummary(await resp.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dashboard-grid">
      <div className="card span-full">
        <div className="card-header">
          <span className="card-title">Імпорт подій з CSV / XLSX</span>
        </div>

        <div
          style={{
            border: "2px dashed var(--border)",
            borderRadius: 12,
            padding: 32,
            textAlign: "center",
            background: file ? "var(--accent-green-muted)" : "var(--bg-input)",
            transition: "background 0.2s",
          }}
        >
          <Upload size={32} style={{ color: "var(--text-secondary)" }} />
          <p style={{ margin: "8px 0", color: "var(--text-secondary)" }}>
            Оберіть CSV або XLSX-файл з подіями
          </p>
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setSummary(null);
              setError(null);
            }}
            style={{ marginTop: 8 }}
          />
          {file && (
            <p style={{ marginTop: 12, fontSize: 13 }}>
              <FileText size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
              <strong>{file.name}</strong>{" "}
              <span style={{ color: "var(--text-muted)" }}>
                ({(file.size / 1024).toFixed(1)} KB)
              </span>
            </p>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button onClick={() => submit(true)} disabled={!file || busy} className="secondary">
            Перевірити (dry-run)
          </button>
          <button onClick={() => submit(false)} disabled={!file || busy}>
            Імпортувати
          </button>
        </div>

        <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-muted)" }}>
          Обов'язкові колонки: <code>item_serial_no</code>, <code>item_type_code</code>,{" "}
          <code>operator_code</code>, <code>event_date</code>, <code>outcome</code>.
          Опційні: <code>loss_reason_code</code>, <code>repair_reason_code</code>,{" "}
          <code>notes</code>, <code>client_event_id</code>.
        </div>
      </div>

      {error && (
        <div className="card span-full">
          <div className="error-msg">
            <AlertCircle size={16} style={{ verticalAlign: "middle", marginRight: 6 }} />
            {error}
          </div>
        </div>
      )}

      {summary && (
        <>
          <div className="card">
            <div className="card-header">
              <span className="card-title">Результат</span>
              {summary.dry_run && (
                <span className="card-badge badge-blue">Dry-run</span>
              )}
            </div>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
              <div>
                <div className="stat-label">Усього рядків</div>
                <div className="stat-value">{summary.total_rows}</div>
              </div>
              <div>
                <div className="stat-label">Розпарсено</div>
                <div className="stat-value">{summary.parsed}</div>
              </div>
              <div>
                <div className="stat-label">Імпортовано</div>
                <div className="stat-value" style={{ color: "var(--accent-green)" }}>
                  <FileCheck size={18} style={{ verticalAlign: "middle", marginRight: 4 }} />
                  {summary.imported}
                </div>
              </div>
              <div>
                <div className="stat-label">Дублікати</div>
                <div className="stat-value" style={{ color: "var(--accent-gold)" }}>
                  {summary.duplicates}
                </div>
              </div>
              <div>
                <div className="stat-label">Помилки</div>
                <div className="stat-value" style={{ color: "var(--accent-red)" }}>
                  {summary.failed}
                </div>
              </div>
            </div>
          </div>

          {(summary.parse_errors.length > 0 || summary.persist_errors.length > 0) && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">Помилки по рядках</span>
                <span className="card-badge badge-red">
                  {summary.parse_errors.length + summary.persist_errors.length}
                </span>
              </div>
              <table className="rating-table">
                <thead>
                  <tr>
                    <th>Рядок</th>
                    <th>Стадія</th>
                    <th>Повідомлення</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.parse_errors.map((e, i) => (
                    <tr key={`p-${i}`}>
                      <td style={{ fontWeight: 600 }}>{e.row}</td>
                      <td>
                        <span className="card-badge badge-gold">Парсинг</span>
                      </td>
                      <td style={{ color: "var(--text-secondary)" }}>{e.message}</td>
                    </tr>
                  ))}
                  {summary.persist_errors.map((e, i) => (
                    <tr key={`x-${i}`}>
                      <td style={{ fontWeight: 600 }}>{e.row}</td>
                      <td>
                        <span className="card-badge badge-red">Збереження</span>
                      </td>
                      <td style={{ color: "var(--text-secondary)" }}>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
