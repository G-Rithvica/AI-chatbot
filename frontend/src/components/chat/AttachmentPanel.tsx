import type { Attachment } from '../../types'

interface AttachmentPanelProps {
  attachments: Attachment[]
  onRemove: (attachmentId: string) => void
}

export function AttachmentPanel({ attachments, onRemove }: AttachmentPanelProps) {
  return (
    <div className="space-y-3 border-t border-slate-700/70 bg-slate-900/65 px-4 py-3">
      {attachments.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold text-slate-400">Attached Files</p>
          <div className="flex flex-wrap gap-2">
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                className="inline-flex items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-400/10 px-3 py-1.5 text-xs text-slate-100"
              >
                <span className="font-semibold text-emerald-100">{attachment.kind.toUpperCase()}</span>
                <span className="max-w-28 truncate">{attachment.file_name}</span>
                <button
                  type="button"
                  onClick={() => onRemove(attachment.id)}
                  className="ml-1 font-bold text-slate-500 transition hover:text-rose-300"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
