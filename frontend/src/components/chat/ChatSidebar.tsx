import { Link } from 'react-router-dom'

import type { Thread } from '../../types'

interface ChatSidebarProps {
  threads: Thread[]
  activeThreadId: string | null
  isLoading: boolean
  isCreatingNew: boolean
  renamingId: string | null
  renameValue: string
  onSelectThread: (threadId: string) => void
  onCreateNew: () => void
  onStartRename: (thread: Thread) => void
  onCommitRename: (id: string) => void
  onRenameChange: (value: string) => void
  onDelete: (threadId: string) => void
  onLogout: () => void
}

export function ChatSidebar({
  threads,
  activeThreadId,
  isLoading,
  isCreatingNew,
  renamingId,
  renameValue,
  onSelectThread,
  onCreateNew,
  onStartRename,
  onCommitRename,
  onRenameChange,
  onDelete,
  onLogout,
}: ChatSidebarProps) {
  return (
    <aside className="flex w-64 flex-col border-r border-slate-800/80 bg-slate-950/45 backdrop-blur-sm md:w-72">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800/80 px-4 py-4">
        <h1 className="text-sm font-semibold tracking-wide text-slate-100">AI Chat</h1>
        <button
          onClick={onLogout}
          className="rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800/60 hover:text-slate-200"
          title="Logout"
        >
          ⏚
        </button>
      </div>

      {/* New Chat Button */}
      <div className="px-3 py-3">
        <button
          onClick={onCreateNew}
          disabled={isCreatingNew}
          className="ui-btn-secondary w-full rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          + New Chat
        </button>
      </div>

      {/* Chat History */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-2 pb-4">
        {isLoading && <p className="px-2 py-2 text-xs text-emerald-200/80">Loading…</p>}
        
        {threads.map((thread) => (
          <div
            key={thread.id}
            className={`group flex items-center gap-2 rounded-lg px-3 py-2 transition ${
              thread.id === activeThreadId
                ? 'ui-active-accent text-slate-100'
                : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200'
            }`}
          >
            {renamingId === thread.id ? (
              <input
                autoFocus
                value={renameValue}
                onChange={(e) => onRenameChange(e.target.value)}
                onBlur={() => onCommitRename(thread.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onCommitRename(thread.id)
                  if (e.key === 'Escape') onRenameChange(thread.name)
                }}
                className="ui-input flex-1 px-2 py-1 text-sm"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <>
                <button
                  onClick={() => onSelectThread(thread.id)}
                  className="flex-1 text-left text-sm truncate"
                >
                  {thread.name}
                </button>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onStartRename(thread)
                    }}
                    className="rounded p-1 text-slate-500 transition hover:bg-slate-700/60 hover:text-emerald-200"
                    title="Rename"
                  >
                    ✎
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onDelete(thread.id)
                    }}
                    className="rounded p-1 text-slate-500 transition hover:bg-slate-700/60 hover:text-rose-300"
                    title="Delete"
                  >
                    ✕
                  </button>
                </div>
              </>
            )}
          </div>
        ))}

        {!isLoading && threads.length === 0 && (
          <p className="px-2 py-2 text-xs text-slate-500">No chats yet.</p>
        )}
      </nav>

      {/* Tool links */}
      <div className="border-t border-slate-800/60 px-3 py-3 space-y-2">
        <Link
          to="/image-rules"
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-400 transition hover:bg-slate-800/70 hover:text-slate-200"
        >
          <span>🔍</span> Image Rule Checker
        </Link>
      </div>
    </aside>
  )
}
