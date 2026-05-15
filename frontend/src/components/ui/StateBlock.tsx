type StateBlockProps = {
  title: string
  message: string
  tone?: 'neutral' | 'error' | 'warning'
}

export function StateBlock({ title, message, tone = 'neutral' }: StateBlockProps) {
  const toneClass = tone === 'error' ? 'ui-error-banner' : tone === 'warning' ? 'border border-amber-400/30 bg-amber-500/10 text-amber-100' : 'ui-surface-accent'
  return (
    <div className={`${toneClass} rounded-xl px-4 py-3`} role={tone === 'error' ? 'alert' : 'status'}>
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-1 text-sm opacity-90">{message}</p>
    </div>
  )
}

type SkeletonBlockProps = {
  lines?: number
}

export function SkeletonBlock({ lines = 3 }: SkeletonBlockProps) {
  return (
    <div className="ui-surface rounded-xl px-4 py-3" aria-hidden="true">
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, index) => (
          <div
            key={index}
            className="ui-skeleton h-4 rounded"
            style={{ width: `${Math.max(35, 100 - index * 15)}%` }}
          />
        ))}
      </div>
    </div>
  )
}
