import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Map as MapIcon, Search } from "lucide-react";
import { apiFetch } from "../lib/api";

interface Feature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    id: number;
    serial_no: string;
    operator_code: string;
    item_type_code: string;
    outcome: "success" | "lost" | "repair";
    event_date: string;
  };
}

interface FeatureCollection {
  type: string;
  features: Feature[];
  count: number;
}

interface ItemTypeRow { code: string; name_uk?: string }

const W = 1000;
const H = 640;
const PAD = 60;

const OUTCOME_COLOR: Record<Feature["properties"]["outcome"], string> = {
  success: "var(--accent-green)",
  lost: "var(--accent-red)",
  repair: "var(--accent-gold)",
};
const OUTCOME_LABEL: Record<string, string> = {
  success: "Успіх",
  lost: "Втрата",
  repair: "Ремонт",
};

function niceTicks(min: number, max: number, n = 5): number[] {
  if (max <= min) return [min];
  const step = (max - min) / n;
  return Array.from({ length: n + 1 }, (_, i) => min + i * step);
}

export default function MapPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [outcome, setOutcome] = useState("");
  const [operator, setOperator] = useState("");
  const [itemType, setItemType] = useState("");
  const [params, setParams] = useState("");
  const [selected, setSelected] = useState<Feature | null>(null);

  const itemTypes = useQuery({
    queryKey: ["dict", "/dictionaries/item-types"],
    queryFn: () => apiFetch<ItemTypeRow[]>("/dictionaries/item-types"),
  });

  const geo = useQuery({
    queryKey: ["events-geojson", params],
    queryFn: () => apiFetch<FeatureCollection>(`/events/geojson?${params}`),
  });

  function build() {
    const p = new URLSearchParams();
    if (dateFrom) p.set("date_from", dateFrom);
    if (dateTo) p.set("date_to", dateTo);
    if (outcome) p.set("outcome", outcome);
    if (operator.trim()) p.set("operator_code", operator.trim());
    if (itemType) p.set("item_type_code", itemType);
    setSelected(null);
    setParams(p.toString());
  }

  const features = geo.data?.features ?? [];

  const { project, bbox } = useMemo(() => {
    if (features.length === 0) return { project: null as null | ((c: [number, number]) => [number, number]), bbox: null };
    let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
    for (const f of features) {
      const [lon, lat] = f.geometry.coordinates;
      minLon = Math.min(minLon, lon); maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
    }
    // avoid zero-span
    if (maxLon - minLon < 1e-6) { minLon -= 0.05; maxLon += 0.05; }
    if (maxLat - minLat < 1e-6) { minLat -= 0.05; maxLat += 0.05; }
    const spanLon = maxLon - minLon, spanLat = maxLat - minLat;
    const proj = ([lon, lat]: [number, number]): [number, number] => [
      PAD + ((lon - minLon) / spanLon) * (W - 2 * PAD),
      PAD + ((maxLat - lat) / spanLat) * (H - 2 * PAD),
    ];
    return { project: proj, bbox: { minLon, maxLon, minLat, maxLat } };
  }, [features]);

  const counts = useMemo(() => {
    const c = { success: 0, lost: 0, repair: 0 };
    for (const f of features) c[f.properties.outcome] += 1;
    return c;
  }, [features]);

  return (
    <div className="page-stack">
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <MapIcon size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            Геокарта подій
          </span>
          <span className="card-badge badge-blue">{geo.data?.count ?? 0} точок</span>
        </div>
        <div className="form-grid">
          <label>
            Дата від
            <input className="form-input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            Дата до
            <input className="form-input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label>
            Результат
            <select className="form-input" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
              <option value="">Будь-який</option>
              <option value="success">Успіх</option>
              <option value="lost">Втрата</option>
              <option value="repair">Ремонт</option>
            </select>
          </label>
          <label>
            Тип виробу
            <select className="form-input" value={itemType} onChange={(e) => setItemType(e.target.value)}>
              <option value="">Будь-який</option>
              {(itemTypes.data ?? []).map((it) => (
                <option key={it.code} value={it.code}>{it.code}</option>
              ))}
            </select>
          </label>
          <label>
            Експлуатант
            <input className="form-input" value={operator} onChange={(e) => setOperator(e.target.value)} placeholder="E-01" />
          </label>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button onClick={build} disabled={geo.isFetching}>
              <Search size={14} /> {geo.isFetching ? "Завантаження…" : "Показати"}
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Тактичний плот</span>
          <div style={{ display: "flex", gap: 14, fontSize: 12 }}>
            <span><span className="map-dot" style={{ background: "var(--accent-green)" }} /> Успіх ({counts.success})</span>
            <span><span className="map-dot" style={{ background: "var(--accent-red)" }} /> Втрата ({counts.lost})</span>
            <span><span className="map-dot" style={{ background: "var(--accent-gold)" }} /> Ремонт ({counts.repair})</span>
          </div>
        </div>

        {geo.isError && <div className="error-msg">Помилка завантаження геоданих</div>}
        {!geo.isFetching && features.length === 0 && (
          <div className="loading">
            Немає геоприв'язаних подій за фільтрами. Координати зʼявляються, коли
            подія має поле <code>location</code> (GeoJSON Point) — напр. при вході
            через інтеграції.
          </div>
        )}

        {project && bbox && features.length > 0 && (
          <div className="map-wrap">
            <svg viewBox={`0 0 ${W} ${H}`} className="map-svg" role="img" aria-label="Геокарта подій">
              <rect x={0} y={0} width={W} height={H} fill="var(--bg-input)" />
              {/* graticule */}
              {niceTicks(bbox.minLon, bbox.maxLon).map((lon, i) => {
                const [x] = project([lon, bbox.minLat]);
                return (
                  <g key={`v${i}`}>
                    <line x1={x} y1={PAD} x2={x} y2={H - PAD} stroke="var(--border-muted)" strokeWidth={1} />
                    <text x={x} y={H - PAD + 16} fontSize={10} fill="var(--text-muted)" textAnchor="middle">
                      {lon.toFixed(2)}°
                    </text>
                  </g>
                );
              })}
              {niceTicks(bbox.minLat, bbox.maxLat).map((lat, i) => {
                const [, y] = project([bbox.minLon, lat]);
                return (
                  <g key={`h${i}`}>
                    <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="var(--border-muted)" strokeWidth={1} />
                    <text x={PAD - 8} y={y + 3} fontSize={10} fill="var(--text-muted)" textAnchor="end">
                      {lat.toFixed(2)}°
                    </text>
                  </g>
                );
              })}
              {/* points */}
              {features.map((f) => {
                const [cx, cy] = project(f.geometry.coordinates);
                const color = OUTCOME_COLOR[f.properties.outcome];
                const isSel = selected?.properties.id === f.properties.id;
                return (
                  <circle
                    key={f.properties.id}
                    cx={cx}
                    cy={cy}
                    r={isSel ? 7 : f.properties.outcome === "lost" ? 5.5 : 4.5}
                    fill={color}
                    fillOpacity={0.85}
                    stroke={isSel ? "var(--text-primary)" : color}
                    strokeWidth={isSel ? 2 : 0.5}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelected(f)}
                  >
                    <title>
                      {`${f.properties.serial_no} · ${OUTCOME_LABEL[f.properties.outcome]} · ${f.properties.operator_code} · ${f.properties.event_date}`}
                    </title>
                  </circle>
                );
              })}
            </svg>
            <p className="map-note">
              Тактичний плот у координатах lon/lat без базової картографічної
              підложки — навмисно, щоб не залежати від зовнішніх тайл-серверів і
              не розкривати районів інтересу. Наведіть/торкніться точки для деталей.
            </p>
          </div>
        )}

        {selected && (
          <div className="signal-review-card" style={{ marginTop: 12, borderLeft: `3px solid ${OUTCOME_COLOR[selected.properties.outcome]}` }}>
            <div style={{ fontWeight: 500 }}>
              {selected.properties.serial_no} · {OUTCOME_LABEL[selected.properties.outcome]}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              Тип {selected.properties.item_type_code} · {selected.properties.operator_code} ·{" "}
              {selected.properties.event_date} · [{selected.geometry.coordinates[1].toFixed(4)},{" "}
              {selected.geometry.coordinates[0].toFixed(4)}]
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
