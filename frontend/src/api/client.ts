import type { BatchResult, DispatchRecord, Invoice, RateCardEntry, SystemStatus } from '../types/api'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
      signal: controller.signal,
    })

    if (!response.ok) {
      let detail = `Request failed (${response.status})`
      try {
        const body = (await response.json()) as { detail?: string }
        if (body.detail) detail = body.detail
      } catch {
        /* ignore parse errors */
      }
      throw new ApiError(response.status, detail)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, 'Request timed out')
    }
    throw new ApiError(0, 'Reconciliation engine unavailable')
  } finally {
    window.clearTimeout(timer)
  }
}

export const api = {
  health: () => request<{ status: string }>('/api/health', {}, 4000),
  status: () => request<SystemStatus>('/api/status', {}, 4000),
  invoices: () => request<Invoice[]>('/api/invoices'),
  dispatchRecords: () => request<DispatchRecord[]>('/api/dispatch-records'),
  rateCards: () => request<RateCardEntry[]>('/api/rate-cards'),
  latestBatch: () => request<BatchResult>('/api/batches/latest'),
  getBatch: (batchId: string) => request<BatchResult>(`/api/batches/${batchId}`),
  runBatch: () => request<BatchResult>('/api/batches', { method: 'POST' }, 180000),
}
