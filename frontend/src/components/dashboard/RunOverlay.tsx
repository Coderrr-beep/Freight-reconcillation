import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

const STAGES = [
  'INITIALIZING RECONCILIATION ENGINE',
  'INGESTING RECORDS',
  'NORMALIZING DATA',
  'MATCHING CONTRACTS',
  'VERIFYING DISPATCH DATA',
  'INVESTIGATING EXCEPTIONS',
]

export function RunOverlay({ open }: { open: boolean }) {
  const [active, setActive] = useState(0)

  useEffect(() => {
    if (!open) {
      setActive(0)
      return
    }
    const id = window.setInterval(() => {
      setActive((current) => Math.min(current + 1, STAGES.length - 1))
    }, 900)
    return () => window.clearInterval(id)
  }, [open])

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="surface w-[460px] rounded-2xl px-8 py-8">
            <p className="micro text-accent">Control pipeline</p>
            <h2 className="mt-2 text-lg font-medium">Running reconciliation</h2>
            <p className="mt-1 text-sm text-mist-400">
              Deterministic proof first. AI only on unresolved cases.
            </p>
            <ol className="mt-6 space-y-3">
              {STAGES.map((stage, index) => {
                const done = index < active
                const current = index === active
                return (
                  <li key={stage} className="flex items-center gap-3 text-sm">
                    <span
                      className={`flex h-5 w-5 items-center justify-center rounded-full border text-[10px] ${
                        done
                          ? 'border-verified/40 text-verified'
                          : current
                            ? 'border-accent/50 text-accent'
                            : 'border-white/10 text-mist-500'
                      }`}
                    >
                      {done ? '✓' : current ? '●' : '○'}
                    </span>
                    <span className={done || current ? 'text-mist-100' : 'text-mist-500'}>
                      {stage}
                    </span>
                  </li>
                )
              })}
            </ol>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
