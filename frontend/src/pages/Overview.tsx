import { ExecutiveMetrics } from '../components/dashboard/ExecutiveMetrics'
import { IntelligenceSection, ExposureSection } from '../components/dashboard/IntelligenceSection'
import { ControlPipeline } from '../components/dashboard/ControlPipeline'
import { ActivityFeed } from '../components/dashboard/ActivityFeed'
import { EmptyState, Skeleton } from '../components/ui/EmptyState'
import { useSession } from '../hooks/useSession'

export function Overview() {
  const { batch, loading, connected, error, refresh, runReconciliation, running } = useSession()

  if (connected === false) {
    return (
      <EmptyState
        title="Reconciliation engine unavailable"
        body={error ?? 'The control plane cannot reach the backend.'}
        actionLabel="Retry Connection"
        onAction={() => void refresh()}
      />
    )
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-[280px]" />
          <Skeleton className="h-[280px]" />
        </div>
        <Skeleton className="h-[160px]" />
      </div>
    )
  }

  if (!batch) {
    return (
      <div className="mx-auto max-w-2xl pt-14 text-center">
        <p className="micro text-accent">Finance control center</p>
        <h2 className="mt-4 text-3xl font-medium tracking-[-0.05em] text-white">No batch in memory</h2>
        <p className="mt-3 text-sm leading-7 text-mist-400">
          Run reconciliation to ingest invoices, prove contracted rates, and send unresolved cases to the AI agent.
        </p>
        <button
          type="button"
          disabled={running}
          onClick={() => void runReconciliation()}
          className="mt-8 rounded-xl border border-accent/20 bg-accent px-5 py-2.5 text-[10px] font-semibold tracking-[0.16em] text-white"
        >
          RUN RECONCILIATION
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="micro text-accent">Finance control center</p>
        <h2 className="mt-2 max-w-xl text-[32px] font-medium leading-tight tracking-[-0.05em] text-white">
          Control freight spend before it becomes leakage.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-mist-400">
          Reconcile every freight invoice against contracted rates and dispatch evidence — then let AI investigate the
          cases rules cannot resolve.
        </p>
      </div>
      <ExecutiveMetrics batch={batch} />
      <IntelligenceSection batch={batch} />
      <ExposureSection batch={batch} />
      <ControlPipeline batch={batch} />
      <ActivityFeed results={batch.results} />
    </div>
  )
}
