import { summarizeDocumentReview } from '../lib/document-review'
import type { DocumentReviewArtifact } from '../lib/types'
import { Badge } from './ui/Badge'

interface DocumentReviewSectionProps {
  review: DocumentReviewArtifact
}

function shown(value: string | null): string {
  return value?.trim() || 'Not found'
}

export function DocumentReviewSection({ review }: DocumentReviewSectionProps) {
  const summary = summarizeDocumentReview(review)
  const differences = review.comparisons.filter(
    (comparison) => comparison.status !== 'match' && comparison.status !== 'missing_in_both',
  )
  const fallbackFields = new Set(review.fallback_fields.map((item) => item.field))
  const messageStyle = {
    agreement: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    supplemented: 'border-blue-200 bg-blue-50 text-blue-950',
    differences: 'border-amber-200 bg-amber-50 text-amber-950',
    unavailable: 'border-zinc-200 bg-zinc-50 text-zinc-800',
  }[summary.kind]

  return (
    <section className="border-t border-zinc-100 pt-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-zinc-900">Independent LLM cross-check</h3>
          <p className="mt-1 text-sm text-zinc-500">Azure OpenAI reads the original document separately and compares its extraction with Document Intelligence.</p>
        </div>
        <Badge variant="secondary">Document Intelligence primary</Badge>
      </div>

      <div className={`mt-4 rounded-lg border p-4 ${messageStyle}`}>
        <p className="text-sm font-semibold">{summary.title}</p>
        <p className="mt-1 text-sm leading-6 opacity-80">{summary.description}</p>
        {review.extraction?.summary && <p className="mt-2 text-sm leading-6"><span className="font-medium">LLM summary:</span> {review.extraction.summary}</p>}
      </div>

      {differences.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200">
          <div className="grid min-w-[40rem] grid-cols-[minmax(8rem,0.8fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 border-b border-zinc-200 bg-zinc-50 px-4 py-2 text-xs font-medium text-zinc-500">
            <span>Field</span>
            <span>Document Intelligence</span>
            <span>Azure OpenAI</span>
          </div>
          {differences.map((comparison) => (
            <div key={comparison.field} className="grid min-w-[40rem] grid-cols-[minmax(8rem,0.8fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 border-b border-zinc-100 px-4 py-3 text-sm last:border-b-0">
              <span className="font-medium text-zinc-800">{comparison.label}{fallbackFields.has(comparison.field) && <Badge variant="secondary" className="ml-2">LLM fallback</Badge>}</span>
              <span className="break-words text-zinc-600">{shown(comparison.document_intelligence_value)}</span>
              <span className="break-words text-zinc-600">{shown(comparison.llm_value)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
