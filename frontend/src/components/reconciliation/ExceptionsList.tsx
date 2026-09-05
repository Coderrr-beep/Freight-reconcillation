import { useMemo, useState } from 'react'
import { formatIssue, formatINR, formatPct } from '../../lib/format'
import { exceptionRows, exposureTotal } from '../../lib/aggregates'
import type { Invoice, MergedInvoiceResult } from '../../types/api'
import { StatusBadge } from '../ui/StatusBadge'

export function ExceptionsList({
  results,
  invoices,
  onSelect,
}: {
  results: MergedInvoiceResult[]
  invoices: Invoice[]
  onSelect: (row: MergedInvoiceResult) => void
}) {
  const rows = useMemo(() => exceptionRows(results), [results])
  const [query, setQuery] = useState('')
  const map = useMemo(() => new Map(invoices.map((i) => [i.invoice_id, i])), [invoices])
  const visible = rows.filter((row) => {
    const inv = map.get(row.invoice_id)
    const hay = `${row.invoice_id} ${inv?.transporter_name ?? ''} ${row.discrepancy_type}`.toLowerCase()
    return hay.includes(query.trim().toLowerCase())
  })
  const high = rows.filter((row) => row.rupee_impact >= 10000).length
  const total = exposureTotal(results)

  return (
    <div>
      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="Total exceptions" value={String(rows.length)} />
        <Stat label="Total exposure" value={formatINR(total)} />
        <Stat label="High priority" value={String(high)} hint="≥ ₹10,000" />
      </div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter exceptions..."
        className="mt-5 h-10 w-72 rounded-xl border border-white/10 bg-white/[0.02] px-3 text-sm outline-none focus:border-accent/40"
      />
      <div className="mt-4 space-y-2">
        {visible.map((row) => {
          const inv = map.get(row.invoice_id)
          const hot = row.rupee_impact >= 10000
          return (
            <button
              type="button"
              key={row.invoice_id}
              onClick={() => onSelect(row)}
              className={`grid w-full grid-cols-[80px_120px_1fr_180px_140px_110px] items-center gap-3 rounded-2xl px-4 py-4 text-left transition hover:-translate-y-0.5 hover:border-white/10 ${
                hot ? 'border border-risk/20 bg-risk/[0.04]' : 'surface'
              }`}
            >
              <span className={`text-[9px] font-semibold tracking-[0.16em] ${hot ? 'text-risk' : 'text-review'}`}>
                {hot ? 'HIGH' : 'MED'}
              </span>
              <div>
                <p className="num text-sm text-accent-glow">{row.invoice_id}</p>
                <p className="text-[10px] tracking-[0.12em] text-mist-500">{row.lr_number}</p>
              </div>
              <div>
                <p className="text-[10px] tracking-[0.16em] text-mist-200">{formatIssue(row.discrepancy_type)}</p>
                <p className="mt-1 text-xs text-mist-500">{inv?.transporter_name ?? '—'}</p>
              </div>
              <p className="num text-sm text-white">{formatINR(row.rupee_impact)}</p>
              <StatusBadge status={row.status} />
              <p className="text-right text-[10px] font-semibold tracking-[0.16em] text-mist-400">INSPECT</p>
            </button>
          )
        })}
      </div>
      <p className="mt-3 text-[10px] tracking-[0.14em] text-mist-500">{formatPct(visible.length, results.length)} OF BATCH CURRENTLY EXCEPTED</p>
    </div>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="surface rounded-xl px-5 py-4">
      <p className="micro">{label}</p>
      <p className="num mt-2 text-2xl text-white">{value}</p>
      {hint ? <p className="mt-1 text-[11px] text-mist-500">{hint}</p> : null}
    </div>
  )
}
