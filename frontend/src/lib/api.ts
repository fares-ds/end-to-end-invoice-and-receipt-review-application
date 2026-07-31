import { apiBaseUrl } from './env'
import type { CorrectionEmailDraft, Document, GlAccount, ReviewData } from './types'

export class UnauthorizedError extends Error {
  constructor(message = 'Authentication required') {
    super(message)
    this.name = 'UnauthorizedError'
  }
}

export interface AuthSession {
  auth_enabled: boolean
  authenticated: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: 'include',
  })
  if (response.status === 401) {
    throw new UnauthorizedError()
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string' && body.detail) {
        message = body.detail
      }
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new Error(message)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export function getAuthSession(): Promise<AuthSession> {
  return request<AuthSession>('/api/auth/session')
}

export function login(password: string): Promise<AuthSession> {
  return request<AuthSession>('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export function logout(): Promise<AuthSession> {
  return request<AuthSession>('/api/auth/logout', { method: 'POST' })
}

export function listDocuments(): Promise<Document[]> {
  return request<Document[]>('/api/documents')
}

export function getDocument(id: string): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}`)
}

export function uploadDocument(file: File): Promise<Document> {
  const body = new FormData()
  body.append('file', file)
  return request<Document>('/api/documents', { method: 'POST', body })
}

export function listGlAccounts(): Promise<GlAccount[]> {
  return request<GlAccount[]>('/api/accounting/gl-accounts')
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function selectGlAccount(id: string, glAccountCode: string): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}/accounting`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gl_account_code: glAccountCode }),
  })
}

export function updateDocument(id: string, data: ReviewData): Promise<Document> {
  const {
    vendor_name,
    vendor_vat_id,
    customer_name,
    customer_vat_id,
    invoice_number,
    purchase_order,
    invoice_date,
    due_date,
    currency,
    subtotal,
    total_tax,
    invoice_total,
    amount_due,
  } = data
  return request<Document>(`/api/documents/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      vendor_name,
      vendor_vat_id,
      customer_name,
      customer_vat_id,
      invoice_number,
      purchase_order,
      invoice_date,
      due_date,
      currency,
      subtotal,
      total_tax,
      invoice_total,
      amount_due,
    }),
  })
}

export function decideDocument(id: string, decision: 'approved' | 'rejected'): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}

export function generateCorrectionEmail(id: string): Promise<CorrectionEmailDraft> {
  return request<CorrectionEmailDraft>(
    `/api/documents/${encodeURIComponent(id)}/correction-email`,
    { method: 'POST' },
  )
}

export function documentFileUrl(id: string): string {
  return `${apiBaseUrl}/api/documents/${encodeURIComponent(id)}/file`
}
