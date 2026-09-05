import { Fragment, useMemo, useState } from 'react'
import { demoClock } from '../../demo/timestamps'
import { formatIssue } from '../../lib/format'
import type { MergedInvoiceResult } from '../../types/api'
import { StatusBadge } from '../ui/StatusBadge'

export function AuditTable({ results }: { results: MergedInvoiceResult[] }) {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<'all' | 'deterministic' | 'ai_agent'>('all')
  const [openId, setOpenId] = useState<string | null>(null)

  const rows = useMemo(() => {
    return results.filter((row) => {
      if (source !== 'all' && row.resolved_by !== source) return false
      const hay = `${row.invoice_id} ${row.discrepancy_type} ${row.status}`.toLowerCase()
      return hay.includes(query.trim().toLowerCase())
    })
  }, [results, query, source])

  return (
    <div>
      <div className="mb-4 flex gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Invoice, action, decision..."
          className="h-10 w-72 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-sm outline-none focus:border-accent/40"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as typeof source)}
          className="h-10 rounded-lg border border-white/10 bg-ink-800 px-3 text-xs tracking-wide text-mist-200"
        >
          <option value="all">SOURCE · ALL</option>
          <option value="deterministic">RULE ENGINE</option>
          <option value="ai_agent">AI AGENT</option>
        </select>
      </div>
      <div className="surface overflow-hidden rounded-xl">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-white/[0.05] text-[10px] tracking-[0.16em] text-mist-500">
              {['TIME', 'INVOICE', 'ACTION', 'ACTOR', 'DECISION', 'EVIDENCE'].map((col) => (
                <th key={col} className="px-4 py-3 font-semibold">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const actor = row.resolved_by === 'ai_agent' ? 'AI Agent' : 'Reconciliation Engine'
              const action =
                row.resolved_by === 'ai_agent'
                  ? 'AI investigation'
                  : row.status === 'auto_clear'
                    ? 'Rate validated'
                    : formatIssue(row.discrepancy_type)
              const evidence = [
                'Invoice',
                row.matched_rate_id ? 'Rate Card' : null,
                row.deterministic_result.evidence.dispatched_weight_tons != null ? 'Dispatch' : null,
                row.deterministic_result.evidence.duplicate_related_invoice_ids.length ? 'Related LR' : null,
              ]
                .filter(Boolean)
                .join(' + ')
              const expanded = openId === row.invoice_id
              return (
                <Fragment key={row.invoice_id}>
                  <tr
                    onClick={() => setOpenId(expanded ? null : row.invoice_id)}
                    className="cursor-pointer border-b border-white/[0.04] hover:bg-white/[0.03]"
                  >
                    <td className="num px-4 py-4 text-xs text-mist-500">{demoClock(index)}</td>
                    <td className="num px-4 py-4 text-sm text-accent-glow">{row.invoice_id}</td>
                    <td className="px-4 py-4 text-sm text-mist-200">{action}</td>
                    <td className="px-4 py-4 text-sm text-mist-300">{actor}</td>
                    <td className="px-4 py-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-4 text-xs text-mist-400">{evidence || 'Invoice'}</td>
                  </tr>
                  {expanded ? (
                    <tr className="border-b border-white/[0.04] bg-black/20">
                      <td colSpan={6} className="px-4 py-4 text-sm leading-7 text-mist-300">
                        {row.explanation}
                        <span className="mt-2 block text-[11px] tracking-wide text-mist-500">
                          Checks: {row.deterministic_result.checks_performed.join(' · ') || '—'}
                        </span>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
