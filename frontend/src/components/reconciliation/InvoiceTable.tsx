import { useMemo, useState } from 'react'
import { formatINR, formatIssue, primaryIssue } from '../../lib/format'
import type { Invoice, MergedInvoiceResult } from '../../types/api'
import { ConfidenceMeter, engineConfidencePct } from '../ui/ConfidenceMeter'
import { StatusBadge } from '../ui/StatusBadge'

type StatusFilter = 'all' | 'auto_clear' | 'flagged' | 'needs_human'
type IssueFilter = 'all' | 'rate_mismatch' | 'weight_variance' | 'duplicate_billing' | 'no_contracted_rate_found'

export function InvoiceTable({
  results,
  invoices,
  onSelect,
}: {
  results: MergedInvoiceResult[]
  invoices: Invoice[]
  onSelect: (row: MergedInvoiceResult) => void
}) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [issue, setIssue] = useState<IssueFilter>('all')
  const invoiceMap = useMemo(
    () => new Map(invoices.map((item) => [item.invoice_id, item])),
    [invoices],
  )

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return results.filter((row) => {
      const inv = invoiceMap.get(row.invoice_id)
      if (status !== 'all' && row.status !== status) return false
      const detected = primaryIssue(row.discrepancy_type, row.deterministic_result.evidence.issues_detected)
      if (issue !== 'all' && detected !== issue) return false
      if (!q) return true
      const hay = `${row.invoice_id} ${row.lr_number} ${inv?.transporter_name ?? ''} ${inv?.origin ?? ''} ${inv?.destination ?? ''}`.toLowerCase()
      return hay.includes(q)
    })
  }, [results, invoiceMap, query, status, issue])

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search invoices..."
          className="h-10 w-64 rounded-xl border border-white/10 bg-white/[0.02] px-3 text-sm text-white outline-none placeholder:text-mist-500 focus:border-accent/40"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusFilter)}
          className="h-10 rounded-xl border border-white/10 bg-ink-800 px-3 text-[10px] tracking-[0.16em] text-mist-200"
        >
          <option value="all">STATUS · ALL</option>
          <option value="auto_clear">CLEARED</option>
          <option value="flagged">FLAGGED</option>
          <option value="needs_human">HUMAN REVIEW</option>
        </select>
        <select
          value={issue}
          onChange={(e) => setIssue(e.target.value as IssueFilter)}
          className="h-10 rounded-xl border border-white/10 bg-ink-800 px-3 text-[10px] tracking-[0.16em] text-mist-200"
        >
          <option value="all">ISSUE · ALL</option>
          <option value="rate_mismatch">RATE</option>
          <option value="weight_variance">WEIGHT</option>
          <option value="duplicate_billing">DUPLICATE</option>
          <option value="no_contracted_rate_found">NO CONTRACT</option>
        </select>
        <p className="ml-auto text-[10px] tracking-[0.16em] text-mist-500">{rows.length} SHOWN</p>
      </div>

      <div className="surface overflow-hidden rounded-2xl">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left">
            <thead>
              <tr className="border-b border-white/[0.05] text-[9px] tracking-[0.18em] text-mist-500">
                {[
                  'INVOICE',
                  'TRANSPORTER',
                  'ROUTE',
                  'BILLED',
                  'EXPECTED',
                  'VARIANCE',
                  'STATUS',
                  'ISSUE',
                  'CONFIDENCE',
                  'ACTION',
                ].map((col) => (
                  <th key={col} className="px-4 py-3 font-semibold">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const inv = invoiceMap.get(row.invoice_id)
                const ev = row.deterministic_result.evidence
                const billed = ev.billed_amount ?? inv?.total_amount ?? 0
                const expected = ev.expected_amount
                const variance = expected == null ? row.rupee_impact : billed - expected
                const conf = row.ai_result
                  ? Math.round(row.ai_result.confidence * 100)
                  : engineConfidencePct(row.deterministic_result.confidence)
                return (
                  <tr
                    key={row.invoice_id}
                    onClick={() => onSelect(row)}
                    className="group cursor-pointer border-b border-white/[0.04] transition hover:bg-white/[0.035] hover:shadow-[inset_2px_0_0_rgba(124,108,255,0.7)]"
                  >
                    <td className="px-4 py-4">
                      <p className="num text-[13px] text-accent-glow">{row.invoice_id}</p>
                      <p className="mt-1 text-[10px] tracking-[0.12em] text-mist-500">{row.lr_number}</p>
                    </td>
                    <td className="px-4 py-4 text-sm text-mist-200">{inv?.transporter_name ?? '—'}</td>
                    <td className="px-4 py-4 text-sm text-mist-300">
                      {inv ? `${inv.origin} → ${inv.destination}` : '—'}
                    </td>
                    <td className="num px-4 py-4 text-sm">{formatINR(billed)}</td>
                    <td className="num px-4 py-4 text-sm text-mist-300">
                      {expected == null ? '—' : formatINR(expected)}
                    </td>
                    <td className={`num px-4 py-4 text-sm ${variance > 0.01 ? 'text-risk' : 'text-mist-300'}`}>
                      {formatINR(variance)}
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-4 text-[10px] tracking-[0.14em] text-mist-300">
                      {formatIssue(primaryIssue(row.discrepancy_type, ev.issues_detected))}
                    </td>
                    <td className="px-4 py-4">
                      <ConfidenceMeter value={conf} />
                    </td>
                    <td className="px-4 py-4 text-[10px] font-semibold tracking-[0.16em] text-mist-500 transition-colors group-hover:text-accent">VIEW</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
