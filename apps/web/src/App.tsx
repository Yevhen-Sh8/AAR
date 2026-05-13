import { useEffect } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { installAutoSync } from "./lib/sync";
import CasesPage from "./pages/CasesPage";
import Dashboard from "./pages/Dashboard";
import EventForm from "./pages/EventForm";
import EventsPage from "./pages/EventsPage";

export default function App() {
  useEffect(() => installAutoSync(), []);
  return (
    <div className="app">
      <header>
        <h1>AAR</h1>
        <nav>
          <Link to="/">Дашборд</Link>
          <Link to="/events">Події</Link>
          <Link to="/event-form">Подати подію</Link>
          <Link to="/cases">AAR-кейси</Link>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/event-form" element={<EventForm />} />
          <Route path="/cases" element={<CasesPage />} />
        </Routes>
      </main>
    </div>
  );
}
