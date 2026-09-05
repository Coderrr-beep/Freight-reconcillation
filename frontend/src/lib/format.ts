export function formatINR(value: number | null | undefined): string {
  const amount = value ?? 0
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value)
}

export function formatPct(part: number, total: number): string {
  if (!total) return '0.0%'
  return `${((part / total) * 100).toFixed(1)}%`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function formatIssue(type: string): string {
  const labels: Record<string, string> = {
    none: 'NONE',
    rate_mismatch: 'RATE MISMATCH',
    weight_variance: 'WEIGHT VARIANCE',
    duplicate_billing: 'DUPLICATE BILLING',
    no_contracted_rate_found: 'NO CONTRACT',
    multiple_issues: 'MULTIPLE ISSUES',
    ai_agent_unavailable: 'AI UNAVAILABLE',
    ai_response_invalid: 'AI INVALID',
    ai_result_validation_failed: 'AI VALIDATION',
  }
  return labels[type] ?? type.replaceAll('_', ' ').toUpperCase()
}

export function primaryIssue(type: string, issues: string[]): string {
  if (type && type !== 'none' && type !== 'multiple_issues') return type
  if (issues.includes('duplicate_billing')) return 'duplicate_billing'
  if (issues.includes('rate_mismatch')) return 'rate_mismatch'
  if (issues.includes('weight_variance')) return 'weight_variance'
  if (issues.includes('no_contracted_rate_found')) return 'no_contracted_rate_found'
  return type || 'none'
}
