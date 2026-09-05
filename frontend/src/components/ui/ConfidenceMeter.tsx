export function ConfidenceMeter({
  value,
  label,
}: {
  value: number
  label?: string
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value)))
  return (
    <div className="min-w-[88px]">
      <div className="flex items-baseline justify-between gap-2">
        <span className="num text-xs text-mist-100">{pct}%</span>
        {label ? <span className="micro">{label}</span> : null}
      </div>
      <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function engineConfidencePct(level: 'high' | 'medium' | 'low'): number {
  if (level === 'high') return 94
  if (level === 'medium') return 76
  return 42
}
