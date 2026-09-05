import { formatDate, formatINR, formatIssue } from '../../lib/format'
import type { DispatchRecord, Invoice, MergedInvoiceResult, RateCardEntry } from '../../types/api'
import { ConfidenceMeter, engineConfidencePct } from '../ui/ConfidenceMeter'
import { StatusBadge } from '../ui/StatusBadge'

export function InvoiceDrawerBody({
  result,
  invoice,
  dispatchRecord,
  rateCard,
}: {
  result: MergedInvoiceResult
  invoice?: Invoice
  dispatchRecord?: DispatchRecord
  rateCard?: RateCardEntry
}) {
  const evidence = result.deterministic_result.evidence
  const ai = result.ai_result
  const confidencePct = ai
    ? Math.round(ai.confidence * 100)
    : engineConfidencePct(result.deterministic_result.confidence)

  return (
    <div className="space-y-7 pr-4">
      <header className="rounded-2xl border border-white/5 bg-[#0D1219] p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="num text-[22px] tracking-[-0.04em] text-white">{result.invoice_id}</p>
            <div className="mt-3 flex items-center gap-3">
              <StatusBadge status={result.status} />
              <span className="text-[10px] tracking-[0.16em] text-mist-400">
                {formatIssue(result.discrepancy_type)}
              </span>
            </div>
          </div>
          <span className="rounded-full border border-accent/20 bg-accent/10 px-2 py-1 text-[9px] font-semibold tracking-[0.16em] text-accent">
            {result.resolved_by === 'ai_agent' ? 'AI REVIEW' : 'RULE ENGINE'}
          </span>
        </div>
        <p className="mt-4 text-sm leading-6 text-mist-200">{result.explanation}</p>
        <div className="mt-5 border-t border-white/5 pt-4">
          <p className="micro text-[9px]">Financial impact</p>
          <p className="num mt-2 text-[28px] tracking-[-0.04em] text-white">{formatINR(result.rupee_impact)}</p>
        </div>
      </header>

      <Section title="Invoice">
        <KV label="Invoice ID" value={result.invoice_id} />
        <KV label="Transporter" value={invoice?.transporter_name ?? '—'} />
        <KV
          label="Route"
          value={invoice ? `${invoice.origin} → ${invoice.destination}` : '—'}
        />
        <KV label="LR" value={result.lr_number} />
        <KV label="Invoice date" value={formatDate(invoice?.invoice_date)} />
        <KV label="Vehicle" value={invoice?.vehicle_type ?? '—'} />
      </Section>

      <Section title="Contract evidence">
        <KV label="Contract rate" value={money(evidence.contracted_rate_per_ton)} suffix="/ton" />
        <KV label="Billed rate" value={money(evidence.billed_rate_per_ton)} suffix="/ton" />
        <KV label="Expected amount" value={money(evidence.expected_amount)} />
        <KV label="Billed amount" value={money(evidence.billed_amount)} />
        <KV label="Rate card" value={result.matched_rate_id ?? 'None'} />
        {rateCard ? <KV label="Contract lane" value={`${rateCard.origin} → ${rateCard.destination}`} /> : null}
      </Section>

      <Section title="Dispatch evidence">
        <KV label="Dispatched weight" value={tons(evidence.dispatched_weight_tons ?? dispatchRecord?.dispatched_weight_tons)} />
        <KV label="Billed weight" value={tons(evidence.billed_weight_tons ?? invoice?.weight_billed_tons)} />
        <KV
          label="Variance"
          value={
            evidence.weight_variance_pct != null
              ? `${evidence.weight_variance_pct.toFixed(2)}%`
              : '—'
          }
        />
      </Section>

      {evidence.duplicate_related_invoice_ids.length > 0 ? (
        <section className="rounded-2xl border border-risk/20 bg-risk/[0.05] p-4">
          <p className="micro text-[9px] text-risk">Duplicate evidence</p>
          <div className="mt-4 flex items-center gap-3">
            <div className="min-w-0 flex-1 rounded-xl border border-risk/20 bg-black/10 px-3 py-2">
              <p className="micro text-[8px]">Invoice</p>
              <p className="num mt-1 truncate text-sm text-white">{result.invoice_id}</p>
            </div>
            <div className="h-px w-6 shrink-0 bg-risk/60" />
            <div className="min-w-0 flex-1 rounded-xl border border-risk/20 bg-black/10 px-3 py-2">
              <p className="micro text-[8px]">Related invoice</p>
              <p className="num mt-1 truncate text-sm text-white">{evidence.duplicate_related_invoice_ids.join(', ')}</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 border-t border-risk/10 pt-3">
            <KV label="Same LR" value={result.lr_number} />
            <KV label="Financial impact" value={formatINR(result.rupee_impact)} />
          </div>
          <p className="mt-3 text-xs leading-5 text-mist-300">
            {evidence.duplicate_reason ?? 'Shared LR billed more than once.'}
          </p>
        </section>
      ) : null}

      <Section title="Decision">
        <KV
          label="Deterministic check"
          value={result.deterministic_result.status === 'needs_human' ? 'INCONCLUSIVE' : result.deterministic_result.status === 'flagged' ? 'FAILED' : 'PASSED'}
        />
        <KV
          label="AI investigation"
          value={result.resolved_by === 'ai_agent' ? 'COMPLETED' : 'NOT REQUIRED'}
        />
        <div className="col-span-2 pt-2">
          <p className="micro mb-2 text-[9px]">Confidence</p>
          <ConfidenceMeter value={confidencePct} label={ai ? 'AI' : result.deterministic_result.confidence.toUpperCase()} />
        </div>
      </Section>

      <section className="rounded-2xl border border-white/5 bg-[#0D1219] p-4">
        <p className="micro text-[9px]">Reasoning</p>
        <p className="mt-3 text-sm leading-7 text-mist-200">
          {ai?.reason ?? result.explanation}
        </p>
      </section>

      <section className="rounded-2xl border border-white/5 bg-[#0D1219] p-4">
        <p className="micro text-[9px]">Evidence chain</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {['Invoice', 'Rate Card', 'Dispatch Record', ...evidence.duplicate_related_invoice_ids.map((id) => `Related ${id}`)].map(
            (item) => (
              <span
                key={item}
                className="rounded-full border border-white/10 bg-white/[0.02] px-2.5 py-1 text-[9px] tracking-[0.12em] text-mist-200"
              >
                {item}
              </span>
            ),
          )}
        </div>
      </section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-white/[0.06] pt-5">
      <p className="micro mb-4">{title}</p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-4">{children}</div>
    </section>
  )
}

function KV({ label, value, suffix }: { label: string; value: string; suffix?: string }) {
  return (
    <div>
      <p className="micro">{label}</p>
      <p className="mt-1 text-sm text-mist-100">
        {value}
        {suffix ? <span className="text-mist-500">{suffix}</span> : null}
      </p>
    </div>
  )
}

function money(value: number | null | undefined): string {
  if (value == null) return '—'
  return formatINR(value)
}

function tons(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(2)} t`
}
