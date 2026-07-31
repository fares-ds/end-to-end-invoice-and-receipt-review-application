interface DocumentPreviewProps {
  src: string
  filename: string
  contentType: string
  className?: string
}

export function DocumentPreview({ src, filename, contentType, className = '' }: DocumentPreviewProps) {
  const frameClass = `h-full min-h-[520px] w-full rounded-xl border border-zinc-200 bg-zinc-100 ${className}`

  if (contentType.startsWith('image/')) {
    return (
      <div className={`${frameClass} flex items-center justify-center overflow-hidden p-4`}>
        <img src={src} alt={`Source document: ${filename}`} className="max-h-[720px] max-w-full object-contain" />
      </div>
    )
  }

  return (
    <div className={`${frameClass} overflow-hidden`}>
      <iframe
        src={src}
        title={`Source document: ${filename}`}
        className="h-full min-h-[520px] w-full border-0 bg-white"
      />
    </div>
  )
}
