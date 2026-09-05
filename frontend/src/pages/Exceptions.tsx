import { useMemo, useState } from 'react'
import { ExceptionsList } from '../components/reconciliation/ExceptionsList'
import { InvoiceDrawerBody } from '../components/reconciliation/InvoiceDrawer'
import { Drawer } from '../components/ui/Drawer'
import { EmptyState } from '../components/ui/EmptyState'
import { useSession } from '../hooks/useSession'
import type { MergedInvoiceResult } from '../types/api'

export function Exceptions() {
  const { batch, invoices, dispatchRecords, rateCards, connected, error, refresh } = useSession()
  const [selected, setSelected] = useState<MergedInvoiceResult | null>(null)

  const invoice = useMemo(
    () => invoices.find((item) => item.invoice_id === selected?.invoice_id),
    [invoices, selected],
  )
  const dispatch = useMemo(
    () => dispatchRecords.find((item) => item.lr_number === selected?.lr_number),
    [dispatchRecords, selected],
  )
  const rate = useMemo(
    () => rateCards.find((item) => item.rate_id === selected?.matched_rate_id),
    [rateCards, selected],
  )

  if (connected === false) {
    return (
      <EmptyState
        title="Reconciliation engine unavailable"
        body={error ?? 'Cannot load exceptions.'}
        actionLabel="Retry Connection"
        onAction={() => void refresh()}
      />
    )
  }

  if (!batch) {
    return <EmptyState title="No exceptions yet" body="Run a batch to rank discrepancies by financial impact." />
  }

  return (
    <div>
      <p className="text-sm text-mist-400">Every unresolved discrepancy, ranked by financial impact.</p>
      <div className="mt-6">
        <ExceptionsList results={batch.results} invoices={invoices} onSelect={setSelected} />
      </div>
      <Drawer open={Boolean(selected)} onClose={() => setSelected(null)}>
        {selected ? (
          <InvoiceDrawerBody result={selected} invoice={invoice} dispatchRecord={dispatch} rateCard={rate} />
        ) : null}
      </Drawer>
    </div>
  )
}
