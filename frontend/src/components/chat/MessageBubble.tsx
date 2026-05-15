import type { Attachment, ChatMessage } from '../../types'
import { fileTypeBadge, toAbsoluteAttachmentUrl } from '../../lib/messageHelpers'

type TableAlignment = 'left' | 'center' | 'right'

type ContentBlock =
  | { kind: 'text'; text: string }
  | { kind: 'table'; header: string[]; rows: string[][]; alignments: TableAlignment[] }

interface MessageBubbleProps {
  message: ChatMessage
  attachments: Attachment[]
  onAttachmentClick?: (attachment: Attachment) => void
}

function parseMessageContent(content: string): { text: string; attachedFileNames: string[]; usedFileNames: string[] } {
  let text = content
  let attachedFileNames: string[] = []
  let usedFileNames: string[] = []

  const attachedMatch = text.match(/\n\n\[Attached files:\s*([^\]]+)\]\s*$/)
  if (attachedMatch) {
    attachedFileNames = attachedMatch[1].split(',').map((item) => item.trim()).filter(Boolean)
    text = text.replace(/\n\n\[Attached files:\s*([^\]]+)\]\s*$/, '').trim()
  }

  const usedMatch = text.match(/\n\n\[Used files:\s*([^\]]+)\]\s*$/)
  if (usedMatch) {
    usedFileNames = usedMatch[1].split(',').map((item) => item.trim()).filter(Boolean)
    text = text.replace(/\n\n\[Used files:\s*([^\]]+)\]\s*$/, '').trim()
  }

  return { text, attachedFileNames, usedFileNames }
}

function splitPipedRow(line: string): string[] {
  const trimmed = line.trim()
  const normalized = trimmed.replace(/^\|/, '').replace(/\|$/, '')
  return normalized.split('|').map((cell) => cell.trim())
}

function parseSeparatorAlignments(separatorLine: string): TableAlignment[] | null {
  const cells = splitPipedRow(separatorLine)
  if (cells.length < 2) {
    return null
  }

  const alignments: TableAlignment[] = []
  for (const rawCell of cells) {
    const cell = rawCell.replace(/\s+/g, '')
    if (!/^:?-{3,}:?$/.test(cell)) {
      return null
    }

    const left = cell.startsWith(':')
    const right = cell.endsWith(':')
    if (left && right) {
      alignments.push('center')
    } else if (right) {
      alignments.push('right')
    } else {
      alignments.push('left')
    }
  }

  return alignments
}

function parseContentBlocks(content: string): ContentBlock[] {
  const lines = content.split('\n')
  const blocks: ContentBlock[] = []
  let index = 0

  const isTableStartAt = (lineIndex: number): boolean => {
    if (lineIndex + 1 >= lines.length) {
      return false
    }

    const headerLine = lines[lineIndex]
    const separatorLine = lines[lineIndex + 1]
    if (!headerLine.includes('|') || !separatorLine.includes('|')) {
      return false
    }

    const headerCells = splitPipedRow(headerLine)
    const alignments = parseSeparatorAlignments(separatorLine)
    return headerCells.length >= 2 && !!alignments && alignments.length === headerCells.length
  }

  const isLenientTableStartAt = (lineIndex: number): boolean => {
    if (lineIndex + 1 >= lines.length) {
      return false
    }

    const first = lines[lineIndex]
    const second = lines[lineIndex + 1]
    if (!first.includes('|') || !second.includes('|')) {
      return false
    }

    const firstCells = splitPipedRow(first)
    const secondCells = splitPipedRow(second)
    if (firstCells.length < 2 || secondCells.length < 2) {
      return false
    }

    // If strict separator exists, strict parser should handle it.
    if (parseSeparatorAlignments(second)) {
      return false
    }

    // Guard against parsing simple sentence fragments with a single pipe.
    return firstCells.length >= 2 && secondCells.length >= 2
  }

  while (index < lines.length) {
    if (isTableStartAt(index)) {
      const headerCells = splitPipedRow(lines[index])
      const alignments = parseSeparatorAlignments(lines[index + 1]) ?? new Array(headerCells.length).fill('left')
      index += 2

      const rows: string[][] = []
      while (index < lines.length) {
        const line = lines[index]
        if (!line.trim()) {
          const nextLine = lines[index + 1]
          if (nextLine && nextLine.includes('|')) {
            index += 1
            continue
          }
          break
        }
        if (!line.includes('|')) {
          break
        }

        const rowCells = splitPipedRow(line)
        if (rowCells.length < 2) {
          break
        }

        const padded = [...rowCells]
        while (padded.length < headerCells.length) {
          padded.push('')
        }
        rows.push(padded.slice(0, headerCells.length))
        index += 1
      }

      blocks.push({
        kind: 'table',
        header: headerCells,
        rows,
        alignments: alignments.slice(0, headerCells.length),
      })
      continue
    }

    if (isLenientTableStartAt(index)) {
      const headerCells = splitPipedRow(lines[index])
      index += 1

      const rows: string[][] = []
      while (index < lines.length) {
        const line = lines[index]
        if (!line.trim()) {
          const nextLine = lines[index + 1]
          if (nextLine && nextLine.includes('|')) {
            index += 1
            continue
          }
          break
        }
        if (!line.includes('|')) {
          break
        }

        // Skip separator rows if they appear later in malformed outputs.
        if (parseSeparatorAlignments(line)) {
          index += 1
          continue
        }

        const rowCells = splitPipedRow(line)
        if (rowCells.length < 2) {
          break
        }

        const padded = [...rowCells]
        while (padded.length < headerCells.length) {
          padded.push('')
        }
        rows.push(padded.slice(0, headerCells.length))
        index += 1
      }

      blocks.push({
        kind: 'table',
        header: headerCells,
        rows,
        alignments: new Array(headerCells.length).fill('left'),
      })
      continue
    }

    const textLines: string[] = []
    while (index < lines.length && !isTableStartAt(index) && !isLenientTableStartAt(index)) {
      textLines.push(lines[index])
      index += 1
    }

    const text = textLines.join('\n').trim()
    if (text) {
      blocks.push({ kind: 'text', text })
    }
  }

  return blocks
}

export function MessageContentRenderer({ content }: { content: string }) {
  const blocks = parseContentBlocks(content)

  if (!blocks.length) {
    return null
  }

  return (
    <div className="space-y-3">
      {blocks.map((block, blockIndex) => {
        if (block.kind === 'text') {
          return (
            <p key={`text-${blockIndex}`} className="whitespace-pre-wrap text-sm leading-relaxed wrap-break-word">
              {block.text}
            </p>
          )
        }

        return (
          <div key={`table-${blockIndex}`} className="ui-chat-table-wrap rounded-lg border border-slate-700/70">
            <table className="ui-chat-table border-collapse text-sm">
              <thead>
                <tr>
                  {block.header.map((cell, cellIndex) => (
                    <th
                      key={`head-${cellIndex}`}
                      className="ui-chat-table-th"
                      style={{ textAlign: block.alignments[cellIndex] ?? 'left' }}
                    >
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={`row-${rowIndex}`} className="ui-chat-table-row">
                    {row.map((cell, cellIndex) => (
                      <td
                        key={`cell-${rowIndex}-${cellIndex}`}
                        className="ui-chat-table-td"
                        style={{ textAlign: block.alignments[cellIndex] ?? 'left' }}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}

export function MessageBubble({ message, attachments, onAttachmentClick }: MessageBubbleProps) {
  const parsed = parseMessageContent(message.content)
  const isUser = message.role === 'user'

  return (
    <div className={`mb-4 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`${isUser ? 'w-fit max-w-[80%] sm:max-w-[72%]' : 'w-full max-w-3xl'} h-auto overflow-visible rounded-xl px-4 py-3 shadow-sm ${
          isUser
            ? 'ui-user-bubble rounded-br-sm text-white'
            : 'ui-assistant-bubble rounded-bl-sm text-slate-100'
        }`}
      >
        {/* Main message text */}
        <MessageContentRenderer content={parsed.text} />

        {/* Attached files */}
        {parsed.attachedFileNames.length > 0 && (
          <div className="mt-3 border-t border-white/20 pt-3">
            <p className="mb-2 text-xs font-semibold opacity-80">Attachments</p>
            <div className="flex flex-wrap gap-1.5">
              {parsed.attachedFileNames.map((name) => {
                const attachment = attachments.find((item) => item.file_name === name)
                const badge = fileTypeBadge(attachment, name)
                return (
                  <a
                    key={name}
                    href={attachment ? toAbsoluteAttachmentUrl(attachment.url) : '#'}
                    target="_blank"
                    rel="noreferrer"
                    onClick={() => {
                      if (attachment) {
                        onAttachmentClick?.(attachment)
                      }
                    }}
                    className="rounded-full bg-white/10 px-2 py-1 text-xs underline decoration-dotted transition hover:bg-white/20"
                  >
                    <span className="mr-1">{badge}</span>
                    {name}
                  </a>
                )
              })}
            </div>
          </div>
        )}

        {/* Used files */}
        {parsed.usedFileNames.length > 0 && (
          <div className="mt-3 border-t border-white/20 pt-3">
            <p className="mb-2 text-xs font-semibold opacity-80">Used Files</p>
            <div className="flex flex-wrap gap-1.5">
              {parsed.usedFileNames.map((name) => {
                const attachment = attachments.find((item) => item.file_name === name)
                const badge = fileTypeBadge(attachment, name)
                return (
                  <a
                    key={`used-${name}`}
                    href={attachment ? toAbsoluteAttachmentUrl(attachment.url) : '#'}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-full bg-white/10 px-2 py-1 text-xs underline decoration-dotted transition hover:bg-white/20"
                  >
                    <span className="mr-1">{badge}</span>
                    {name}
                  </a>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function TypingBubble() {
  return (
    <div className="mb-4 flex justify-start">
      <div className="ui-assistant-bubble rounded-xl rounded-bl-sm px-4 py-3 text-slate-100">
        <div className="flex gap-1">
          <div className="ui-loading-dot-1 h-2 w-2 animate-bounce rounded-full" style={{ animationDelay: '0ms' }} />
          <div className="ui-loading-dot-2 h-2 w-2 animate-bounce rounded-full" style={{ animationDelay: '150ms' }} />
          <div className="ui-loading-dot-3 h-2 w-2 animate-bounce rounded-full" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  )
}

export function GeneratedImageBubble({ dataUrl }: { dataUrl: string }) {
  return (
    <div className="mb-4 flex justify-start">
      <div className="ui-image-card w-full max-w-3xl rounded-xl rounded-bl-sm px-4 py-3 text-slate-100">
        <p className="mb-2 text-xs font-semibold text-slate-300">Generated Image</p>
        <img
          src={dataUrl}
          alt="Generated"
          className="h-auto max-w-full rounded-lg border border-slate-600"
        />
      </div>
    </div>
  )
}
