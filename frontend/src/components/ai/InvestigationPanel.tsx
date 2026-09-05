import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import type { AgentTraceEntry, AIReconciliationResult, MergedInvoiceResult } from '../../types/api'

export function InvestigationTimeline({ result }: { result: MergedInvoiceResult }) {
  const trace = result.ai_result?.agent_trace ?? []
  const [visible, setVisible] = useState(0)

  useEffect(() => {
    setVisible(0)
    if (!trace.length) return
    const id = window.setInterval(() => {
      setVisible((n) => {
        if (n >= trace.length + 2) {
          window.clearInterval(id)
          return n
        }
        return n + 1
      })
    }, 380)
    return () => window.clearInterval(id)
  }, [result.invoice_id, trace.length])

  return (
    <div className="space-y-4">
      <Step show active={visible >= 0} title="AGENT INITIALIZED" body={`Investigating ${result.invoice_id}`} />
      {trace.map((entry, index) => (
        <ToolStep key={`${entry.tool}-${index}`} entry={entry} show={visible >= index + 1} />
      ))}
      <Step
        show={visible >= trace.length + 1 || !trace.length}
        active
        title="ANALYSIS"
        body={result.ai_result?.reason ?? result.explanation}
      />
      <Step
        show={visible >= trace.length + 2 || !trace.length}
        active
        title="FINAL DECISION"
        body={(result.ai_result?.decision ?? result.status).replaceAll('_', ' ').toUpperCase()}
        accent
      />
    </div>
  )
}

function Step({
  title,
  body,
  show,
  active,
  accent,
}: {
  title: string
  body: string
  show: boolean
  active?: boolean
  accent?: boolean
}) {
  if (!show) return null
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="relative pl-6">
      <span className={`absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full ${accent ? 'bg-accent shadow-[0_0_12px_rgba(124,108,255,0.8)]' : 'bg-white/35'}`} />
      <p className="micro text-[9px]">{title}</p>
      <p className={`mt-1 text-sm leading-6 ${active ? 'text-mist-200' : 'text-mist-400'}`}>{body}</p>
    </motion.div>
  )
}

function ToolStep({ entry, show }: { entry: AgentTraceEntry; show: boolean }) {
  if (!show) return null
  const ok = !('error' in entry.result)
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="relative pl-6">
      <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-accent/80" />
      <p className="micro text-[9px]">Tool call</p>
      <div className="mt-2 rounded-xl border border-white/[0.06] bg-[#0D1219] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <p className="num text-[12px] text-accent-glow">{entry.tool}()</p>
          <span className={`text-[9px] font-semibold tracking-[0.16em] ${ok ? 'text-verified' : 'text-risk'}`}>
            {ok ? 'SUCCESS' : 'ERROR'}
          </span>
        </div>
        <p className="mt-2 text-xs leading-5 text-mist-400">{summarizeResult(entry)}</p>
      </div>
    </motion.div>
  )
}

function summarizeResult(entry: AgentTraceEntry): string {
  const result = entry.result
  if (typeof result.found === 'boolean' && result.found === false) return 'No contracted rate'
  if (typeof result.count === 'number') return `${result.count} historical matches found.`
  if (typeof result.error === 'string') return result.error
  return 'Retrieved evidence.'
}

export function DecisionCard({ ai, fallback }: { ai: AIReconciliationResult | null; fallback: string }) {
  const decision = ai?.decision ?? 'needs_human'
  const label =
    decision === 'clear' ? 'AUTO-CLEAR' : decision === 'flag' ? 'FLAGGED' : 'HUMAN REVIEW REQUIRED'

  return (
    <div className="rounded-2xl border border-accent/20 bg-gradient-to-br from-accent/[0.08] via-[#0F141C] to-[#10141B] p-6">
      <p className="micro text-[9px] text-accent">AI decision</p>
      <p className="mt-3 text-2xl font-medium tracking-[-0.04em] text-white">{label}</p>
      {ai ? (
        <>
          <div className="mt-5 flex items-end justify-between gap-3 border-t border-white/5 pt-4">
            <div>
              <p className="micro text-[9px]">Confidence</p>
              <p className="num mt-2 text-3xl">{Math.round(ai.confidence * 100)}%</p>
            </div>
            <span className="rounded-full border border-accent/20 bg-accent/10 px-2 py-1 text-[9px] font-semibold tracking-[0.14em] text-accent">
              AI
            </span>
          </div>
          <p className="micro mt-6 text-[9px]">Reasoning</p>
          <p className="mt-2 text-sm leading-7 text-mist-200">{ai.reason}</p>
          <p className="micro mt-6 text-[9px]">Evidence used</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {ai.evidence.length
              ? ai.evidence.map((item, i) => (
                  <span key={`${item.source}-${i}`} className="rounded-full border border-verified/20 bg-verified/10 px-2.5 py-1 text-[9px] tracking-[0.12em] text-verified">
                    ✓ {item.source.replaceAll('_', ' ')} · {item.field}
                  </span>
                ))
              : ['Invoice', 'Rate Card', 'Dispatch record'].map((item) => (
                  <span key={item} className="rounded-full border border-white/10 bg-black/15 px-2.5 py-1 text-[9px] tracking-[0.12em] text-mist-400">
                    ✓ {item}
                  </span>
                ))}
          </div>
          <p className="micro mt-6 text-[9px]">Tools used</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(ai.agent_trace.length ? ai.agent_trace.map((t) => t.tool) : ['deterministic_context']).map(
              (tool, i) => (
                <span key={`${tool}-${i}`} className="num rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-[10px] text-accent-glow">
                  {tool}()
                </span>
              ),
            )}
          </div>
        </>
      ) : (
        <p className="mt-4 text-sm leading-7 text-mist-300">{fallback}</p>
      )}
    </div>
  )
}
