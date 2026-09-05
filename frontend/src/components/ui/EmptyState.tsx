import { WifiOff } from 'lucide-react'
import { API_BASE_URL } from '../../api/client'

export function EmptyState({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string
  body: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="flex min-h-[320px] items-center justify-center">
      <div className="surface max-w-md rounded-2xl px-8 py-10 text-center">
        <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-white/[0.04]">
          <WifiOff className="h-4 w-4 text-mist-400" />
        </div>
        <p className="micro text-[9px] text-accent">System status</p>
        <h2 className="mt-3 text-xl font-medium tracking-[-0.04em] text-white">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-mist-400">{body}</p>
        <div className="mt-5 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
          <p className="micro text-[8px]">API</p>
          <p className="num mt-1 text-[11px] text-mist-200">{API_BASE_URL}</p>
        </div>
        {onAction && actionLabel ? (
          <button
            type="button"
            onClick={onAction}
            className="mt-6 rounded-xl border border-accent/20 bg-accent px-4 py-2 text-[10px] font-semibold tracking-[0.16em] text-white"
          >
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-white/[0.04] ${className}`} />
}
