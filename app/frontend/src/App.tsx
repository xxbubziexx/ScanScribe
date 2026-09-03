import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { AppLayout } from '@/components/layout/AppLayout'
import { LoginPage } from '@/pages/Login/LoginPage'
import { RegisterPage } from '@/pages/Register/RegisterPage'
import { CommandCenterPage } from '@/pages/CommandCenter/CommandCenterPage'
import { DashboardPage } from '@/pages/Dashboard/DashboardPage'
import { InsightsPage } from '@/pages/Insights/InsightsPage'
import { DatabasePage } from '@/pages/Database/DatabasePage'
import { DatasetPage } from '@/pages/DataExplorer/DatasetPage'
import { DataExplorerLayout } from '@/pages/DataExplorer/DataExplorerLayout'
import { EventsTable } from '@/pages/DataExplorer/Tables/EventsTable'
import { SpansTable } from '@/pages/DataExplorer/Tables/SpansTable'
import { EntitiesTable } from '@/pages/DataExplorer/Tables/EntitiesTable'
import { EventsLayout } from '@/pages/Events/EventsLayout'
import { EventsIncidentsPage } from '@/pages/Events/IncidentsPage'
import { EventsMonitorsPage } from '@/pages/Events/EventsMonitorsPage'
import { EventsDebugPage } from '@/pages/Events/EventsDebugPage'
import { UsersPage } from '@/pages/Users/UsersPage'
import { RequireAdmin } from '@/components/auth/RequireAdmin'
import { DocumentTitle } from '@/components/layout/DocumentTitle'

const SettingsPage = lazy(() =>
  import('@/pages/Settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)

function SettingsFallback() {
  return (
    <div className="ss-splash">
      <span className="ss-splash-text">Loading settings…</span>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <DocumentTitle />
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected — all children share the AppLayout shell */}
        <Route element={<AppLayout />}>
          <Route path="/" element={<CommandCenterPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="/data" element={<DataExplorerLayout />}>
              <Route index element={<Navigate to="events" replace />} />
              <Route path="events" element={<EventsTable />} />
              <Route path="spans" element={<SpansTable />} />
              <Route path="entities" element={<EntitiesTable />} />
              <Route path="logs" element={<DatabasePage />} />
              <Route path="dataset" element={<DatasetPage />} />
            </Route>
            <Route path="/logs" element={<Navigate to="/data/logs" replace />} />
            <Route path="/events" element={<EventsLayout />}>
              <Route index element={<EventsIncidentsPage />} />
              <Route path="monitors" element={<EventsMonitorsPage />} />
              <Route path="span-store" element={<Navigate to="/data/spans" replace />} />
              <Route path="debug" element={<EventsDebugPage />} />
            </Route>
            <Route path="/users" element={<UsersPage />} />
            <Route
              path="/settings"
              element={
                <Suspense fallback={<SettingsFallback />}>
                  <SettingsPage />
                </Suspense>
              }
            />
          </Route>
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
