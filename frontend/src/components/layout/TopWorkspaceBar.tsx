import type { ReactNode } from 'react'

type TopWorkspaceBarProps = {
  title: string
  subtitle?: string
  leftActions?: ReactNode
  rightActions?: ReactNode
}

export function TopWorkspaceBar({ title, subtitle, leftActions, rightActions }: TopWorkspaceBarProps) {
  return (
    <header className="app-topbar px-4 py-3 sm:px-6">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold text-(--text-main) sm:text-lg">{title}</h1>
          {subtitle && <p className="truncate text-xs text-(--text-muted) sm:text-sm">{subtitle}</p>}
        </div>

        <div className="flex items-center gap-2">
          {leftActions}
          {rightActions}
        </div>
      </div>
    </header>
  )
}
