import { useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Zap,
  FilePlus,
  FolderKanban,
  Library,
  FileBarChart,
  Settings,
  Plug,
  Shield,
  Upload,
} from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { installAutoSync } from "./lib/sync";
import { IS_DEMO } from "./lib/api";
import Dashboard from "./pages/Dashboard";
import EventsPage from "./pages/EventsPage";
import EventForm from "./pages/EventForm";
import CasesPage from "./pages/CasesPage";
import ImportPage from "./pages/ImportPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

const NAV = [
  { section: "Аналітика" },
  { to: "/", icon: LayoutDashboard, label: "Дашборд" },
  { to: "/events", icon: Zap, label: "Події" },
  { to: "/event-form", icon: FilePlus, label: "Подати подію" },
  { to: "/import", icon: Upload, label: "Імпорт CSV/XLSX" },
  { section: "AAR" },
  { to: "/cases", icon: FolderKanban, label: "Кейси" },
  { to: "/context", icon: Library, label: "Контекст-активи" },
  { section: "Звіти" },
  { to: "/reports", icon: FileBarChart, label: "Звіти" },
  { section: "Система" },
  { to: "/integrations", icon: Plug, label: "Інтеграції" },
  { to: "/audit", icon: Shield, label: "Аудит" },
  { to: "/settings", icon: Settings, label: "Налаштування" },
] as const;

function Sidebar() {
  const { pathname } = useLocation();
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        AAR
        {IS_DEMO && (
          <span
            style={{
              fontSize: 10,
              padding: "2px 6px",
              marginLeft: 8,
              background: "var(--accent-gold-muted)",
              color: "var(--accent-gold)",
              borderRadius: 4,
              fontWeight: 600,
              letterSpacing: 0,
            }}
          >
            DEMO
          </span>
        )}
      </div>
      {NAV.map((item, i) =>
        "section" in item ? (
          <div className="sidebar-section" key={i}>{item.section}</div>
        ) : (
          <Link
            key={item.to}
            to={item.to}
            className={pathname === item.to ? "active" : ""}
          >
            <item.icon />
            {item.label}
          </Link>
        ),
      )}
    </nav>
  );
}

function Placeholder({ title }: { title: string }) {
  return (
    <div className="card" style={{ textAlign: "center", padding: 40 }}>
      <h2>{title}</h2>
      <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>
        Сторінка у розробці
      </p>
    </div>
  );
}

export default function App() {
  useEffect(() => installAutoSync(), []);
  return (
    <QueryClientProvider client={queryClient}>
      <div className="app">
        <Sidebar />
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/event-form" element={<EventForm />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/context" element={<Placeholder title="Контекст-активи" />} />
            <Route path="/reports" element={<Placeholder title="Звіти" />} />
            <Route path="/integrations" element={<Placeholder title="Інтеграції" />} />
            <Route path="/audit" element={<Placeholder title="Аудит" />} />
            <Route path="/settings" element={<Placeholder title="Налаштування" />} />
          </Routes>
        </main>
      </div>
    </QueryClientProvider>
  );
}
