import { useMemo, useState } from 'react'
import { DecisionCard, InvestigationTimeline } from '../components/ai/InvestigationPanel'
import { EmptyState } from '../components/ui/EmptyState'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useSession } from '../hooks/useSession'
import { aiCases } from '../lib/aggregates'
import { formatINR, formatIssue, formatDate } from '../lib/format'

export function AIInvestigation() {
  const { batch, invoices, connected, error, refresh } = useSession()
  const cases = useMemo(() => (batch ? aiCases(batch.results) : []), [batch])
  const [activeId, setActiveId] = useState<string | null>(null)
  const selected = cases.find((row) => row.invoice_id === (activeId ?? cases[0]?.invoice_id)) ?? cases[0]
  const invoice = invoices.find((item) => item.invoice_id === selected?.invoice_id)

  if (connected === false) {
    return (
      <EmptyState
        title="Reconciliation engine unavailable"
        body={error ?? 'AI console cannot reach the API.'}
        actionLabel="Retry Connection"
        onAction={() => void refresh()}
      />
    )
  }

  if (!batch) {
    return <EmptyState title="No agent activity" body="Run reconciliation to send inconclusive cases to the AI agent." />
  }

  if (!selected) {
    return (
      <EmptyState
        title="No AI investigations in this batch"
        body="The deterministic engine resolved every invoice without routing to the agent."
      />
    )
  }

  return (
    <div>
      <p className="micro text-accent">Enterprise investigation console</p>
      <h2 className="mt-2 text-2xl font-medium tracking-[-0.05em] text-white">AI case review</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-mist-400">
        Agent reasoning across invoices, contracts and operational evidence.
      </p>
      <div className="mt-6 grid gap-4 lg:grid-cols-[0.35fr_0.65fr]">
        <aside className="surface rounded-xl p-5">
          <p className="micro text-[9px] text-accent">Case queue</p>
          <div className="mt-4 space-y-1">
            {cases.map((row) => (
              <button
                type="button"
                key={row.invoice_id}
                onClick={() => setActiveId(row.invoice_id)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left ${
                  row.invoice_id === selected.invoice_id ? 'bg-accent/10' : 'hover:bg-white/[0.03]'
                }`}
              >
                <span className="num text-sm text-white">{row.invoice_id}</span>
                <span className="text-[10px] tracking-wide text-mist-500">{formatIssue(row.discrepancy_type)}</span>
              </button>
            ))}
          </div>
          <div className="mt-6 border-t border-white/[0.06] pt-5">
            <p className="micro text-[9px] text-accent">Case</p>
            <p className="num mt-2 text-2xl tracking-[-0.04em] text-white">{selected.invoice_id}</p>
            <div className="mt-3">
              <StatusBadge status={selected.status} />
            </div>
            <p className="micro mt-5">Issue</p>
            <p className="mt-1 text-sm text-mist-200">{formatIssue(selected.discrepancy_type)}</p>
            <p className="micro mt-4">Exposure</p>
            <p className="num mt-1 text-2xl">{formatINR(selected.rupee_impact)}</p>
            <p className="micro mt-4">Transporter</p>
            <p className="mt-1 text-sm text-mist-200">{invoice?.transporter_name ?? '—'}</p>
            <p className="micro mt-4">Route</p>
            <p className="mt-1 text-sm text-mist-200">
              {invoice ? `${invoice.origin} → ${invoice.destination}` : '—'}
            </p>
            <p className="micro mt-4">Invoice date</p>
            <p className="mt-1 text-sm text-mist-200">{formatDate(invoice?.invoice_date)}</p>
            {selected.deterministic_result.evidence.duplicate_related_invoice_ids.length > 0 ? (
              <div className="mt-5 rounded-xl border border-risk/20 bg-risk/[0.06] p-3">
                <p className="micro text-[9px] text-risk">Duplicate billing</p>
                <p className="mt-2 text-xs text-mist-200">
                  Related invoice: <span className="num text-white">{selected.deterministic_result.evidence.duplicate_related_invoice_ids.join(', ')}</span>
                </p>
                <p className="mt-1 text-xs text-mist-400">Same LR {selected.lr_number}</p>
              </div>
            ) : null}
          </div>
        </aside>

        <div className="space-y-4">
          <div className="surface rounded-xl p-6">
            <div className="mb-5 flex items-center justify-between">
              <p className="micro text-accent">Agent activity</p>
              <span className="flex items-center gap-2 text-[10px] tracking-[0.16em] text-accent">
                <span className="h-1.5 w-1.5 animate-pulseGlow rounded-full bg-accent" />
                ANALYZING EVIDENCE
              </span>
            </div>
            <InvestigationTimeline result={selected} />
          </div>
          <DecisionCard ai={selected.ai_result} fallback={selected.explanation} />
        </div>
      </div>
    </div>
  )
}
