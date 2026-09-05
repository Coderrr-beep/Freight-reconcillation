import { motion } from 'framer-motion'
import { demoClock } from '../../demo/timestamps'
import { formatIssue } from '../../lib/format'
import type { MergedInvoiceResult } from '../../types/api'
import { StatusBadge } from '../ui/StatusBadge'

export function ActivityFeed({ results }: { results: MergedInvoiceResult[] }) {
  const featured = pickFeed(results)

  return (
    <section className="surface rounded-2xl p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="micro text-[9px] text-accent">Live reconciliation activity</p>
          <h3 className="mt-2 text-lg font-medium tracking-[-0.03em] text-white">Decision event stream</h3>
        </div>
        <span className="flex items-center gap-2 text-[9px] font-semibold tracking-[0.14em] text-verified">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-verified" /> LIVE
        </span>
      </div>
      <div className="mt-5 divide-y divide-white/[0.04]">
        {featured.map((row, index) => (
          <motion.div
            key={row.invoice_id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05, duration: 0.24 }}
            className="grid grid-cols-[70px_1fr_auto] items-center gap-x-3 gap-y-2 py-3.5 transition-colors hover:bg-white/[0.02] sm:grid-cols-[90px_110px_1fr_160px] sm:gap-4"
          >
            <p className="num text-[11px] text-mist-500">{demoClock(index)}</p>
            <p className="num text-[11px] text-accent-glow">{row.invoice_id}</p>
            <div className="col-span-2 sm:col-span-1">
              <p className="truncate text-sm text-mist-200">
                {row.resolved_by === 'ai_agent'
                  ? 'AI investigation complete'
                  : row.explanation}
              </p>
              <p className="mt-1 text-[10px] tracking-[0.12em] text-mist-500">{formatIssue(row.discrepancy_type)}</p>
            </div>
            <div className="col-span-3 flex justify-start sm:col-span-1 sm:justify-end">
              {row.resolved_by === 'ai_agent' && row.status === 'needs_human' ? (
                <span className="rounded-full border border-accent/20 bg-accent/10 px-2 py-1 text-[9px] font-semibold tracking-[0.14em] text-accent">
                  AI INVESTIGATION
                </span>
              ) : (
                <StatusBadge status={row.status} />
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

function pickFeed(results: MergedInvoiceResult[]): MergedInvoiceResult[] {
  const flagged = results.filter((row) => row.status === 'flagged').slice(0, 3)
  const human = results.filter((row) => row.status === 'needs_human').slice(0, 2)
  const cleared = results.filter((row) => row.status === 'auto_clear').slice(0, 3)
  return [...cleared, ...flagged, ...human].slice(0, 8)
}
