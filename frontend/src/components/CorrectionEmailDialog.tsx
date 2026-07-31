import { useState } from 'react'
import type { CorrectionEmailDraft } from '../lib/types'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'

interface CorrectionEmailDialogProps {
  open: boolean
  draft: CorrectionEmailDraft | null
  loading: boolean
  error: string | null
  onClose: () => void
}

export function CorrectionEmailDialog({ open, draft, loading, error, onClose }: CorrectionEmailDialogProps) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  async function copy() {
    if (!draft) return
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  return (
    <Dialog
      open={open}
      title="Supplier correction email"
      description="Review the draft, copy it, then send it from your normal email client. Nothing is sent from this app."
      onClose={onClose}
    >
      <div className="p-6">
        {loading && <div className="flex min-h-52 items-center justify-center text-sm text-zinc-500"><span className="mr-3 h-5 w-5 animate-spin rounded-full border-2 border-zinc-200 border-t-zinc-800" aria-hidden="true" />Drafting email…</div>}
        {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
        {draft && !loading && (
          <div className="space-y-4">
            <label className="block text-sm font-medium text-zinc-700">To
              <input readOnly value={draft.recipient_name} className="mt-1.5 w-full rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm" />
            </label>
            <label className="block text-sm font-medium text-zinc-700">Subject
              <input readOnly value={draft.subject} className="mt-1.5 w-full rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm" />
            </label>
            <label className="block text-sm font-medium text-zinc-700">Message
              <textarea readOnly value={draft.body} rows={10} className="mt-1.5 w-full resize-none rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm leading-6" />
            </label>
            {copyState === 'failed' && <p role="alert" className="text-sm text-red-700">Clipboard access failed. Select the text and copy it manually.</p>}
          </div>
        )}
        <div className="mt-6 flex justify-end gap-2 border-t border-zinc-100 pt-5">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button disabled={!draft || loading} onClick={() => void copy()}>{copyState === 'copied' ? 'Copied' : 'Copy email'}</Button>
        </div>
      </div>
    </Dialog>
  )
}
