import { useEffect, useState } from "react";
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
  BookOpen,
  Activity,
  LogOut,
} from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { installAutoSync } from "./lib/sync";
import { IS_DEMO } from "./lib/api";
import { clearSession, getEmail, isAuthed } from "./lib/auth";
import Dashboard from "./pages/Dashboard";
import EventsPage from "./pages/EventsPage";
import EventForm from "./pages/EventForm";
import CasesPage from "./pages/CasesPage";
import ImportPage from "./pages/ImportPage";
import ContextPage from "./pages/ContextPage";
import ReportsPage from "./pages/ReportsPage";
import IntegrationsPage from "./pages/IntegrationsPage";
import AuditPage from "./pages/AuditPage";
import SettingsPage from "./pages/SettingsPage";
import DictionariesPage from "./pages/DictionariesPage";
import LearningLoopPage from "./pages/LearningLoopPage";
import LoginPage from "./pages/LoginPage";

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
  { to: "/learning-loop", icon: Activity, label: "Цикл навчання" },
  { section: "Система" },
  { to: "/dictionaries", icon: BookOpen, label: "Довідники" },
  { to: "/integrations", icon: Plug, label: "Інтеграції" },
  { to: "/audit", icon: Shield, label: "Аудит" },
  { to: "/settings", icon: Settings, label: "Налаштування" },
] as const;

function Sidebar({ onLogout }: { onLogout: () => void }) {
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
      {!IS_DEMO && (
        <button className="sidebar-logout" onClick={onLogout} title={getEmail() ?? ""}>
          <LogOut size={18} />
          Вийти{getEmail() ? ` (${getEmail()})` : ""}
        </button>
      )}
    </nav>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(IS_DEMO || isAuthed());

  useEffect(() => installAutoSync(), []);
  useEffect(() => {
    const onUnauth = () => setAuthed(false);
    window.addEventListener("aar:unauthorized", onUnauth);
    return () => window.removeEventListener("aar:unauthorized", onUnauth);
  }, []);

  function logout() {
    clearSession();
    setAuthed(false);
  }

  if (!IS_DEMO && !authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <div className="app">
        <Sidebar onLogout={logout} />
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/event-form" element={<EventForm />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/context" element={<ContextPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/learning-loop" element={<LearningLoopPage />} />
            <Route path="/dictionaries" element={<DictionariesPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </QueryClientProvider>
  );
}
