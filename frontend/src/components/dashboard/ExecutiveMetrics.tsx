import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { formatINR, formatNumber, formatPct } from '../../lib/format'
import type { BatchResult } from '../../types/api'
import { exposureTotal } from '../../lib/aggregates'

export function ExecutiveMetrics({ batch }: { batch: BatchResult }) {
  const exposure = exposureTotal(batch.results)
  const total = batch.total_invoices

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <Metric label="Total records" value={formatNumber(total)} hint="Current batch" />
      <Metric
        label="Auto-cleared"
        value={formatNumber(batch.auto_clear)}
        hint={`${formatPct(batch.auto_clear, total)} of batch`}
        tone="verified"
        badge="VERIFIED"
      />
      <Metric
        label="Flagged"
        value={formatNumber(batch.flagged)}
        hint={`${formatPct(batch.flagged, total)} of batch`}
        tone="risk"
        badge="DISCREPANCY"
      />
      <Metric
        label="Human review"
        value={formatNumber(batch.needs_human)}
        hint={`${formatPct(batch.needs_human, total)} of batch`}
        tone="review"
        badge="REVIEW"
      />
      <Metric
        label="Financial exposure"
        value={formatINR(exposure)}
        hint="Identified billing risk"
        featured
      />
    </div>
  )
}

function Metric({
  label,
  value,
  hint,
  tone,
  badge,
  featured,
}: {
  label: string
  value: string
  hint: string
  tone?: 'verified' | 'risk' | 'review'
  badge?: string
  featured?: boolean
}) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      className={`rounded-2xl px-5 py-4 ${
        featured
          ? 'surface-strong border border-risk/20 bg-gradient-to-br from-risk/[0.08] via-[#10141B] to-[#0B0E13]'
          : 'surface'
      }`}
    >
      <p className="micro text-[9px]">{label}</p>
      <p className={`num mt-3 tracking-[-0.04em] ${featured ? 'text-[26px] text-white' : 'text-[26px] text-white'}`}>
        {value}
      </p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="text-[11px] text-mist-400">{hint}</p>
        {badge ? <ToneBadge tone={tone}>{badge}</ToneBadge> : null}
      </div>
    </motion.div>
  )
}

function ToneBadge({
  tone,
  children,
}: {
  tone?: 'verified' | 'risk' | 'review'
  children: ReactNode
}) {
  const color =
    tone === 'verified' ? 'text-verified' : tone === 'risk' ? 'text-risk' : 'text-review'
  return <span className={`text-[9px] font-semibold tracking-[0.14em] ${color}`}>✓ {children}</span>
}
