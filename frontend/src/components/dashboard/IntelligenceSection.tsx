import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'
import { formatINR, formatNumber, formatPct } from '../../lib/format'
import { ISSUE_LABEL, ISSUE_ORDER, exposureTotal, issueStats } from '../../lib/aggregates'
import type { BatchResult } from '../../types/api'

const COLORS = {
  auto_clear: '#3EE0A3',
  flagged: '#F45B69',
  needs_human: '#F5A524',
}

export function IntelligenceSection({ batch }: { batch: BatchResult }) {
  const data = [
    { name: 'AUTO-CLEARED', value: batch.auto_clear, color: COLORS.auto_clear },
    { name: 'FLAGGED', value: batch.flagged, color: COLORS.flagged },
    { name: 'HUMAN REVIEW', value: batch.needs_human, color: COLORS.needs_human },
  ]
  const stats = issueStats(batch.results)
  const totalIssues = ISSUE_ORDER.reduce((sum, key) => sum + stats[key].count, 0)

  return (
    <section className="grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
      <div className="surface rounded-2xl p-6">
        <p className="micro text-[9px]">Reconciliation intelligence</p>
        <div className="mt-5 flex items-center gap-8">
          <div className="relative h-[220px] w-[220px] shrink-0">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  innerRadius={66}
                  outerRadius={92}
                  paddingAngle={3}
                  stroke="rgba(255,255,255,0.08)"
                  strokeWidth={1}
                >
                  {data.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <p className="num text-[30px] tracking-[-0.04em] text-white">{formatNumber(batch.total_invoices)}</p>
              <p className="micro mt-1 text-[9px]">Invoices</p>
            </div>
          </div>
          <ul className="w-full space-y-3">
            {data.map((entry) => (
              <li key={entry.name} className="flex items-center gap-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: entry.color }} />
                <span className="w-32 text-[10px] font-semibold tracking-[0.16em] text-mist-400">{entry.name}</span>
                <span className="num ml-auto text-sm text-white">{entry.value}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="surface rounded-2xl p-6">
        <p className="micro text-[9px]">Exception breakdown</p>
        <div className="mt-5 space-y-4">
          {ISSUE_ORDER.map((key) => {
            const row = stats[key]
            const pct = totalIssues ? row.count / totalIssues : 0
            return (
              <div key={key} className="rounded-xl border border-white/5 bg-black/10 px-3 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[10px] font-semibold tracking-[0.16em] text-mist-200">
                    {ISSUE_LABEL[key]}
                  </p>
                  <p className="num text-sm text-white">{row.count}</p>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-gradient-to-r from-accent to-accent/70" style={{ width: `${pct * 100}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-between text-[10px] text-mist-500">
                  <span>{formatPct(row.count, batch.total_invoices)} of batch</span>
                  <span className="num text-mist-300">{formatINR(row.impact)}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

export function ExposureSection({ batch }: { batch: BatchResult }) {
  const stats = issueStats(batch.results)
  const total = exposureTotal(batch.results)
  const max = Math.max(...ISSUE_ORDER.map((key) => stats[key].impact), 1)

  return (
    <section className="surface rounded-2xl p-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="micro text-[9px] text-accent">Financial exposure</p>
          <p className="mt-1 text-sm text-mist-400">Identified billing risk</p>
          <p className="num mt-3 text-4xl tracking-[-0.05em] text-white">{formatINR(total)}</p>
        </div>
        <p className="text-right text-[10px] tracking-[0.16em] text-mist-500">{batch.flagged + batch.needs_human} EXCEPTIONS</p>
      </div>
      <div className="mt-7 space-y-4">
        {ISSUE_ORDER.map((key) => {
          const row = stats[key]
          return (
            <div key={key} className="grid grid-cols-[170px_1fr_110px] items-center gap-4">
              <p className="text-[10px] font-semibold tracking-[0.16em] text-mist-300">
                {key === 'no_contracted_rate_found' ? 'OTHER / HUMAN REVIEW' : ISSUE_LABEL[key]}
              </p>
              <div className="h-2 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent via-accent/90 to-risk"
                  style={{ width: `${(row.impact / max) * 100}%` }}
                />
              </div>
              <p className="num text-right text-sm text-white">{formatINR(row.impact)}</p>
            </div>
          )
        })}
      </div>
    </section>
  )
}
