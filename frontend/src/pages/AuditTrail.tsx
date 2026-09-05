import { AuditTable } from '../components/audit/AuditTable'
import { EmptyState } from '../components/ui/EmptyState'
import { useSession } from '../hooks/useSession'

export function AuditTrail() {
  const { batch, connected, error, refresh } = useSession()

  if (connected === false) {
    return (
      <EmptyState
        title="Reconciliation engine unavailable"
        body={error ?? 'Audit log cannot be loaded.'}
        actionLabel="Retry Connection"
        onAction={() => void refresh()}
      />
    )
  }

  if (!batch) {
    return <EmptyState title="Audit trail empty" body="Every financial decision will appear here after a run." />
  }

  return (
    <div>
      <p className="text-sm text-mist-400">Every financial decision is traceable.</p>
      <div className="mt-6">
        <AuditTable results={batch.results} />
      </div>
    </div>
  )
}
