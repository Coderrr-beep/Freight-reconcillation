import type { MergedInvoiceResult } from '../types/api'
import { primaryIssue } from './format'

export type IssueKey =
  | 'rate_mismatch'
  | 'weight_variance'
  | 'duplicate_billing'
  | 'no_contracted_rate_found'

export const ISSUE_ORDER: IssueKey[] = [
  'rate_mismatch',
  'weight_variance',
  'duplicate_billing',
  'no_contracted_rate_found',
]

export const ISSUE_LABEL: Record<IssueKey, string> = {
  rate_mismatch: 'RATE MISMATCH',
  weight_variance: 'WEIGHT VARIANCE',
  duplicate_billing: 'DUPLICATE BILLING',
  no_contracted_rate_found: 'NO CONTRACT',
}

/** Presentation aggregates of backend-provided rupee_impact — no formula recompute. */
export function exposureTotal(results: MergedInvoiceResult[]): number {
  return results
    .filter((row) => row.status !== 'auto_clear')
    .reduce((sum, row) => sum + row.rupee_impact, 0)
}

export function issueStats(results: MergedInvoiceResult[]) {
  const stats: Record<IssueKey, { count: number; impact: number }> = {
    rate_mismatch: { count: 0, impact: 0 },
    weight_variance: { count: 0, impact: 0 },
    duplicate_billing: { count: 0, impact: 0 },
    no_contracted_rate_found: { count: 0, impact: 0 },
  }

  for (const row of results) {
    const issue = primaryIssue(
      row.discrepancy_type,
      row.deterministic_result.evidence.issues_detected,
    )
    if (issue in stats) {
      const key = issue as IssueKey
      stats[key].count += 1
      stats[key].impact += row.rupee_impact
    }
  }

  return stats
}

export function exceptionRows(results: MergedInvoiceResult[]): MergedInvoiceResult[] {
  return results
    .filter((row) => row.status !== 'auto_clear')
    .slice()
    .sort((a, b) => b.rupee_impact - a.rupee_impact)
}

export function aiCases(results: MergedInvoiceResult[]): MergedInvoiceResult[] {
  return results.filter((row) => row.resolved_by === 'ai_agent' || row.ai_result !== null)
}
