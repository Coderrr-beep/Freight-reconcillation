import { Outlet } from 'react-router-dom'
import { useSession } from '../../hooks/useSession'
import { RunOverlay } from '../dashboard/RunOverlay'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

export function AppShell() {
  const { running } = useSession()

  return (
    <div className="flex min-h-screen bg-ink-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="relative min-h-0 flex-1 overflow-y-auto px-8 py-7">
          <Outlet />
        </main>
        <footer className="border-t border-white/[0.04] px-8 py-3 text-[10px] tracking-[0.14em] text-mist-500">
          AI FINANCE CONTROLLER · RAZORPAY AI BUILDATHON
        </footer>
      </div>
      <RunOverlay open={running} />
    </div>
  )
}
