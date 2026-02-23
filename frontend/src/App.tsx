import { useState, useEffect, useCallback } from 'react'
import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  BarChart3,
  Phone,
  TrendingUp,
  Settings,
  Moon,
  Sun,
  Menu,
  X,
  Heart,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import DashboardPage from '@/pages/DashboardPage'
import CallLogsPage from '@/pages/CallLogsPage'
import AnalyticsPage from '@/pages/AnalyticsPage'
import AgentConfigPage from '@/pages/AgentConfigPage'

/** Navigation items with routes, labels, and icons. */
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: BarChart3 },
  { to: '/calls', label: 'Call Logs', icon: Phone },
  { to: '/analytics', label: 'Analytics', icon: TrendingUp },
  { to: '/config', label: 'Configuration', icon: Settings },
] as const

/** Key used for persisting dark mode preference. */
const DARK_MODE_KEY = 'sunrise-health-dark-mode'

/** Read dark mode preference from localStorage or system preference. */
function getInitialDarkMode(): boolean {
  const stored = localStorage.getItem(DARK_MODE_KEY)
  if (stored !== null) return stored === 'true'
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export default function App() {
  const [darkMode, setDarkMode] = useState(getInitialDarkMode)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  // Apply dark mode class to document root.
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    localStorage.setItem(DARK_MODE_KEY, String(darkMode))
  }, [darkMode])

  // Close mobile sidebar on route change.
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  const toggleDarkMode = useCallback(() => {
    setDarkMode((prev) => !prev)
  }, [])

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev)
  }, [])

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border/50 bg-card transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo / Brand */}
        <div className="flex h-16 items-center gap-3 px-6 border-b border-border/50">
          <Heart className="h-6 w-6 text-rose-500 fill-rose-500 shrink-0" />
          <span className="text-lg font-bold tracking-tight text-foreground">
            Sunrise Health
          </span>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-3 py-4">
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) =>
                      [
                        'flex flex-row items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-primary/10 text-primary'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      ].join(' ')
                    }
                  >
                    <Icon className="h-[18px] w-[18px] shrink-0" />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* Bottom section */}
        <div className="border-t border-border/50 p-3">
          <button
            onClick={toggleDarkMode}
            className="flex w-full flex-row items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {darkMode ? (
              <Sun className="h-[18px] w-[18px] shrink-0" />
            ) : (
              <Moon className="h-[18px] w-[18px] shrink-0" />
            )}
            <span>{darkMode ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="min-h-screen lg:pl-64">
        {/* Mobile Header */}
        <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4 lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleSidebar}
            aria-label="Toggle navigation menu"
          >
            {sidebarOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </Button>
          <div className="flex items-center gap-2">
            <Heart className="h-5 w-5 text-rose-500 fill-rose-500" />
            <span className="font-semibold text-sm">Sunrise Health</span>
          </div>
        </header>

        {/* Page Content */}
        <main className="w-full overflow-x-hidden p-6 lg:p-8">
          <div className="max-w-7xl mx-auto">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/calls" element={<CallLogsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/config" element={<AgentConfigPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}
