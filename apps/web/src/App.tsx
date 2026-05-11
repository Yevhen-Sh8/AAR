import { Route, Routes, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import EventsPage from "./pages/EventsPage";
import CasesPage from "./pages/CasesPage";

export default function App() {
  return (
    <div className="app">
      <header>
        <h1>AAR</h1>
        <nav>
          <Link to="/">Дашборд</Link>
          <Link to="/events">Події</Link>
          <Link to="/cases">AAR-кейси</Link>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/cases" element={<CasesPage />} />
        </Routes>
      </main>
    </div>
  );
}
