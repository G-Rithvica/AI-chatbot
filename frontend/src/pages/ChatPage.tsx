import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AutoResizeTextarea } from '../components/chat/AutoResizeTextarea'
import { AttachmentPanel } from '../components/chat/AttachmentPanel'
import { ChatSidebar } from '../components/chat/ChatSidebar'
import { GeneratedImageBubble, MessageBubble, MessageContentRenderer, TypingBubble } from '../components/chat/MessageBubble'
import { api } from '../lib/api'
import { deriveImageGenerationOptions, isImageGenerationPrompt, isImageValidationPrompt } from '../lib/messageHelpers'
import type { Attachment, ChatMessage, DatabaseConnectionInput, DatabaseQueryResponse, ResearchDigestResponse, SpreadsheetQueryResponse, Thread } from '../types'

const DRAFT_STORAGE_PREFIX = 'chat:draft:'

function draftStorageKey(threadId: string): string {
  return `${DRAFT_STORAGE_PREFIX}${threadId}`
}

function formatDatabaseResult(result: DatabaseQueryResponse): string {
  const lines: string[] = ['### Database Result', `Status: ${result.allowed ? 'Allowed' : 'Blocked'}`, `Message: ${result.message}`]

  if (result.sql) {
    lines.push('', 'Generated SQL:', '```sql', result.sql, '```')
  }

  if (result.explanation) {
    lines.push('', `Explanation: ${result.explanation}`)
  }

  if (result.columns.length && result.rows.length) {
    const header = `| ${result.columns.join(' | ')} |`
    const divider = `| ${result.columns.map(() => '---').join(' | ')} |`
    const body = result.rows.slice(0, 50).map((row) => {
      const cells = result.columns.map((column) => String(row[column] ?? ''))
      return `| ${cells.join(' | ')} |`
    })

    lines.push('', `Rows returned: ${result.row_count}`, '', header, divider, ...body)
  } else {
    lines.push('', `Rows returned: ${result.row_count}`)
  }

  return lines.join('\n')
}

function formatSpreadsheetResult(result: SpreadsheetQueryResponse): string {
  const lines: string[] = [
    '### Spreadsheet Analysis Result',
    `Message: ${result.message}`,
    `Rows analyzed: ${result.rows_considered}`,
    '',
    '**Answer:**',
    result.answer,
  ]

  if (result.columns.length) {
    lines.push('', `Columns: ${result.columns.join(', ')}`)
  }

  return lines.join('\n')
}

function formatResearchDigestResult(result: ResearchDigestResponse): string {
  const lines: string[] = [
    '### Research Digest',
    `Query: ${result.query}`,
    `Papers Found: ${result.papers_found}`,
    '',
    '**Digest:**',
    result.digest,
    '',
    '**Papers:**',
  ]

  for (let i = 0; i < Math.min(result.papers.length, 10); i++) {
    const paper = result.papers[i]
    lines.push(`${i + 1}. [${paper.title}](${paper.url})`)
    if (paper.authors.length) {
      lines.push(`   Authors: ${paper.authors.slice(0, 3).join(', ')}`)
    }
    lines.push(`   Published: ${paper.published}`)
  }

  if (result.papers.length > 10) {
    lines.push(`... and ${result.papers.length - 10} more papers`)
  }

  return lines.join('\n')
}

export default function ChatPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // State
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<string[]>([])
  const [databaseModeEnabled, setDatabaseModeEnabled] = useState(false)
  const [databaseConnectMode, setDatabaseConnectMode] = useState<'automatic' | 'manual'>('automatic')
  const [databaseConnected, setDatabaseConnected] = useState(false)
  const [databaseStatusMessage, setDatabaseStatusMessage] = useState<string | null>(null)
  const [tabularModeEnabled, setTabularModeEnabled] = useState(false)
  const [tabularSourceId, setTabularSourceId] = useState<string | null>(null)
  const [tabularSourceLabel, setTabularSourceLabel] = useState<string | null>(null)
  const [tabularGSheetUrl, setTabularGSheetUrl] = useState('')
  const [tabularPanelOpen, setTabularPanelOpen] = useState(false)
  const [researchQuery, setResearchQuery] = useState('')
  const [researchPanelOpen, setResearchPanelOpen] = useState(false)
  const [manualDatabaseConnection, setManualDatabaseConnection] = useState<DatabaseConnectionInput>({
    db_type: 'postgresql',
    host: '',
    port: 5432,
    database: '',
    username: '',
    password: '',
    schema: 'public',
    url: '',
    sqlite_path: '',
    ssl_required: false,
  })
  const fileInputRef = useRef<HTMLInputElement>(null)
  const tabularFileInputRef = useRef<HTMLInputElement>(null)
  const tabularPanelRef = useRef<HTMLDivElement>(null)
  const researchPanelRef = useRef<HTMLDivElement>(null)
  const currentThreadIdRef = useRef<string | null>(null)

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

  useEffect(() => {
    currentThreadIdRef.current = currentThreadId
  }, [currentThreadId])

  // ── Messages ─────────────────────────────────────────────────────────────
  const historyQuery = useQuery({
    queryKey: ['chat', 'history', currentThreadId],
    queryFn: () => api.getChatHistory(currentThreadId!),
    enabled: !!currentThreadId,
  })

  const messages = useMemo(() => historyQuery.data?.messages ?? [], [historyQuery.data])
  const historyImages = useMemo(() => historyQuery.data?.generated_images ?? [], [historyQuery.data])
  const currentThreadImages = useMemo(
    () => historyImages.filter((image) => image.thread_id === currentThreadId),
    [historyImages, currentThreadId],
  )

  const timelineItems = useMemo(() => {
    const messageItems = messages.map((message) => ({
      kind: 'message' as const,
      id: message.id,
      timestamp: Date.parse(message.created_at || '') || 0,
      message,
    }))

    const userPromptSet = new Set(
      messages
        .filter((message) => message.role === 'user')
        .map((message) => message.content.trim()),
    )

    const imageItems = currentThreadImages.flatMap((image) => {
      const imageTimestamp = Date.parse(image.created_at) || 0
      const normalizedPrompt = image.prompt.trim()
      const needsPromptBubble = normalizedPrompt.length > 0 && !userPromptSet.has(normalizedPrompt)

      const syntheticPromptItem = needsPromptBubble
        ? [{
            kind: 'message' as const,
            id: `img-prompt-${image.id}`,
            timestamp: imageTimestamp,
            message: {
              id: `img-prompt-${image.id}`,
              role: 'user' as const,
              content: image.prompt,
              created_at: image.created_at,
            },
          }]
        : []

      return [
        ...syntheticPromptItem,
        {
          kind: 'image' as const,
          id: image.id,
          timestamp: imageTimestamp,
          image,
        },
      ]
    })

    return [...messageItems, ...imageItems].sort((a, b) => {
      if (a.timestamp !== b.timestamp) return a.timestamp - b.timestamp
      if (a.kind === b.kind) return 0
      return a.kind === 'message' ? -1 : 1
    })
  }, [messages, currentThreadImages])

  const attachmentsQuery = useQuery({
    queryKey: ['attachments', currentThreadId],
    queryFn: () => api.getAttachments(currentThreadId!),
    select: (data) => data.attachments,
    enabled: !!currentThreadId,
  })

  const attachments: Attachment[] = attachmentsQuery.data ?? []

  const selectedAttachments = useMemo(
    () => attachments.filter((item) => selectedAttachmentIds.includes(item.id)),
    [attachments, selectedAttachmentIds],
  )

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

  const uploadAttachmentMutation = useMutation({
    mutationFn: ({ threadId, file }: { threadId: string; file: File }) => api.uploadAttachment(threadId, file),
    onSuccess: (attachment) => {
      queryClient.invalidateQueries({ queryKey: ['attachments', currentThreadId] })
      setSelectedAttachmentIds((prev) => [...prev, attachment.id])
    },
    onError: (error: Error) => {
      setError(error.message)
    },
  })

  const removeAttachmentMutation = useMutation({
    mutationFn: api.deleteAttachment,
    onSuccess: (_, attachmentId) => {
      queryClient.invalidateQueries({ queryKey: ['attachments', currentThreadId] })
      setSelectedAttachmentIds((prev) => prev.filter((id) => id !== attachmentId))
    },
    onError: (error: Error) => {
      setError(error.message)
    },
  })

  const databaseConnectMutation = useMutation({
    mutationFn: () => api.databaseConnect({
      connection: databaseConnectMode === 'manual' ? manualDatabaseConnection : undefined,
    }),
    onSuccess: (result) => {
      setDatabaseConnected(result.connected)
      setDatabaseStatusMessage(result.message)
      setError(null)
    },
    onError: (connectError: Error) => {
      setDatabaseConnected(false)
      setDatabaseStatusMessage(null)
      setError(connectError.message)
    },
  })

  const generateImageMutation = useMutation({
    mutationFn: api.generateImage,
    onError: (error: Error) => {
      setError(error.message)
    },
  })

  const validateImageMutation = useMutation({
    mutationFn: api.validateImage,
    onError: (error: Error) => {
      setError(error.message)
    },
  })

  // Effects
  useEffect(() => {
    setSelectedAttachmentIds([])
  }, [currentThreadId])

  useEffect(() => {
    setTabularModeEnabled(false)
    setTabularSourceId(null)
    setTabularSourceLabel(null)
    setTabularGSheetUrl('')
    setTabularPanelOpen(false)
    setResearchQuery('')
    setResearchPanelOpen(false)
  }, [currentThreadId])

  useEffect(() => {
    if (!tabularPanelOpen) return

    const handleOutsideClick = (event: MouseEvent) => {
      if (!tabularPanelRef.current?.contains(event.target as Node)) {
        setTabularPanelOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)
    }
  }, [tabularPanelOpen])

  useEffect(() => {
    if (!researchPanelOpen) return

    const handleOutsideClick = (event: MouseEvent) => {
      if (!researchPanelRef.current?.contains(event.target as Node)) {
        setResearchPanelOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)
    }
  }, [researchPanelOpen])

  useEffect(() => {
    setDatabaseConnected(false)
    setDatabaseStatusMessage(null)
  }, [databaseConnectMode, manualDatabaseConnection, databaseModeEnabled])

  // Restore per-thread unsent draft on thread switch or refresh.
  useEffect(() => {
    if (!currentThreadId) {
      setInput('')
      return
    }

    try {
      const savedDraft = localStorage.getItem(draftStorageKey(currentThreadId))
      setInput(savedDraft ?? '')
    } catch {
      setInput('')
    }
  }, [currentThreadId])

  // Persist unsent draft for current thread while typing.
  useEffect(() => {
    const threadId = currentThreadIdRef.current
    if (!threadId) return

    try {
      if (input) {
        localStorage.setItem(draftStorageKey(threadId), input)
      } else {
        localStorage.removeItem(draftStorageKey(threadId))
      }
    } catch {
      // Ignore storage errors (private mode/quota issues) without impacting chat flow.
    }
  }, [input])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [timelineItems, streamingText])

  // Handlers
  const handleSend = async () => {
    const rawPrompt = input.trim()
    const forceImageGeneration = /^\/(image|img)\s+/i.test(rawPrompt)
    const forceImageValidation = /^\/(validate|validate-image)\s*/i.test(rawPrompt)
    const promptWithoutImageCommand = rawPrompt.replace(/^\/(image|img)\s+/i, '').trim()
    const prompt = promptWithoutImageCommand.replace(/^\/(validate|validate-image)\s*/i, '').trim()

    if (sending || !currentThreadId) return

    const shouldGenerateImage = forceImageGeneration || isImageGenerationPrompt(prompt)
    const shouldValidateImage = forceImageValidation || isImageValidationPrompt(rawPrompt)
    if (!prompt && !shouldValidateImage) return

    setInput('')
    setStreamingText('')
    setError(null)
    setSending(true)

    const attachmentIds = selectedAttachmentIds.length ? [...selectedAttachmentIds] : undefined
    const selectedImageAttachment = selectedAttachments.find(
      (item) => item.kind === 'image' || item.mime_type.toLowerCase().startsWith('image/'),
    )
    const optimisticPrompt = prompt || (shouldValidateImage ? 'Validate selected image' : rawPrompt)

    // Add optimistic user message
    await queryClient.setQueryData(
      ['chat', 'history', currentThreadId],
      (old: { messages: ChatMessage[] } | undefined) => {
        const optimistic: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'user',
          content: optimisticPrompt,
          created_at: new Date().toISOString(),
        }
        return { messages: [...(old?.messages ?? []), optimistic] }
      },
    )

    try {
      if (tabularModeEnabled) {
        if (!tabularSourceId) {
          throw new Error('Select a spreadsheet source from the left panel (Upload Excel or Load GSheet), then ask your question.')
        }

        const spreadsheetResult = await api.spreadsheetQuery({
          source_id: tabularSourceId,
          question: prompt,
          max_rows: 200,
          thread_id: currentThreadId,
        })

        const assistantMessage: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: formatSpreadsheetResult(spreadsheetResult),
          created_at: new Date().toISOString(),
        }

        await queryClient.setQueryData(
          ['chat', 'history', currentThreadId],
          (old: { messages: ChatMessage[]; generated_images?: unknown[] } | undefined) => ({
            messages: [...(old?.messages ?? []), assistantMessage],
            generated_images: old?.generated_images ?? [],
          }),
        )
      } else if (databaseModeEnabled) {
        if (!databaseConnected) {
          throw new Error('Connect to the database first (automatic or manual mode), then ask your question.')
        }

        const databaseResult = await api.databaseQuery({
          question: prompt,
          max_rows: 50,
          thread_id: currentThreadId,
          connection: databaseConnectMode === 'manual' ? manualDatabaseConnection : undefined,
        })

        const assistantMessage: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: formatDatabaseResult(databaseResult),
          created_at: new Date().toISOString(),
        }

        await queryClient.setQueryData(
          ['chat', 'history', currentThreadId],
          (old: { messages: ChatMessage[]; generated_images?: unknown[] } | undefined) => ({
            messages: [...(old?.messages ?? []), assistantMessage],
            generated_images: old?.generated_images ?? [],
          }),
        )
      } else if (shouldValidateImage) {
        if (!selectedImageAttachment) {
          throw new Error('Attach and select at least one image, then send /validate to run validation.')
        }
        await validateImageMutation.mutateAsync({
          image_id: selectedImageAttachment.id,
          thread_id: currentThreadId,
          note: optimisticPrompt,
          include_default_rules: true,
        })
        setError(null)
      } else if (shouldGenerateImage) {
        const imageOptions = deriveImageGenerationOptions(prompt)
        await generateImageMutation.mutateAsync({
          prompt: imageOptions.prompt,
          thread_id: currentThreadId,
          size: imageOptions.size,
          style: imageOptions.style,
          response_format: 'b64_json',
        })
        setError(null)
      } else {
        await api.streamChat(prompt, currentThreadId, attachmentIds, (token) => {
          setStreamingText((c) => c + token)
        })
      }
      setSelectedAttachmentIds([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get a response.')
    } finally {
      setSending(false)
      setStreamingText('')
      if (!databaseModeEnabled && !tabularModeEnabled) {
        await queryClient.invalidateQueries({ queryKey: ['chat', 'history', currentThreadId] })
        queryClient.invalidateQueries({ queryKey: ['threads'] })
      }
    }
  }

  const handleTabularFilePick = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    if (!currentThreadId) {
      setError('Create or select a chat thread first, then upload a spreadsheet.')
      return
    }

    setError(null)
    const first = files[0]
    try {
      const attachment = await api.uploadAttachment(currentThreadId, first)
      await queryClient.invalidateQueries({ queryKey: ['attachments', currentThreadId] })
      setTabularSourceId(attachment.id)
      setTabularSourceLabel(`${attachment.file_name} (uploaded)`)
      setTabularModeEnabled(true)
      setTabularGSheetUrl('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload spreadsheet.')
    } finally {
      if (tabularFileInputRef.current) {
        tabularFileInputRef.current.value = ''
      }
    }
  }

  const handleTabularLoadGSheet = () => {
    const trimmed = tabularGSheetUrl.trim()
    if (!trimmed) return
    setTabularSourceId(trimmed)
    setTabularSourceLabel(trimmed)
    setTabularModeEnabled(true)
    setError(null)
  }

  const handleResearchDigest = async () => {
    const query = researchQuery.trim()
    if (!query || !currentThreadId || sending) return

    setError(null)
    setSending(true)
    setStreamingText('')

    await queryClient.setQueryData(
      ['chat', 'history', currentThreadId],
      (old: { messages: ChatMessage[] } | undefined) => {
        const optimistic: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'user',
          content: `Research: ${query}`,
          created_at: new Date().toISOString(),
        }
        return { messages: [...(old?.messages ?? []), optimistic] }
      },
    )

    let finalResult: ResearchDigestResponse | null = null
    try {
      await api.streamResearchDigest(
        {
          query,
          max_results: 15,
          max_summary_length: 1000,
          thread_id: currentThreadId,
        },
        (event) => {
          if (event.type === 'status') {
            setStreamingText((current) => `${current}${current ? '\n' : ''}[${event.stage}] ${event.message}`)
            return
          }
          if (event.type === 'token') {
            setStreamingText((current) => `${current}${event.content}`)
            return
          }
          if (event.type === 'final') {
            finalResult = event.result
          }
        },
      )

      if (!finalResult) {
        throw new Error('Research digest stream ended without a final result.')
      }

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: formatResearchDigestResult(finalResult),
        created_at: new Date().toISOString(),
      }

      await queryClient.setQueryData(
        ['chat', 'history', currentThreadId],
        (old: { messages: ChatMessage[]; generated_images?: unknown[] } | undefined) => ({
          messages: [...(old?.messages ?? []), assistantMessage],
          generated_images: old?.generated_images ?? [],
        }),
      )

      setResearchQuery('')
      setResearchPanelOpen(false)
      setSelectedAttachmentIds([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate research digest.')
    } finally {
      setSending(false)
      setStreamingText('')
      await queryClient.invalidateQueries({ queryKey: ['chat', 'history', currentThreadId] })
      queryClient.invalidateQueries({ queryKey: ['threads'] })
    }
  }

  const handleAttachmentPick = async (files: FileList | null) => {
    if (!files || !currentThreadId || files.length === 0) return

    setError(null)
    for (const file of Array.from(files)) {
      await uploadAttachmentMutation.mutateAsync({ threadId: currentThreadId, file })
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const startRename = (thread: Thread) => {
    setRenamingId(thread.id)
    setRenameValue(thread.name)
  }

  const commitRename = (id: string) => {
    if (renameValue.trim()) {
      renameThreadMutation.mutate({ id, name: renameValue.trim() })
    } else {
      setRenamingId(null)
    }
  }

  if (!currentThreadId) {
    return (
      <div className="app-shell flex h-screen">
        <input
          ref={tabularFileInputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.xls,.ods"
          className="hidden"
          onChange={(e) => void handleTabularFilePick(e.target.files)}
        />
        <ChatSidebar
          threads={threads}
          activeThreadId={activeThreadId}
          isLoading={threadsQuery.isLoading}
          isCreatingNew={createThreadMutation.isPending}
          renamingId={renamingId}
          renameValue={renameValue}
          onSelectThread={setActiveThreadId}
          onCreateNew={() => createThreadMutation.mutate()}
          onStartRename={startRename}
          onCommitRename={commitRename}
          onRenameChange={setRenameValue}
          onDelete={(id) => deleteThreadMutation.mutate(id)}
          onLogout={() => logoutMutation.mutate()}
        />
        <div className="flex flex-1 items-center justify-center px-6 text-slate-400">
          <div className="ui-empty-state px-8 py-7 text-center">
            <p className="text-lg font-medium text-slate-200">Select a chat or create a new one</p>
            <p className="mt-1 text-sm text-slate-400">Your conversations will appear here.</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell flex h-screen">
      <input
        ref={tabularFileInputRef}
        type="file"
        accept=".csv,.tsv,.xlsx,.xls,.ods"
        className="hidden"
        onChange={(e) => void handleTabularFilePick(e.target.files)}
      />
      {/* Sidebar */}
      <ChatSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        isLoading={threadsQuery.isLoading}
        isCreatingNew={createThreadMutation.isPending}
        renamingId={renamingId}
        renameValue={renameValue}
        onSelectThread={setActiveThreadId}
        onCreateNew={() => createThreadMutation.mutate()}
        onStartRename={startRename}
        onCommitRename={commitRename}
        onRenameChange={setRenameValue}
        onDelete={(id) => deleteThreadMutation.mutate(id)}
        onLogout={() => logoutMutation.mutate()}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b border-slate-800/80 bg-slate-900/55 px-5 py-4 backdrop-blur-sm sm:px-6">
          <h1 className="text-base font-semibold text-slate-100 sm:text-lg">{activeThread?.name ?? 'Chat'}</h1>
        </div>

        {/* Messages Container */}
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-6">
          {historyQuery.isLoading && (
            <div className="ui-surface-accent px-4 py-3 text-sm text-slate-300">Loading messages…</div>
          )}

          {historyQuery.isError && (
            <div className="ui-error-banner px-4 py-3 text-sm">Failed to load messages.</div>
          )}

          {/* Timeline: messages + generated images in chronological order */}
          {timelineItems.map((item) => (
            item.kind === 'message'
              ? (
                <MessageBubble
                  key={`m-${item.id}`}
                  message={item.message}
                  attachments={attachments}
                />
              )
              : (
                <GeneratedImageBubble
                  key={`i-${item.id}`}
                  dataUrl={`data:${item.image.mime_type || 'image/png'};base64,${item.image.image_base64}`}
                />
              )
          ))}

          {/* Streaming text */}
          {streamingText && (
            <div className="flex justify-start">
              <div className="ui-assistant-bubble w-full max-w-3xl rounded-xl rounded-bl-sm px-4 py-3">
                <MessageContentRenderer content={streamingText} />
              </div>
            </div>
          )}

          {/* Typing indicator */}
          {sending && !streamingText && <TypingBubble />}

          {/* Error message */}
          {error && (
            <div className="flex justify-center">
              <div className="ui-error-banner px-4 py-2">
                <p className="text-sm">{error}</p>
              </div>
            </div>
          )}

          {/* Auto-scroll anchor */}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-800/80 bg-slate-900/55 backdrop-blur-sm">
          {selectedAttachments.length > 0 && (
            <AttachmentPanel
              attachments={selectedAttachments}
              onRemove={(id) => removeAttachmentMutation.mutate(id)}
            />
          )}

          {/* Input Box */}
          <div className="space-y-3 px-4 py-4 sm:px-6">
            <div className="ui-surface rounded-xl border border-emerald-900/40 px-3 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setDatabaseModeEnabled((previous) => !previous)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${databaseModeEnabled ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-200 hover:bg-slate-700'}`}
                >
                  {databaseModeEnabled ? 'DB Mode On' : 'DB Mode Off'}
                </button>

                {databaseModeEnabled && !databaseConnected && (
                  <>
                    <button
                      onClick={() => setDatabaseConnectMode('automatic')}
                      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${databaseConnectMode === 'automatic' ? 'bg-emerald-500/30 text-emerald-100 border border-emerald-400/40' : 'bg-slate-800 text-slate-200 hover:bg-slate-700'}`}
                    >
                      Auto Connect
                    </button>
                    <button
                      onClick={() => setDatabaseConnectMode('manual')}
                      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${databaseConnectMode === 'manual' ? 'bg-emerald-500/30 text-emerald-100 border border-emerald-400/40' : 'bg-slate-800 text-slate-200 hover:bg-slate-700'}`}
                    >
                      Manual Connect
                    </button>
                    <button
                      onClick={() => databaseConnectMutation.mutate()}
                      disabled={databaseConnectMutation.isPending}
                      className="ui-btn-secondary rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                    >
                      {databaseConnectMutation.isPending ? 'Connecting…' : 'Connect DB'}
                    </button>
                  </>
                )}

                {databaseModeEnabled && databaseConnected && (
                  <>
                    <span className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-1.5 text-xs font-medium text-emerald-100">
                      DB Mode On: Connected
                    </span>
                    <button
                      onClick={() => {
                        setDatabaseConnected(false)
                        setDatabaseStatusMessage(null)
                      }}
                      className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700"
                    >
                      Change DB
                    </button>
                  </>
                )}
              </div>

              {databaseModeEnabled && !databaseConnected && databaseConnectMode === 'manual' && (
                <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <select
                    value={manualDatabaseConnection.db_type ?? 'postgresql'}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, db_type: event.target.value as 'postgresql' | 'mysql' | 'sqlite' | 'supabase' }))}
                    className="ui-input text-xs"
                  >
                    <option value="postgresql">PostgreSQL</option>
                    <option value="mysql">MySQL</option>
                    <option value="sqlite">SQLite</option>
                    <option value="supabase">Supabase</option>
                  </select>
                  <input
                    value={manualDatabaseConnection.host ?? ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, host: event.target.value }))}
                    className="ui-input text-xs"
                    placeholder="Host"
                  />
                  <input
                    value={manualDatabaseConnection.port ? String(manualDatabaseConnection.port) : ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, port: event.target.value ? Number(event.target.value) : undefined }))}
                    className="ui-input text-xs"
                    placeholder="Port"
                  />
                  <input
                    value={manualDatabaseConnection.database ?? ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, database: event.target.value }))}
                    className="ui-input text-xs"
                    placeholder="Database"
                  />
                  <input
                    value={manualDatabaseConnection.username ?? ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, username: event.target.value }))}
                    className="ui-input text-xs"
                    placeholder="Username"
                  />
                  <input
                    type="password"
                    value={manualDatabaseConnection.password ?? ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, password: event.target.value }))}
                    className="ui-input text-xs"
                    placeholder="Password"
                  />
                  <input
                    value={manualDatabaseConnection.schema ?? ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, schema: event.target.value }))}
                    className="ui-input text-xs"
                    placeholder="Schema (optional)"
                  />
                  <input
                    value={manualDatabaseConnection.url ?? ''}
                    onChange={(event) => setManualDatabaseConnection((current) => ({ ...current, url: event.target.value }))}
                    className="ui-input text-xs"
                    placeholder="Full URL or public CSV/Google Sheet URL"
                  />
                </div>
              )}

              {databaseModeEnabled && (
                <p className="mt-2 text-xs text-slate-400">
                  {databaseConnected
                    ? 'DB Mode On. Ask natural-language DB questions directly in the prompt area.'
                    : databaseStatusMessage
                      ? `${databaseStatusMessage} You can now ask natural language questions in this chat.`
                      : 'Enable DB mode and connect first. Then ask natural language database questions in this same chat.'}
                </p>
              )}
            </div>

            <div className="flex gap-3">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => handleAttachmentPick(e.target.files)}
              />
              <div ref={tabularPanelRef} className="relative flex shrink-0 gap-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadAttachmentMutation.isPending}
                  className="ui-btn-secondary shrink-0 px-3 py-3 disabled:opacity-50"
                  title="Attach files"
                >
                  📎
                </button>
                <button
                  type="button"
                  onClick={() => setTabularPanelOpen((current) => !current)}
                  className={`ui-btn-secondary shrink-0 px-3 py-3 text-xs font-semibold ${tabularModeEnabled ? 'border-emerald-400/70 text-emerald-100' : ''}`}
                  title="Excel / GSheet QA"
                >
                  ▦
                </button>
                <button
                  type="button"
                  onClick={() => setResearchPanelOpen((current) => !current)}
                  className={`ui-btn-secondary shrink-0 px-3 py-3 text-xs font-semibold ${researchQuery ? 'border-emerald-400/70 text-emerald-100' : ''}`}
                  title="Research Digest (arXiv)"
                >
                  🔬
                </button>

                {tabularPanelOpen && (
                  <div className="ui-surface-accent absolute bottom-full left-0 z-20 mb-2 w-72 px-3 py-3 shadow-2xl">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-emerald-200/80">Excel / GSheet QA</p>
                    <div className="space-y-2">
                      <button
                        type="button"
                        onClick={() => tabularFileInputRef.current?.click()}
                        disabled={sending}
                        className="ui-btn-secondary w-full rounded-lg px-3 py-2 text-xs font-medium disabled:opacity-50"
                      >
                        Upload Excel
                      </button>
                      <input
                        value={tabularGSheetUrl}
                        onChange={(e) => setTabularGSheetUrl(e.target.value)}
                        placeholder="Load GSheet URL"
                        className="ui-input px-2.5 py-1.5 text-xs"
                      />
                      <button
                        type="button"
                        onClick={handleTabularLoadGSheet}
                        disabled={sending || !tabularGSheetUrl.trim()}
                        className="ui-btn-secondary w-full rounded-lg px-3 py-2 text-xs font-medium disabled:opacity-50"
                      >
                        Load GSheet
                      </button>
                      <label className="flex items-center justify-between rounded-lg border border-slate-800/70 bg-slate-950/40 px-2.5 py-2 text-xs text-slate-300">
                        <span>Query Tabular</span>
                        <input
                          type="checkbox"
                          checked={tabularModeEnabled}
                          onChange={(e) => setTabularModeEnabled(e.target.checked)}
                          disabled={sending || !tabularSourceLabel}
                        />
                      </label>
                      <p className="truncate text-[11px] text-slate-400">
                        Source: {tabularSourceLabel ?? 'None selected'}
                      </p>
                    </div>
                  </div>
                )}

                {researchPanelOpen && (
                  <div
                    ref={researchPanelRef}
                    className="ui-surface-accent absolute bottom-full left-0 z-20 mb-2 w-72 px-3 py-3 shadow-2xl"
                  >
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-blue-200/80">Research Digest (arXiv)</p>
                    <div className="space-y-2">
                      <input
                        value={researchQuery}
                        onChange={(e) => setResearchQuery(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            void handleResearchDigest()
                          }
                        }}
                        placeholder="Research topic or keywords"
                        className="ui-input px-2.5 py-1.5 text-xs w-full"
                      />
                      <button
                        type="button"
                        onClick={() => void handleResearchDigest()}
                        disabled={sending || !researchQuery.trim()}
                        className="ui-btn-secondary w-full rounded-lg px-3 py-2 text-xs font-medium disabled:opacity-50"
                      >
                        {sending ? 'Searching…' : 'Search & Digest'}
                      </button>
                      <p className="text-[11px] text-slate-400">
                        Searches arXiv for papers and generates a structured research digest.
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex-1">
                <AutoResizeTextarea
                  value={input}
                  onChange={setInput}
                  onKeyDown={handleKeyDown}
                  placeholder={databaseModeEnabled
                    ? 'Ask a natural-language database question…'
                    : 'Type a message… (/image for generation, /validate for selected image validation)'}
                  disabled={sending}
                  maxRows={6}
                />
              </div>

              <button
                onClick={handleSend}
                disabled={sending || !input.trim()}
                className="ui-btn-primary shrink-0 px-4 py-3 disabled:opacity-50"
                title="Send message"
              >
                {sending ? '⏳' : '→'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
