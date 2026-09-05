import { motion } from 'framer-motion'
import { Database, GitMerge, ScanSearch, ShieldCheck, Sparkles, Scale } from 'lucide-react'
import type { BatchResult } from '../../types/api'

export function ControlPipeline({ batch }: { batch: BatchResult }) {
  const stages = [
    { n: '01', label: 'INGEST', icon: Database, detail: `${batch.total_invoices} records`, glow: false },
    { n: '02', label: 'NORMALIZE', icon: GitMerge, detail: `${batch.total_invoices} records`, glow: false },
    { n: '03', label: 'MATCH', icon: ScanSearch, detail: `${batch.total_invoices} records`, glow: false },
    { n: '04', label: 'VERIFY', icon: ShieldCheck, detail: `${batch.total_invoices} records`, glow: false },
    { n: '05', label: 'INVESTIGATE', icon: Sparkles, detail: `${batch.needs_human} cases`, glow: true },
    { n: '06', label: 'DECIDE', icon: Scale, detail: `${batch.total_invoices} decisions`, glow: false },
  ]

  return (
    <section className="surface rounded-2xl p-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="micro text-[9px] text-accent">Control pipeline</p>
          <h3 className="mt-2 text-lg font-medium tracking-[-0.03em] text-white">Processing architecture</h3>
        </div>
        <p className="hidden text-[10px] tracking-[0.14em] text-mist-500 sm:block">DETERMINISTIC → AI → DECISION</p>
      </div>
      <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-stretch">
        {stages.map((stage, index) => (
          <motion.div
            key={stage.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06, duration: 0.28 }}
            className="flex flex-1 items-center gap-3"
          >
            <motion.div
              whileHover={{ y: -2 }}
              className={`flex flex-1 flex-col items-start rounded-xl border px-3 py-3 ${
                stage.glow
                  ? 'border-accent/20 bg-accent/[0.08] shadow-[0_0_0_1px_rgba(124,108,255,0.12),0_0_28px_rgba(124,108,255,0.14)]'
                  : 'border-white/5 bg-black/10'
              }`}
            >
              <div className="flex w-full items-center justify-between gap-2">
                <stage.icon className={`h-4 w-4 ${stage.glow ? 'text-accent' : 'text-mist-400'}`} />
                <span className="micro text-[8px] text-mist-500">{stage.n}</span>
              </div>
              <p className="mt-3 text-[10px] font-semibold tracking-[0.16em] text-white">
                {stage.glow ? '✦ ' : '✓ '}
                {stage.label}
              </p>
              <p className="mt-1 text-[10px] text-mist-400">{stage.detail}</p>
            </motion.div>
            {index < stages.length - 1 ? (
              <div className="hidden h-px w-6 shrink-0 bg-gradient-to-r from-verified/35 via-white/10 to-white/5 lg:block" />
            ) : null}
          </motion.div>
        ))}
      </div>
    </section>
  )
}
