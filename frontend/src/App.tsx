import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { SessionProvider } from './hooks/useSession'
import { ToastProvider } from './hooks/useToast'
import { AIInvestigation } from './pages/AIInvestigation'
import { AuditTrail } from './pages/AuditTrail'
import { Exceptions } from './pages/Exceptions'
import { Overview } from './pages/Overview'
import { Reconciliation } from './pages/Reconciliation'

export default function App() {
  return (
    <ToastProvider>
      <SessionProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={<Overview />} />
              <Route path="/reconciliation" element={<Reconciliation />} />
              <Route path="/exceptions" element={<Exceptions />} />
              <Route path="/investigation" element={<AIInvestigation />} />
              <Route path="/audit" element={<AuditTrail />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </SessionProvider>
    </ToastProvider>
  )
}
