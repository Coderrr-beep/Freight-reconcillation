import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Rows3,
  ShieldAlert,
  Sparkles,
  ScrollText,
} from 'lucide-react'
import { useSession } from '../../hooks/useSession'

const LINKS = [
  { to: '/', label: 'OVERVIEW', icon: LayoutDashboard },
  { to: '/reconciliation', label: 'RECONCILIATION', icon: Rows3 },
  { to: '/exceptions', label: 'EXCEPTIONS', icon: ShieldAlert },
  { to: '/investigation', label: 'AI INVESTIGATION', icon: Sparkles },
  { to: '/audit', label: 'AUDIT TRAIL', icon: ScrollText },
]

export function Sidebar() {
  const { status, connected } = useSession()
  const engineOnline = connected !== false
  const aiReady = status?.ai_agent === 'ready'

  return (
    <aside className="flex h-screen w-[232px] shrink-0 flex-col border-r border-white/[0.05] bg-[#07090D]">
      <div className="px-6 pb-8 pt-7">
        <div className="font-semibold tracking-tight text-white">
          <span className="text-[22px]">FREIGHT</span>
          <span className="block text-[22px] text-accent">//AI</span>
        </div>
        <p className="micro mt-3">Finance control</p>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-3">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[11px] font-semibold tracking-[0.14em] transition-colors ${
                isActive
                  ? 'bg-accent/10 text-white'
                  : 'text-mist-400 hover:bg-white/[0.03] hover:text-mist-200'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`absolute left-0 top-1.5 h-[calc(100%-12px)] w-[2px] rounded-full ${
                    isActive ? 'bg-accent shadow-[0_0_12px_#7C6CFF]' : 'bg-transparent'
                  }`}
                />
                <link.icon className={`h-3.5 w-3.5 ${isActive ? 'text-accent' : ''}`} />
                {link.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-6 pb-6">
        <p className="micro mb-3">System status</p>
        <div className="space-y-2 text-[11px] tracking-wide text-mist-200">
          <p className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 rounded-full ${engineOnline ? 'bg-verified' : 'bg-risk'}`} />
            RECONCILIATION ENGINE
            <span className="ml-auto text-mist-500">{engineOnline ? 'ONLINE' : 'DOWN'}</span>
          </p>
          <p className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 rounded-full ${aiReady ? 'bg-accent animate-pulseGlow' : 'bg-review'}`} />
            AI AGENT
            <span className="ml-auto text-mist-500">{aiReady ? 'READY' : 'DEGRADED'}</span>
          </p>
        </div>
        <div className="mt-6 border-t border-white/[0.05] pt-4 text-[10px] tracking-wide text-mist-500">
          <p>v1.0.0</p>
          <p className="mt-1">Razorpay AI Buildathon</p>
        </div>
      </div>
    </aside>
  )
}
