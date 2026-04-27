import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { AppLayout } from '@/components/layout/AppLayout'
import { LoginPage } from '@/pages/Login/LoginPage'
import { RegisterPage } from '@/pages/Register/RegisterPage'
import { DashboardPage } from '@/pages/Dashboard/DashboardPage'
import { InsightsPage } from '@/pages/Insights/InsightsPage'
import { DatabasePage } from '@/pages/Database/DatabasePage'
import { EventsLayout } from '@/pages/Events/EventsLayout'
import { EventsIncidentsPage } from '@/pages/Events/IncidentsPage'
import { EventsMonitorsPage } from '@/pages/Events/EventsMonitorsPage'
import { EventsDebugPage } from '@/pages/Events/EventsDebugPage'

/** Temporary placeholder — replaced as each page is ported to React. */
function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-xl border border-white/10">
      <p className="font-mono text-sm text-gray-500">[{name}] — migration in progress</p>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected — all children share the AppLayout shell */}
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/logs" element={<DatabasePage />} />
          <Route path="/events" element={<EventsLayout />}>
            <Route index element={<EventsIncidentsPage />} />
            <Route path="monitors" element={<EventsMonitorsPage />} />
            <Route path="debug" element={<EventsDebugPage />} />
          </Route>
          <Route path="/users" element={<Placeholder name="Users" />} />
          <Route path="/settings" element={<Placeholder name="Settings" />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
