import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, api } from '../api/client'
import type { BatchResult, DispatchRecord, Invoice, RateCardEntry, SystemStatus } from '../types/api'
import { useToast } from './useToast'

interface SessionValue {
  status: SystemStatus | null
  invoices: Invoice[]
  dispatchRecords: DispatchRecord[]
  rateCards: RateCardEntry[]
  batch: BatchResult | null
  loading: boolean
  running: boolean
  error: string | null
  connected: boolean | null
  runReconciliation: () => Promise<void>
  refresh: () => Promise<void>
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const { push } = useToast()
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [dispatchRecords, setDispatchRecords] = useState<DispatchRecord[]>([])
  const [rateCards, setRateCards] = useState<RateCardEntry[]>([])
  const [batch, setBatch] = useState<BatchResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connected, setConnected] = useState<boolean | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sys, inv, dispatch, rates] = await Promise.all([
        api.status(),
        api.invoices(),
        api.dispatchRecords(),
        api.rateCards(),
      ])
      setStatus(sys)
      setInvoices(inv)
      setDispatchRecords(dispatch)
      setRateCards(rates)
      setConnected(true)
      try {
        const latest = await api.latestBatch()
        setBatch(latest)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setBatch(null)
        } else {
          throw err
        }
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Reconciliation engine unavailable'
      setConnected(false)
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const runReconciliation = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      const result = await api.runBatch()
      setBatch(result)
      setConnected(true)
      push({
        kind: 'ok',
        title: 'Reconciliation complete',
        body: `${result.total_invoices} invoices decided`,
      })
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Reconciliation engine unavailable'
      setError(message)
      setConnected(false)
      push({ kind: 'err', title: 'Run failed', body: message })
    } finally {
      setRunning(false)
    }
  }, [push])

  const value = useMemo<SessionValue>(
    () => ({
      status,
      invoices,
      dispatchRecords,
      rateCards,
      batch,
      loading,
      running,
      error,
      connected,
      runReconciliation,
      refresh,
    }),
    [
      status,
      invoices,
      dispatchRecords,
      rateCards,
      batch,
      loading,
      running,
      error,
      connected,
      runReconciliation,
      refresh,
    ],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}
