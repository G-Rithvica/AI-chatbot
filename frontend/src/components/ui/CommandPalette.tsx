import { useEffect, useMemo, useState } from 'react'

export type CommandItem = {
  id: string
  label: string
  hint?: string
  onTrigger: () => void
}

type CommandPaletteProps = {
  isOpen: boolean
  search: string
  onSearchChange: (value: string) => void
  commands: CommandItem[]
  onClose: () => void
}

export function CommandPalette({ isOpen, search, onSearchChange, commands, onClose }: CommandPaletteProps) {
  const [activeIndex, setActiveIndex] = useState(0)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((command) => {
      const base = `${command.label} ${command.hint ?? ''}`.toLowerCase()
      return base.includes(q)
    })
  }, [commands, search])

  useEffect(() => {
    setActiveIndex(0)
  }, [search, isOpen])

  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setActiveIndex((current) => Math.min(current + 1, Math.max(filtered.length - 1, 0)))
        return
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setActiveIndex((current) => Math.max(current - 1, 0))
        return
      }

      if (event.key === 'Enter' && filtered[activeIndex]) {
        event.preventDefault()
        filtered[activeIndex].onTrigger()
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [activeIndex, filtered, isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-16" onClick={onClose}>
      <div className="ui-surface w-full max-w-2xl p-3 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search commands..."
          className="ui-input"
          aria-label="Search commands"
        />
        <div className="mt-2 flex items-center gap-2 text-xs text-(--text-muted)">
          <span className="ui-kbd">↑</span>
          <span className="ui-kbd">↓</span>
          <span>Navigate</span>
          <span className="ui-kbd">Enter</span>
          <span>Run</span>
          <span className="ui-kbd">Esc</span>
          <span>Close</span>
        </div>
        <div className="mt-3 max-h-80 overflow-y-auto">
          {filtered.length === 0 && (
            <p className="px-2 py-3 text-sm text-(--text-muted)">No commands found.</p>
          )}
          {filtered.map((command, index) => (
            <button
              key={command.id}
              type="button"
              onClick={() => {
                command.onTrigger()
                onClose()
              }}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition hover:bg-(--accent-soft) ${index === activeIndex ? 'bg-(--accent-soft)' : ''}`}
            >
              <span>{command.label}</span>
              {command.hint && <span className="text-xs text-(--text-muted)">{command.hint}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
