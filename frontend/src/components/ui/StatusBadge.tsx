import type { ReconciliationStatus } from '../../types/api'

const MAP: Record<ReconciliationStatus, { label: string; className: string }> = {
  auto_clear: {
    label: 'AUTO-CLEARED',
    className: 'bg-verified/10 text-verified border-verified/20',
  },
  flagged: {
    label: 'FLAGGED',
    className: 'bg-risk/10 text-risk border-risk/20',
  },
  needs_human: {
    label: 'HUMAN REVIEW',
    className: 'bg-review/10 text-review border-review/20',
  },
}

export function StatusBadge({ status }: { status: ReconciliationStatus }) {
  const item = MAP[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-semibold tracking-[0.16em] ${item.className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-90" />
      {item.label}
    </span>
  )
}
