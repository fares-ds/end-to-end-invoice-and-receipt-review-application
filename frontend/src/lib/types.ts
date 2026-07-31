export type DocumentStatus =
  | 'processing'
  | 'ready'
  | 'needs_review'
  | 'approved'
  | 'rejected'
  | 'failed'

export type IssueSeverity = 'error' | 'warning'
export type DocumentType = 'invoice' | 'receipt'
export type ExpenseCategory = 'fuel' | 'meals' | 'travel' | 'supplies' | 'other'
export type FieldSource = 'document_intelligence' | 'llm_fallback' | 'human'

export interface ReviewLineItem {
  description: string | null
  quantity: string | null
  unit_price: string | null
  amount: string | null
}

export interface ReviewData {
  document_type: DocumentType
  expense_category: ExpenseCategory | null
  vendor_name: string | null
  vendor_vat_id: string | null
  customer_name: string | null
  customer_vat_id: string | null
  invoice_number: string | null
  purchase_order: string | null
  invoice_date: string | null
  due_date: string | null
  currency: string | null
  subtotal: string | null
  total_tax: string | null
  invoice_total: string | null
  amount_due: string | null
  line_items: ReviewLineItem[]
  field_confidence: Record<string, number>
  field_sources: Record<string, FieldSource>
}

export interface ValidationIssue {
  code: string
  field: string | null
  severity: IssueSeverity
  message: string
}

export interface GlAccount {
  code: string
  name: string
  description: string
}

export interface AccountingSuggestion {
  gl_account_code: string
  category: string
  rationale: string
  confidence: number
}

export interface AccountingCoding {
  suggestion: AccountingSuggestion | null
  selected_gl_account_code: string | null
  overridden: boolean
  error_message: string | null
}

export type ComparisonStatus =
  | 'match'
  | 'different'
  | 'missing_in_llm'
  | 'missing_in_document_intelligence'
  | 'missing_in_both'

export interface LlmDocumentExtraction {
  document_type: DocumentType | 'unsupported'
  expense_category: ExpenseCategory | null
  vendor_name: string | null
  vendor_vat_id: string | null
  customer_name: string | null
  customer_vat_id: string | null
  invoice_number: string | null
  purchase_order: string | null
  invoice_date: string | null
  due_date: string | null
  currency: string | null
  subtotal: string | null
  total_tax: string | null
  invoice_total: string | null
  amount_due: string | null
  summary: string
}

export interface FieldComparison {
  field: string
  label: string
  status: ComparisonStatus
  document_intelligence_value: string | null
  llm_value: string | null
}

export interface DocumentReviewArtifact {
  extraction: LlmDocumentExtraction | null
  comparisons: FieldComparison[]
  fallback_fields: FieldComparison[]
  error_message: string | null
}

export interface CorrectionEmailDraft {
  recipient_name: string
  subject: string
  body: string
}

export interface Document {
  id: string
  original_filename: string
  content_type: string
  status: DocumentStatus
  classification: Record<string, unknown> | null
  extraction: Record<string, unknown> | null
  validation: Record<string, unknown> | null
  gl_suggestion: Record<string, unknown> | null
  review_data: ReviewData | null
  document_review: DocumentReviewArtifact | null
  accounting_coding: AccountingCoding | null
  issues: ValidationIssue[]
  supplier_action_required: boolean
  error_message: string | null
  created_at: string
  updated_at: string
}
