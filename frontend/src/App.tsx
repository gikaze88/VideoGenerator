import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Film, History, Plus } from 'lucide-react'
import NewJob from './pages/NewJob'
import JobDetail from './pages/JobDetail'
import HistoryPage from './pages/History'

function NavItem({ to, icon: Icon, label }: { to: string; icon: typeof Film; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? 'bg-amber-500 text-gray-950'
            : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
        }`
      }
    >
      <Icon size={16} />
      {label}
    </NavLink>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-6">
            <div className="flex items-center gap-2">
              <Film className="text-amber-400" size={22} />
              <span className="font-semibold text-gray-100 text-base">
                La Sagesse Du Christ
              </span>
              <span className="text-gray-500 text-sm ml-1">— Générateur</span>
            </div>
            <nav className="flex items-center gap-1 ml-auto">
              <NavItem to="/" icon={Plus} label="Nouvelle vidéo" />
              <NavItem to="/history" icon={History} label="Historique" />
            </nav>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-8">
          <Routes>
            <Route path="/" element={<NewJob />} />
            <Route path="/jobs/:jobId" element={<JobDetail />} />
            <Route path="/history" element={<HistoryPage />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="border-t border-gray-800 text-center text-gray-600 text-xs py-4">
          SagesseDuChrist Video Generator — usage local
        </footer>
      </div>
    </BrowserRouter>
  )
}
