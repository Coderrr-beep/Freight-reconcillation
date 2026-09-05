import { useLocation } from 'react-router-dom'
import { useSession } from '../../hooks/useSession'

const TITLES: Record<string, string> = {
  '/': 'Overview',
  '/reconciliation': 'Reconciliation',
  '/exceptions': 'Exceptions',
  '/investigation': 'AI Investigation',
  '/audit': 'Audit Trail',
}

export function TopBar() {
  const { pathname } = useLocation()
  const { batch, status, connected, running, runReconciliation } = useSession()
  const title = TITLES[pathname] ?? 'FREIGHT//AI'
  const engineOnline = connected !== false
  const aiReady = status?.ai_agent === 'ready'

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.05] bg-[#0B0E13]/85 px-8 backdrop-blur-md">
      <h1 className="text-[15px] font-medium tracking-[-0.02em] text-white">{title}</h1>
      <div className="flex items-center gap-5">
        <Meta label="Batch" value={batch ? `${batch.total_invoices} RECORDS` : 'IDLE'} />
        <Meta label="Engine" value={engineOnline ? 'ONLINE' : 'DOWN'} />
        <Meta label="AI" value={aiReady ? 'READY' : 'DEGRADED · NOT CONFIGURED'} />
        <button
          type="button"
          disabled={running || !engineOnline}
          onClick={() => void runReconciliation()}
          className="rounded-xl border border-accent/25 bg-accent px-3.5 py-2 text-[10px] font-semibold tracking-[0.16em] text-white shadow-[0_0_24px_rgba(124,108,255,0.28)] transition hover:-translate-y-0.5 hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? 'RUNNING…' : 'RUN RECONCILIATION'}
        </button>
      </div>
    </header>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="hidden text-right sm:block">
      <p className="micro">{label}</p>
      <p className="mt-0.5 text-[11px] font-medium tracking-wide text-mist-100">{value}</p>
    </div>
  )
}
