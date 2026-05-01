import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../lib/api'
import type { ChatMessage, Thread } from '../types'

export default function ChatPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const [sending, setSending] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  // ── Threads ──────────────────────────────────────────────────────────────
  const threadsQuery = useQuery({
    queryKey: ['threads'],
    queryFn: api.getThreads,
    select: (data) => data.threads,
  })

  const threads: Thread[] = threadsQuery.data ?? []

  // Auto-select first thread when list loads
  const activeThread = useMemo(() => {
    if (activeThreadId) return threads.find((t) => t.id === activeThreadId) ?? null
    if (threads.length > 0) return threads[0]
    return null
  }, [threads, activeThreadId])

  const currentThreadId = activeThread?.id ?? null

  // ── Messages ─────────────────────────────────────────────────────────────
  const historyQuery = useQuery({
    queryKey: ['chat', 'history', currentThreadId],
    queryFn: () => api.getChatHistory(currentThreadId!),
    enabled: !!currentThreadId,
  })

  const messages = useMemo(() => historyQuery.data?.messages ?? [], [historyQuery.data])

  // ── Logout ────────────────────────────────────────────────────────────────
  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      navigate('/')
    },
  })

  // ── New thread ───────────────────────────────────────────────────────────
  const createThreadMutation = useMutation({
    mutationFn: api.createThread,
    onSuccess: (thread) => {
      queryClient.invalidateQueries({ queryKey: ['threads'] })
      setActiveThreadId(thread.id)
    },
  })

  // ── Rename thread ─────────────────────────────────────────────────────────
  const renameThreadMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.renameThread(id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threads'] })
      setRenamingId(null)
    },
  })

  // ── Delete thread ─────────────────────────────────────────────────────────
  const deleteThreadMutation = useMutation({
    mutationFn: api.deleteThread,
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['threads'] })
      queryClient.removeQueries({ queryKey: ['chat', 'history', deletedId] })
      if (activeThreadId === deletedId) setActiveThreadId(null)
    },
  })

  // ── Send message ─────────────────────────────────────────────────────────
  const handleSend = async () => {
    const prompt = input.trim()
    if (!prompt || sending || !currentThreadId) return

    setInput('')
    setStreamingText('')
    setStreamError(null)
    setSending(true)

    await queryClient.setQueryData(
      ['chat', 'history', currentThreadId],
      (old: { messages: ChatMessage[] } | undefined) => {
        const optimistic: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'user',
          content: prompt,
          created_at: new Date().toISOString(),
        }
        return { messages: [...(old?.messages ?? []), optimistic] }
      },
    )

    try {
      await api.streamChat(prompt, currentThreadId, (token) => {
        setStreamingText((c) => c + token)
      })
    } catch (error) {
      setStreamError(error instanceof Error ? error.message : 'Failed to get a response.')
    } finally {
      setSending(false)
      setStreamingText('')
      await queryClient.invalidateQueries({ queryKey: ['chat', 'history', currentThreadId] })
      // Refresh thread list so auto-generated name appears
      queryClient.invalidateQueries({ queryKey: ['threads'] })
    }
  }

  const startRename = (thread: Thread) => {
    setRenamingId(thread.id)
    setRenameValue(thread.name)
  }

  const commitRename = (id: string) => {
    if (renameValue.trim()) renameThreadMutation.mutate({ id, name: renameValue.trim() })
    else setRenamingId(null)
  }

  return (
    <main className="flex h-screen bg-stone-950 text-stone-100 overflow-hidden">
      {/* ── Sidebar ── */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-stone-800 bg-stone-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-stone-800 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-amber-300">Amzur AI Chat</p>
          <button
            type="button"
            onClick={() => logoutMutation.mutate()}
            className="text-xs text-stone-400 hover:text-stone-100"
          >
            Logout
          </button>
        </div>

        {/* New thread */}
        <div className="p-3">
          <button
            type="button"
            onClick={() => createThreadMutation.mutate()}
            disabled={createThreadMutation.isPending}
            className="w-full rounded-xl border border-stone-700 py-2 text-sm text-stone-300 transition hover:bg-stone-800 disabled:opacity-50"
          >
            + New Chat
          </button>
        </div>

        {/* Thread list */}
        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {threadsQuery.isLoading && <p className="px-2 text-xs text-stone-500">Loading…</p>}
          {threads.map((thread) => (
            <div
              key={thread.id}
              className={`group mb-1 flex items-center gap-1 rounded-xl px-2 py-2 text-sm transition ${
                thread.id === currentThreadId
                  ? 'bg-stone-800 text-stone-100'
                  : 'text-stone-400 hover:bg-stone-800/60 hover:text-stone-100'
              }`}
            >
              {renamingId === thread.id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={() => commitRename(thread.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitRename(thread.id)
                    if (e.key === 'Escape') setRenamingId(null)
                  }}
                  className="min-w-0 flex-1 rounded bg-stone-700 px-1 py-0.5 text-sm text-stone-100 outline-none"
                />
              ) : (
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left"
                  onClick={() => setActiveThreadId(thread.id)}
                >
                  {thread.name}
                </button>
              )}
              {/* Action buttons — visible on hover */}
              <div className="flex shrink-0 gap-1 opacity-0 group-hover:opacity-100">
                <button
                  type="button"
                  title="Rename"
                  onClick={(e) => { e.stopPropagation(); startRename(thread) }}
                  className="rounded p-0.5 text-stone-500 hover:text-amber-300"
                >
                  ✎
                </button>
                <button
                  type="button"
                  title="Delete"
                  onClick={(e) => { e.stopPropagation(); deleteThreadMutation.mutate(thread.id) }}
                  className="rounded p-0.5 text-stone-500 hover:text-rose-400"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
          {!threadsQuery.isLoading && threads.length === 0 && (
            <p className="px-2 text-xs text-stone-600">No chats yet. Create one above.</p>
          )}
        </nav>
      </aside>

      {/* ── Main panel ── */}
      <section className="flex flex-1 flex-col overflow-hidden">
        {currentThreadId ? (
          <>
            {/* Thread title bar */}
            <header className="border-b border-stone-800 bg-stone-900/70 px-6 py-3">
              <h1 className="text-sm font-semibold">{activeThread?.name ?? 'Chat'}</h1>
            </header>

            {/* Messages */}
            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={`max-w-[80%] rounded-2xl px-4 py-3 text-justify text-sm leading-6 ${
                    message.role === 'user'
                      ? 'ml-auto bg-amber-300 text-stone-950'
                      : 'mr-auto bg-stone-800 text-stone-100'
                  }`}
                >
                  {message.content}
                </article>
              ))}

              {streamingText && (
                <article className="mr-auto max-w-[80%] rounded-2xl bg-stone-800 px-4 py-3 text-justify text-sm leading-6 text-stone-100">
                  {streamingText}
                </article>
              )}

              {historyQuery.isLoading && <p className="text-sm text-stone-500">Loading messages…</p>}
              {historyQuery.isError && <p className="text-sm text-rose-300">Failed to load messages.</p>}
              {streamError && <p className="text-sm text-rose-300">{streamError}</p>}
            </div>

            {/* Input */}
            <footer className="border-t border-stone-800 bg-stone-900/70 p-4">
              <div className="flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
                  }}
                  rows={3}
                  placeholder="Ask anything… (Enter to send, Shift+Enter for newline)"
                  className="min-h-18 flex-1 resize-y rounded-xl border border-stone-700 bg-stone-950 px-3 py-2 text-sm outline-none placeholder:text-stone-500 focus:border-amber-300"
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={sending || !input.trim()}
                  className="rounded-xl bg-amber-300 px-4 py-2 text-sm font-medium text-stone-950 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sending ? 'Sending…' : 'Send'}
                </button>
              </div>
            </footer>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-stone-600">
            <p className="text-sm">Select a chat or create a new one.</p>
          </div>
        )}
      </section>
    </main>
  )
}
