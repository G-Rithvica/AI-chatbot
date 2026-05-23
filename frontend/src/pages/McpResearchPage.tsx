import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { TopWorkspaceBar } from '../components/layout/TopWorkspaceBar'
import { StateBlock, SkeletonBlock } from '../components/ui/StateBlock'
import { api, streamMcpResearch } from '../lib/api'
import type { McpResearchResponse, McpResearchPaper } from '../types'

function PaperCard({ paper, index }: { paper: McpResearchPaper; index: number }) {
  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-900/50 px-3 py-2.5 text-sm">
      <p className="font-medium text-cyan-100">
        {index + 1}.{' '}
        <a href={paper.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
          {paper.title}
        </a>
      </p>
      {paper.authors.length > 0 && (
        <p className="mt-0.5 text-xs text-slate-400">{paper.authors.slice(0, 3).join(', ')}</p>
      )}
      <p className="mt-0.5 text-xs text-slate-500">Published: {paper.published}</p>
    </div>
  )
}

export default function McpResearchPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const threadsQuery = useQuery({
    queryKey: ['threads'],
    queryFn: api.getThreads,
    select: (data) => data.threads,
  })
  const threads = threadsQuery.data ?? []
  const [selectedThreadId, setSelectedThreadId] = useState<string>('')

  const [query, setQuery] = useState('')
  const [maxResults, setMaxResults] = useState(10)
  const [streaming, setStreaming] = useState(false)
  const [streamLog, setStreamLog] = useState<string[]>([])
  const [result, setResult] = useState<McpResearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  const threadId = useMemo(() => selectedThreadId || undefined, [selectedThreadId])

  const sanitizeMaxResults = (value: number) => {
    if (!Number.isFinite(value)) return 10
    return Math.min(50, Math.max(1, Math.trunc(value)))
  }

  const handleStream = async () => {
    const q = query.trim()
    if (!q || streaming) return
    setStreaming(true)
    setStreamLog([])
    setResult(null)
    setError(null)

    try {
      const safeMaxResults = sanitizeMaxResults(maxResults)
      await streamMcpResearch(
        { query: q, max_results: safeMaxResults, max_summary_length: 800, thread_id: threadId },
        (evt) => {
          if (evt.type === 'status') {
            setStreamLog((l) => [...l, `[${evt.stage}] ${evt.message}`])
          } else if (evt.type === 'token') {
            setStreamLog((l) => {
              const last = l[l.length - 1] ?? ''
              if (last.startsWith('[digest]')) return [...l.slice(0, -1), last + evt.content]
              return [...l, `[digest] ${evt.content}`]
            })
          } else if (evt.type === 'final') {
            setResult(evt.result)
          }
          setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
        },
      )
      if (threadId) {
        queryClient.invalidateQueries({ queryKey: ['threads'] })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stream failed.')
    } finally {
      setStreaming(false)
    }
  }

  const queryMutation = useMutation({
    mutationFn: () => api.mcpResearchQuery({
      query: query.trim(),
      max_results: sanitizeMaxResults(maxResults),
      max_summary_length: 800,
      thread_id: threadId,
    }),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      if (threadId) queryClient.invalidateQueries({ queryKey: ['threads'] })
    },
    onError: (e: Error) => setError(e.message),
  })

  return (
    <div className="app-shell min-h-screen">
      <TopWorkspaceBar
        title="Project 12 — MCP Research Agent"
        subtitle="arXiv search + LLM digest via Model Context Protocol tools"
        leftActions={(
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className="ui-btn-secondary px-3 py-1.5 text-xs"
          >
            ← Back to Chat
          </button>
        )}
      />

      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        {/* ── Query form ── */}
        <section className="ui-surface p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-cyan-200/75">MCP Agent Input</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-100">Research Query</h2>

          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleStream() }}
              placeholder="e.g. transformer agents for code generation"
              className="ui-input"
            />
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400 whitespace-nowrap">Max papers</label>
              <input
                type="number"
                min={1}
                max={50}
                value={maxResults}
                onChange={(e) => setMaxResults(sanitizeMaxResults(Number(e.target.value)))}
                className="ui-input w-16 text-center"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400 whitespace-nowrap">Thread</label>
              <select
                value={selectedThreadId}
                onChange={(e) => setSelectedThreadId(e.target.value)}
                className="ui-input text-xs"
              >
                <option value="">No thread</option>
                {threads.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => void handleStream()}
              disabled={streaming || !query.trim()}
              className="ui-btn-primary px-4 py-2 text-sm disabled:opacity-50"
            >
              {streaming ? 'Streaming…' : '🔬 Stream via MCP'}
            </button>
            <button
              type="button"
              onClick={() => queryMutation.mutate()}
              disabled={queryMutation.isPending || !query.trim()}
              className="ui-btn-secondary px-4 py-2 text-sm disabled:opacity-50"
            >
              {queryMutation.isPending ? 'Loading…' : 'Query (JSON)'}
            </button>
          </div>
        </section>

        {/* ── MCP tool call log ── */}
        {streamLog.length > 0 && (
          <section className="mt-4 ui-surface p-4">
            <p className="mb-2 text-xs uppercase tracking-[0.14em] text-cyan-200/70">MCP Tool Call Log</p>
            <div className="max-h-48 overflow-y-auto space-y-0.5 font-mono text-[11px] text-slate-300">
              {streamLog.map((line, i) => (
                <div key={i} className="leading-5">{line}</div>
              ))}
              <div ref={logEndRef} />
            </div>
          </section>
        )}

        {/* ── Agent thinking indicator ── */}
        {(streaming || queryMutation.isPending) && !result && (
          <div className="mt-4">
            <SkeletonBlock lines={3} />
            <StateBlock tone="neutral" title="MCP agent running" message="Calling search_arxiv_papers → generate_research_digest via MCP protocol…" />
          </div>
        )}

        {error && <div className="mt-4"><StateBlock tone="error" title="Agent error" message={error} /></div>}

        {/* ── Result ── */}
        {result && (
          <section className="mt-4 ui-surface-accent p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-cyan-200/70">MCP Digest Result</p>
                <h3 className="mt-0.5 text-base font-semibold text-slate-100">{result.query}</h3>
              </div>
              <span className="rounded-full border border-cyan-400/40 bg-cyan-500/15 px-2 py-0.5 text-[11px] font-medium text-cyan-100">
                source: {result.agent_source}
              </span>
            </div>

            <div className="mt-3 flex gap-4 text-sm text-slate-400">
              <span><span className="font-medium text-slate-200">{result.papers_found}</span> papers</span>
            </div>

            <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-3 text-sm text-slate-200 whitespace-pre-wrap">
              {result.digest}
            </div>

            <p className="mt-4 text-xs uppercase tracking-[0.14em] text-cyan-200/70">Papers</p>
            <div className="mt-2 space-y-2">
              {result.papers.map((paper, i) => (
                <PaperCard key={paper.arxiv_id} paper={paper} index={i} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
