import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import StationsPage from './pages/StationsPage'
import StationDetail from './pages/StationDetail'
import AlertsPage from './pages/AlertsPage'

function NavItem({ to, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-4 py-2 rounded text-sm font-medium transition-colors ${
          isActive ? 'bg-green-600 text-white' : 'text-gray-400 hover:text-white'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-6">
          <span className="text-green-400 font-bold text-lg tracking-tight">
            ⚡ EV Fleet Monitor
          </span>
          <nav className="flex gap-2">
            <NavItem to="/" label="Dashboard" />
            <NavItem to="/stations" label="Stations" />
            <NavItem to="/alerts" label="Alerts" />
          </nav>
        </header>
        <main className="flex-1 p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/stations" element={<StationsPage />} />
            <Route path="/stations/:nrelId" element={<StationDetail />} />
            <Route path="/alerts" element={<AlertsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
