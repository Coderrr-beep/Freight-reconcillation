export type ReconciliationStatus = 'auto_clear' | 'flagged' | 'needs_human'
export type ConfidenceLevel = 'high' | 'medium' | 'low'
export type ResolvedBy = 'deterministic' | 'ai_agent'

export type EngineDiscrepancyType =
  | 'none'
  | 'rate_mismatch'
  | 'weight_variance'
  | 'duplicate_billing'
  | 'no_contracted_rate_found'
  | 'multiple_issues'

export interface ReconciliationEvidence {
  match_status: string | null
  match_method: string | null
  similarity_score: number | null
  billed_rate_per_ton: number | null
  contracted_rate_per_ton: number | null
  billed_fixed_charge: number | null
  contracted_fixed_charge: number | null
  billed_weight_tons: number | null
  dispatched_weight_tons: number | null
  weight_for_expected_amount_tons: number | null
  weight_variance_pct: number | null
  acceptable_weight_variance_pct: number | null
  expected_amount: number | null
  billed_amount: number | null
  rate_impact: number | null
  weight_impact: number | null
  duplicate_related_invoice_ids: string[]
  duplicate_reason: string | null
  match_reason: string | null
  issues_detected: string[]
}

export interface DeterministicReconciliationResult {
  invoice_id: string
  lr_number: string
  status: ReconciliationStatus
  discrepancy_type: EngineDiscrepancyType | string
  rupee_impact: number
  matched_rate_id: string | null
  checks_performed: string[]
  explanation: string
  confidence: ConfidenceLevel
  evidence: ReconciliationEvidence
}

export interface AIReconciliationEvidence {
  source: 'invoice' | 'rate_card' | 'dispatch' | 'history'
  field: string
  value: string
}

export interface AgentTraceEntry {
  tool: string
  arguments: Record<string, unknown>
  result: Record<string, unknown>
  iteration: number
}

export interface AIReconciliationResult {
  decision: 'clear' | 'flag' | 'needs_human'
  discrepancy_type: string
  reason: string
  confidence: number
  rupee_impact: number
  evidence: AIReconciliationEvidence[]
  agent_trace: AgentTraceEntry[]
}

export interface MergedInvoiceResult {
  invoice_id: string
  lr_number: string
  status: ReconciliationStatus
  discrepancy_type: string
  rupee_impact: number
  matched_rate_id: string | null
  explanation: string
  resolved_by: ResolvedBy
  deterministic_result: DeterministicReconciliationResult
  ai_result: AIReconciliationResult | null
}

export interface BatchResult {
  batch_id: string
  total_invoices: number
  auto_clear: number
  flagged: number
  needs_human: number
  results: MergedInvoiceResult[]
}

export interface Invoice {
  invoice_id: string
  lr_number: string
  transporter_name: string
  origin: string
  destination: string
  vehicle_type: string
  weight_billed_tons: number
  rate_applied_per_ton: number
  fixed_charge_applied: number
  total_amount: number
  invoice_date: string
}

export interface DispatchRecord {
  lr_number: string
  dispatched_weight_tons: number
}

export interface RateCardEntry {
  rate_id: string
  transporter: string
  origin: string
  destination: string
  vehicle_type: string
  rate_per_ton: number
  fixed_charge: number
  acceptable_weight_variance_pct: number
}

export interface SystemStatus {
  engine: string
  ai_agent: string
  version: string
}
