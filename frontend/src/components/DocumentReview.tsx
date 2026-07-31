import { useState } from 'react'
import { decideDocument, generateCorrectionEmail, selectGlAccount, updateDocument } from '../lib/api'
import { summarizeReview } from '../lib/review-outcome'
import type { CorrectionEmailDraft, Document, GlAccount, ReviewData } from '../lib/types'
import { CorrectionEmailDialog } from './CorrectionEmailDialog'
import { DocumentReviewSection } from './DocumentReviewSection'
import { StatusBadge } from './StatusBadge'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'

interface DocumentReviewProps {
  document: Document
  accounts: GlAccount[]
  accountsLoading: boolean
  onRetryAccounts: () => void
  onChanged: (document: Document) => void
}

type EditableField = Exclude<keyof ReviewData, 'line_items' | 'field_confidence' | 'field_sources' | 'document_type' | 'expense_category'>

const fieldGroups: Array<{ title: string; fields: Array<{ key: EditableField; label: string; type?: string }> }> = [
  {
    title: 'Invoice details',
    fields: [
      { key: 'invoice_number', label: 'Invoice number' },
      { key: 'purchase_order', label: 'Purchase order' },
      { key: 'invoice_date', label: 'Invoice date', type: 'date' },
      { key: 'due_date', label: 'Due date', type: 'date' },
      { key: 'currency', label: 'Currency' },
    ],
  },
  {
    title: 'Parties and VAT',
    fields: [
      { key: 'vendor_name', label: 'Supplier' },
      { key: 'vendor_vat_id', label: 'Supplier VAT number' },
      { key: 'customer_name', label: 'Customer' },
      { key: 'customer_vat_id', label: 'Customer VAT number' },
    ],
  },
  {
    title: 'Amounts',
    fields: [
      { key: 'subtotal', label: 'Subtotal', type: 'number' },
      { key: 'total_tax', label: 'VAT total', type: 'number' },
      { key: 'invoice_total', label: 'Invoice total', type: 'number' },
      { key: 'amount_due', label: 'Amount due', type: 'number' },
    ],
  },
]

const receiptFieldGroups: typeof fieldGroups = [
  {
    title: 'Receipt details',
    fields: [
      { key: 'vendor_name', label: 'Merchant' },
      { key: 'invoice_date', label: 'Transaction date', type: 'date' },
      { key: 'currency', label: 'Currency' },
    ],
  },
  {
    title: 'Amounts and VAT',
    fields: [
      { key: 'subtotal', label: 'Subtotal', type: 'number' },
      { key: 'total_tax', label: 'VAT total', type: 'number' },
      { key: 'invoice_total', label: 'Receipt total', type: 'number' },
      { key: 'amount_due', label: 'Amount paid', type: 'number' },
    ],
  },
]

function shown(value: string | null | undefined): string {
  return value?.trim() || 'Not found'
}

function formattedAmount(value: string | null | undefined, currency: string | null | undefined): string {
  if (!value) return 'Not found'
  const amount = Number(value)
  if (!Number.isFinite(amount)) return `${currency ?? ''} ${value}`.trim()
  try {
    return new Intl.NumberFormat('en-NL', { style: 'currency', currency: currency ?? 'EUR' }).format(amount)
  } catch {
    return `${currency ?? ''} ${value}`.trim()
  }
}

function categoryLabel(value: string | null | undefined): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : 'Not found'
}

export function DocumentReview({ document, accounts, accountsLoading, onRetryAccounts, onChanged }: DocumentReviewProps) {
  const [draft, setDraft] = useState<ReviewData | null>(document.review_data)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<'save' | 'account' | 'approved' | 'rejected' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [emailOpen, setEmailOpen] = useState(false)
  const [emailLoading, setEmailLoading] = useState(false)
  const [emailDraft, setEmailDraft] = useState<CorrectionEmailDraft | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)
  const locked = document.status === 'approved' || document.status === 'rejected'
  const hasErrors = document.issues.some((issue) => issue.severity === 'error')
  const selectedAccount = document.accounting_coding?.selected_gl_account_code ?? ''
  const outcome = summarizeReview(document.status, document.issues)
  const outcomeStyle = {
    passed: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    attention: 'border-amber-200 bg-amber-50 text-amber-950',
    failed: 'border-red-200 bg-red-50 text-red-950',
  }[outcome.kind]
  const outcomeBadge = {
    passed: 'success',
    attention: 'warning',
    failed: 'destructive',
  }[outcome.kind] as 'success' | 'warning' | 'destructive'
  const isReceipt = document.review_data?.document_type === 'receipt'
  const documentLabel = isReceipt ? 'receipt' : 'invoice'
  const summary = isReceipt ? [
    { key: 'vendor_name', label: 'Merchant', value: shown(document.review_data?.vendor_name) },
    { key: 'expense_category', label: 'Expense category', value: categoryLabel(document.review_data?.expense_category) },
    { key: 'invoice_date', label: 'Transaction date', value: shown(document.review_data?.invoice_date) },
    { key: 'invoice_total', label: 'Receipt total', value: formattedAmount(document.review_data?.invoice_total, document.review_data?.currency) },
    { key: 'total_tax', label: 'VAT total', value: formattedAmount(document.review_data?.total_tax, document.review_data?.currency) },
    { key: 'subtotal', label: 'Subtotal', value: formattedAmount(document.review_data?.subtotal, document.review_data?.currency) },
    { key: 'currency', label: 'Currency', value: shown(document.review_data?.currency) },
    { key: 'amount_due', label: 'Amount paid', value: formattedAmount(document.review_data?.amount_due, document.review_data?.currency) },
  ] : [
    { key: 'vendor_name', label: 'Supplier', value: shown(document.review_data?.vendor_name) },
    { key: 'invoice_number', label: 'Invoice number', value: shown(document.review_data?.invoice_number) },
    { key: 'invoice_date', label: 'Invoice date', value: shown(document.review_data?.invoice_date) },
    { key: 'due_date', label: 'Due date', value: shown(document.review_data?.due_date) },
    { key: 'invoice_total', label: 'Invoice total', value: formattedAmount(document.review_data?.invoice_total, document.review_data?.currency) },
    { key: 'purchase_order', label: 'Purchase order', value: shown(document.review_data?.purchase_order) },
    { key: 'vendor_vat_id', label: 'Supplier VAT number', value: shown(document.review_data?.vendor_vat_id) },
    { key: 'customer_vat_id', label: 'Customer VAT number', value: shown(document.review_data?.customer_vat_id) },
  ]

  function change(key: EditableField, value: string) {
    setDraft((current) => current ? { ...current, [key]: value || null } : current)
    setDirty(true)
  }

  async function save() {
    if (!draft) return
    setBusy('save')
    setError(null)
    try {
      const changed = await updateDocument(document.id, draft)
      setDraft(changed.review_data)
      setDirty(false)
      onChanged(changed)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save the correction.')
    } finally {
      setBusy(null)
    }
  }

  async function decide(decision: 'approved' | 'rejected') {
    setBusy(decision)
    setError(null)
    try {
      onChanged(await decideDocument(document.id, decision))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save the decision.')
    } finally {
      setBusy(null)
    }
  }

  async function chooseAccount(glAccountCode: string) {
    if (!glAccountCode) return
    setBusy('account')
    setError(null)
    try {
      onChanged(await selectGlAccount(document.id, glAccountCode))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save the GL account.')
    } finally {
      setBusy(null)
    }
  }

  async function draftCorrectionEmail() {
    setEmailOpen(true)
    setEmailLoading(true)
    setEmailDraft(null)
    setEmailError(null)
    try {
      setEmailDraft(await generateCorrectionEmail(document.id))
    } catch (reason) {
      setEmailError(reason instanceof Error ? reason.message : 'Could not draft the correction email.')
    } finally {
      setEmailLoading(false)
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-100 px-6 py-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-zinc-500">{document.original_filename}</p>
            <Badge variant="secondary">{isReceipt ? 'Receipt' : 'Invoice'}</Badge>
            {isReceipt && document.review_data?.expense_category && <Badge variant="secondary">{categoryLabel(document.review_data.expense_category)}</Badge>}
          </div>
          <h2 className="mt-1 text-lg font-semibold">{document.review_data?.vendor_name ?? 'Extraction failed'}</h2>
        </div>
        <StatusBadge status={document.status} />
      </div>

      <div className="space-y-8 p-6 sm:p-8">
        <section className={`rounded-xl border p-5 ${outcomeStyle}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-lg font-semibold">{outcome.title}</p>
              <p className="mt-1 text-sm leading-6 opacity-80">{outcome.description}</p>
            </div>
            <div className="flex gap-2">
              {outcome.errorCount > 0 && <Badge variant="destructive">{outcome.errorCount} {outcome.errorCount === 1 ? 'error' : 'errors'}</Badge>}
              {outcome.warningCount > 0 && <Badge variant="warning">{outcome.warningCount} {outcome.warningCount === 1 ? 'warning' : 'warnings'}</Badge>}
              {outcome.errorCount === 0 && outcome.warningCount === 0 && <Badge variant={outcomeBadge}>{outcome.kind === 'failed' ? 'Failed' : 'Passed'}</Badge>}
            </div>
          </div>
        </section>

        {document.error_message && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{document.error_message}</div>
        )}

        {document.review_data && (
          <section>
            <div>
              <h3 className="text-base font-semibold text-zinc-900">{isReceipt ? 'Receipt summary' : 'Invoice summary'}</h3>
              <p className="mt-1 text-sm text-zinc-500">The combined values used for this {documentLabel} review.</p>
            </div>
            <dl className="mt-4 grid overflow-hidden rounded-xl border border-zinc-200 sm:grid-cols-2 lg:grid-cols-4">
              {summary.map((item) => (
                <div key={item.key} className="border-b border-zinc-100 p-4 last:border-b-0 sm:border-r sm:[&:nth-last-child(-n+2)]:border-b-0 sm:[&:nth-child(2n)]:border-r-0 lg:[&:nth-last-child(-n+4)]:border-b-0 lg:[&:nth-child(2n)]:border-r lg:[&:nth-child(4n)]:border-r-0">
                  <dt className="text-xs font-medium text-zinc-500">{item.label}</dt>
                  <dd className="mt-1 break-words text-sm font-medium text-zinc-900">{item.value}</dd>
                  {document.review_data?.field_sources?.[item.key] === 'llm_fallback' && <Badge variant="secondary" className="mt-2">LLM fallback</Badge>}
                  {document.review_data?.field_sources?.[item.key] === 'human' && <Badge variant="secondary" className="mt-2">Human correction</Badge>}
                </div>
              ))}
            </dl>
          </section>
        )}

        <section className="border-t border-zinc-100 pt-7">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-base font-semibold text-zinc-900">Automatic checks</h3>
              <p className="mt-1 text-sm text-zinc-500">Deterministic {documentLabel} rules decide whether this review can be approved.</p>
            </div>
            <Badge variant={outcomeBadge}>{document.issues.length} {document.issues.length === 1 ? 'issue' : 'issues'}</Badge>
          </div>

          {document.issues.length ? (
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {document.issues.map((issue) => (
                <li key={`${issue.code}-${issue.field}`} className={`rounded-lg border p-3 text-sm ${issue.severity === 'error' ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
                  <span className="font-semibold capitalize">{issue.severity}:</span> {issue.message}
                </li>
              ))}
            </ul>
          ) : document.status !== 'failed' && (
            <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">No issues were found.</p>
          )}
        </section>

        {document.status !== 'failed' && document.supplier_action_required && (
          <section className="flex flex-col gap-4 rounded-xl border border-zinc-200 bg-zinc-50 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-zinc-900">Supplier action needed</h3>
              <p className="mt-1 text-sm leading-6 text-zinc-600">Turn the business issues into a correction request you can copy into email.</p>
            </div>
            <Button variant="outline" onClick={() => void draftCorrectionEmail()}>Draft correction email</Button>
          </section>
        )}

        {document.document_review && <DocumentReviewSection review={document.document_review} />}

        {document.status !== 'failed' && (
          <section className="border-t border-zinc-100 pt-7">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-zinc-900">General ledger account</h3>
                  <p className="mt-1 text-sm text-zinc-500">Azure OpenAI suggests an account. You can override it.</p>
                </div>
                {document.accounting_coding?.suggestion && <Badge variant="secondary">{Math.round(document.accounting_coding.suggestion.confidence * 100)}% confidence</Badge>}
              </div>

              {document.accounting_coding?.suggestion && (
                <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm">
                  <p className="font-medium">Suggested: {document.accounting_coding.suggestion.gl_account_code} · {document.accounting_coding.suggestion.category}</p>
                  <p className="mt-2 leading-6 text-zinc-600">{document.accounting_coding.suggestion.rationale}</p>
                </div>
              )}
              {document.accounting_coding?.error_message && <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">AI suggestion unavailable: {document.accounting_coding.error_message} Choose an account manually to continue.</p>}

              {!accountsLoading && accounts.length === 0 && (
                <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <span>GL accounts could not be loaded.</span>
                  <Button variant="outline" size="sm" onClick={onRetryAccounts}>Retry</Button>
                </div>
              )}

              <label className="mt-4 block text-sm font-medium text-zinc-800">
                Final GL account
                <select
                  value={selectedAccount}
                  disabled={locked || busy !== null || accountsLoading || accounts.length === 0}
                  onChange={(event) => void chooseAccount(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-zinc-500 focus:ring-2 focus:ring-zinc-200 disabled:bg-zinc-100"
                >
                  <option value="">Select an account…</option>
                  {accounts.map((account) => <option key={account.code} value={account.code}>{account.code} · {account.name}</option>)}
                </select>
              </label>
              {document.accounting_coding?.overridden && <p className="mt-2 text-xs font-medium text-zinc-600">Reviewer override saved.</p>}
          </section>
        )}

        {draft && (
          <section className="border-t border-zinc-100 pt-7">
            <h3 className="text-base font-semibold text-zinc-900">Review extracted fields</h3>
            <p className="mt-1 text-sm text-zinc-500">Correct anything that Azure read incorrectly, then rerun the checks.</p>
            <form onSubmit={(event) => { event.preventDefault(); void save() }} className="mt-6 space-y-7">
              {(isReceipt ? receiptFieldGroups : fieldGroups).map((group) => (
                <fieldset key={group.title} disabled={locked || busy !== null}>
                  <legend className="text-sm font-medium text-zinc-900">{group.title}</legend>
                  <div className="mt-3 grid gap-4 sm:grid-cols-2">
                    {group.fields.map((field) => (
                      <label key={field.key} className="block text-sm font-medium text-zinc-700">
                        {field.label}
                        <input
                          type={field.type ?? 'text'}
                          step={field.type === 'number' ? '0.01' : undefined}
                          value={String(draft[field.key] ?? '')}
                          onChange={(event) => change(field.key, event.target.value)}
                          className="mt-1.5 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-zinc-500 focus:ring-2 focus:ring-zinc-200 disabled:bg-zinc-100 disabled:text-zinc-500"
                        />
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}

              {!locked && (
                <Button type="submit" disabled={busy !== null} variant="outline">
                  {busy === 'save' ? 'Rechecking…' : 'Save and rerun checks'}
                </Button>
              )}
            </form>
          </section>
        )}

        {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</div>}

        {!locked && document.status !== 'failed' && document.status !== 'processing' && (
          <div className="border-t border-zinc-100 pt-6">
            {dirty && <p className="mb-3 text-right text-sm text-amber-700">Save and rerun the checks before making a decision.</p>}
            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <Button disabled={busy !== null || dirty} onClick={() => void decide('rejected')} variant="destructive" className="sm:min-w-28">
                {busy === 'rejected' ? 'Rejecting…' : 'Reject'}
              </Button>
              <Button variant="success" disabled={busy !== null || dirty || hasErrors || !selectedAccount} onClick={() => void decide('approved')} title={dirty ? 'Save field changes before approval' : hasErrors ? 'Resolve validation errors before approval' : !selectedAccount ? 'Select a GL account before approval' : undefined} className="sm:min-w-28">
                {busy === 'approved' ? 'Approving…' : 'Approve'}
              </Button>
            </div>
          </div>
        )}
      </div>
      {emailOpen && <CorrectionEmailDialog open draft={emailDraft} loading={emailLoading} error={emailError} onClose={() => setEmailOpen(false)} />}
    </div>
  )
}
