export const PROCESSING_STEPS = [
  {
    title: 'Classify document',
    description: 'Recognizing whether the upload is an invoice or a receipt.',
  },
  {
    title: 'Extract and cross-check',
    description: 'Running Document Intelligence, then filling gaps from the independent LLM review.',
  },
  {
    title: 'Validate Northstar policy',
    description: 'Applying deterministic invoice and receipt rules, including VAT and totals.',
  },
  {
    title: 'Suggest GL account',
    description: 'Matching normalized fields to the fixed Northstar catalog.',
  },
] as const

export function processingStepAt(elapsedMs: number): number {
  if (elapsedMs >= 8000) return 3
  if (elapsedMs >= 5000) return 2
  if (elapsedMs >= 2500) return 1
  return 0
}
