import { useMutation } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../lib/api'
import type {
  Attachment,
  ImageValidationBatchResult,
  ImageValidationBatchItem,
  ImageValidationRuleInput,
  ImageValidationRuleResult,
} from '../types'

// ---------------------------------------------------------------------------
// Default rules catalogue (mirrors backend defaults — informational only)
// ---------------------------------------------------------------------------
const DEFAULT_RULES_INFO = [
  { rule_id: 'mime_type_allowed', description: 'MIME type must be PNG, JPEG, or WebP', field_path: 'metadata.mime_type', operator: 'in' },
  { rule_id: 'max_size_5mb', description: 'File size ≤ 5 MB', field_path: 'metadata.size_bytes', operator: 'lte' },
  { rule_id: 'min_width_512', description: 'Width ≥ 512 px', field_path: 'metadata.width', operator: 'gte' },
  { rule_id: 'min_height_512', description: 'Height ≥ 512 px', field_path: 'metadata.height', operator: 'gte' },
]

const OPERATORS = ['exists', 'not_empty', 'eq', 'neq', 'contains', 'not_contains', 'in', 'regex', 'gte', 'lte']

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type RuleDraft = ImageValidationRuleInput & { _id: string }

type UploadedImage = {
  attachment: Attachment
  previewUrl: string | null
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function uid() {
  return Math.random().toString(36).slice(2)
}

function passBadge(passed: boolean) {
  return passed
    ? <span className="inline-flex items-center rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300 border border-emerald-400/20">PASS</span>
    : <span className="inline-flex items-center rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-semibold text-rose-300 border border-rose-400/20">FAIL</span>
}

function RuleResultRow({ rule }: { rule: ImageValidationRuleResult }) {
  return (
    <tr className="border-t border-slate-800/50">
      <td className="py-1.5 pr-3 align-top text-xs text-slate-300">{rule.rule_id}</td>
      <td className="py-1.5 pr-3 align-top text-xs text-slate-400">{rule.description}</td>
      <td className="py-1.5 pr-3 align-top text-xs text-slate-400">{String(rule.extracted ?? '—')}</td>
      <td className="py-1.5 align-top text-xs">{passBadge(rule.passed)}</td>
    </tr>
  )
}

function ImageResultCard({ item }: { item: ImageValidationBatchItem }) {
  const [open, setOpen] = useState(!item.success || (item.result && !item.result.passed))

  if (!item.success) {
    return (
      <div className="rounded-xl border border-rose-400/25 bg-rose-500/10 p-4">
        <div className="flex items-center gap-3">
          {passBadge(false)}
          <span className="text-sm font-medium text-slate-100 truncate">{item.image_id}</span>
        </div>
        <p className="mt-2 text-xs text-rose-300">{item.error ?? 'Unknown error'}</p>
      </div>
    )
  }

  const r = item.result!
  const meta = r.extracted_data.metadata as Record<string, unknown>

  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-950/30">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left hover:bg-slate-800/30 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          {passBadge(r.passed)}
          <span className="truncate text-sm font-medium text-slate-100">{r.source_name}</span>
          <span className="hidden sm:inline text-xs text-slate-500">{r.image_id}</span>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-xs text-slate-400">
          <span>{r.rule_results.filter(x => x.passed).length}/{r.rule_results.length} rules passed</span>
          <span className="text-slate-600">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {open && (
        <div className="border-t border-slate-800/50 px-4 pb-4 pt-3 space-y-4">
          {/* Extracted metadata */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-500">Extracted Data</p>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ['Format', meta.format],
                ['MIME', meta.mime_type],
                ['Size', meta.size_bytes ? `${Math.round(Number(meta.size_bytes) / 1024)} KB` : '—'],
                ['Dimensions', meta.width && meta.height ? `${meta.width}×${meta.height}` : '—'],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border border-slate-800/60 bg-slate-950/40 px-3 py-2">
                  <p className="text-xs text-slate-500">{String(label)}</p>
                  <p className="mt-0.5 text-sm font-medium text-slate-200 truncate">{String(value ?? '—')}</p>
                </div>
              ))}
            </div>

            {r.extracted_data.text && (
              <div className="mt-3 rounded-lg border border-slate-800/60 bg-slate-950/40 p-3">
                <p className="mb-1 text-xs text-slate-500">Extracted Text</p>
                <p className="whitespace-pre-wrap text-xs text-slate-200">{r.extracted_data.text}</p>
              </div>
            )}

            {r.extracted_data.labels.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {r.extracted_data.labels.map((label) => (
                  <span key={label} className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-200">{label}</span>
                ))}
              </div>
            )}

            {Object.keys(r.extracted_data.fields).length > 0 && (
              <div className="mt-3 rounded-lg border border-slate-800/60 bg-slate-950/40 p-3">
                <p className="mb-2 text-xs text-slate-500">Extracted Fields</p>
                <div className="grid gap-1 sm:grid-cols-2">
                  {Object.entries(r.extracted_data.fields).map(([k, v]) => (
                    <div key={k} className="flex gap-2 text-xs">
                      <span className="font-medium text-slate-400 shrink-0">{k}:</span>
                      <span className="text-slate-200 truncate">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Rule results table */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-500">Rule Results</p>
            <div className="overflow-x-auto rounded-xl border border-slate-800/60">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-800/60 bg-slate-900/50">
                    <th className="px-3 py-2 text-xs font-medium text-slate-400">Rule</th>
                    <th className="px-3 py-2 text-xs font-medium text-slate-400">Field / Description</th>
                    <th className="px-3 py-2 text-xs font-medium text-slate-400">Extracted Value</th>
                    <th className="px-3 py-2 text-xs font-medium text-slate-400">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40">
                  {r.rule_results.map((rule) => (
                    <RuleResultRow key={rule.rule_id} rule={rule} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function ImageRulePage() {
  // --- state -----------------------------------------------------------------
  const [includeDefaults, setIncludeDefaults] = useState(true)
  const [customRules, setCustomRules] = useState<RuleDraft[]>([])
  const [ruleDraft, setRuleDraft] = useState<Omit<RuleDraft, '_id'>>({
    rule_id: '',
    description: '',
    field_path: 'extracted.fields.',
    operator: 'not_empty',
    expected: undefined,
    required: true,
  })

  const [images, setImages] = useState<UploadedImage[]>([])
  const [sessionThreadId, setSessionThreadId] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [batchResult, setBatchResult] = useState<ImageValidationBatchResult | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  // --- mutations -------------------------------------------------------------
  const createThreadMutation = useMutation({ mutationFn: api.createThread })

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      let threadId = sessionThreadId
      if (!threadId) {
        const thread = await createThreadMutation.mutateAsync()
        threadId = thread.id
        setSessionThreadId(thread.id)
      }
      return api.uploadAttachment(threadId, file)
    },
    onError: (err: Error) => setUploadError(err.message),
  })

  const validateMutation = useMutation({
    mutationFn: () =>
      api.validateImagesBatch({
        image_ids: images.map((img) => img.attachment.id),
        include_default_rules: includeDefaults,
        rules: customRules.map(({ _id, ...rule }) => ({
          ...rule,
          expected: rule.expected === '' ? undefined : rule.expected,
        })),
      }),
    onSuccess: (data) => setBatchResult(data),
    onError: (err: Error) => setUploadError(err.message),
  })

  // --- handlers --------------------------------------------------------------
  const handleFileDrop = useCallback(async (files: FileList | null) => {
    if (!files) return
    setUploadError(null)
    for (const file of Array.from(files)) {
      try {
        const attachment = await uploadMutation.mutateAsync(file)
        const previewUrl = file.type.startsWith('image/') ? URL.createObjectURL(file) : null
        setImages((prev) => [...prev, { attachment, previewUrl }])
      } catch {
        // uploadMutation.onError handles display
      }
    }
  }, [uploadMutation])

  const removeImage = (id: string) => {
    setImages((prev) => {
      const removed = prev.find((img) => img.attachment.id === id)
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
      return prev.filter((img) => img.attachment.id !== id)
    })
  }

  const addRule = () => {
    if (!ruleDraft.rule_id.trim() || !ruleDraft.field_path.trim()) return
    setCustomRules((prev) => [...prev, { ...ruleDraft, _id: uid() }])
    setRuleDraft({ rule_id: '', description: '', field_path: 'extracted.fields.', operator: 'not_empty', expected: undefined, required: true })
  }

  const removeRule = (id: string) => setCustomRules((prev) => prev.filter((r) => r._id !== id))

  // --- summary ---------------------------------------------------------------
  const summaryCards = batchResult
    ? [
        { label: 'Total Images', value: batchResult.total_images },
        { label: 'Processed', value: batchResult.processed_images },
        { label: 'Passed', value: batchResult.passed_images, color: 'text-emerald-300' },
        { label: 'Failed', value: batchResult.failed_images, color: 'text-rose-300' },
      ]
    : null

  // ---------------------------------------------------------------------------
  return (
    <main className="app-shell min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">

        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-emerald-200/70">Project 8</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-50">Image Rule Checker</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-300">
              Upload images, define a set of extraction rules, and check each image against those rules.
              The AI extracts text, labels, and field values from each image, then evaluates every rule automatically.
            </p>
          </div>
          <Link to="/chat" className="ui-btn-secondary inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium whitespace-nowrap">
            ← Back to Chat
          </Link>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(340px,420px)_1fr]">

          {/* ---------------------------------------------------------------- */}
          {/* Left: Rules + Images                                              */}
          {/* ---------------------------------------------------------------- */}
          <div className="flex flex-col gap-6">

            {/* Default rules toggle */}
            <section className="ui-surface-accent p-5">
              <h2 className="mb-3 text-lg font-semibold text-slate-100">Rules</h2>

              <label className="mb-4 flex items-center gap-3 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeDefaults}
                  onChange={(e) => setIncludeDefaults(e.target.checked)}
                  className="rounded"
                />
                Include default rules
              </label>

              {includeDefaults && (
                <div className="mb-4 rounded-xl border border-slate-700/50 divide-y divide-slate-800/50">
                  {DEFAULT_RULES_INFO.map((r) => (
                    <div key={r.rule_id} className="flex items-start justify-between gap-2 px-3 py-2">
                      <div>
                        <p className="text-xs font-medium text-slate-200">{r.rule_id}</p>
                        <p className="text-xs text-slate-400">{r.description}</p>
                      </div>
                      <span className="shrink-0 rounded-md bg-slate-800/70 px-2 py-0.5 text-xs text-slate-400">{r.operator}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Custom rule builder */}
              <div className="space-y-3 rounded-xl border border-slate-700/40 bg-slate-900/30 p-4">
                <p className="text-sm font-medium text-slate-200">Add Custom Rule</p>

                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1 block text-xs text-slate-400">Rule ID</span>
                    <input value={ruleDraft.rule_id} onChange={(e) => setRuleDraft((d) => ({ ...d, rule_id: e.target.value }))} className="ui-input text-sm" placeholder="invoice_number_required" />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs text-slate-400">Description</span>
                    <input value={ruleDraft.description} onChange={(e) => setRuleDraft((d) => ({ ...d, description: e.target.value }))} className="ui-input text-sm" placeholder="Optional description" />
                  </label>
                </div>

                <label className="block">
                  <span className="mb-1 block text-xs text-slate-400">Field Path</span>
                  <input value={ruleDraft.field_path} onChange={(e) => setRuleDraft((d) => ({ ...d, field_path: e.target.value }))} className="ui-input font-mono text-sm" placeholder="extracted.fields.invoice_number" />
                  <p className="mt-1 text-xs text-slate-500">Paths: <code className="text-emerald-300/80">metadata.width</code>, <code className="text-emerald-300/80">extracted.text</code>, <code className="text-emerald-300/80">extracted.fields.KEY</code></p>
                </label>

                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1 block text-xs text-slate-400">Operator</span>
                    <select value={ruleDraft.operator} onChange={(e) => setRuleDraft((d) => ({ ...d, operator: e.target.value }))} className="ui-input text-sm">
                      {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs text-slate-400">Expected Value</span>
                    <input value={String(ruleDraft.expected ?? '')} onChange={(e) => setRuleDraft((d) => ({ ...d, expected: e.target.value }))} className="ui-input text-sm" placeholder="e.g. INV- or 512" />
                  </label>
                </div>

                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input type="checkbox" checked={ruleDraft.required} onChange={(e) => setRuleDraft((d) => ({ ...d, required: e.target.checked }))} />
                  Required (failure blocks overall pass)
                </label>

                <button type="button" onClick={addRule} disabled={!ruleDraft.rule_id.trim() || !ruleDraft.field_path.trim()} className="ui-btn-primary rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-40 w-full">
                  + Add Rule
                </button>
              </div>

              {/* Custom rules list */}
              {customRules.length > 0 && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs font-medium text-slate-400">Custom Rules ({customRules.length})</p>
                  {customRules.map((rule) => (
                    <div key={rule._id} className="flex items-start justify-between gap-2 rounded-lg border border-emerald-400/20 bg-emerald-500/5 px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-slate-200">{rule.rule_id}</p>
                        <p className="text-xs text-slate-400 font-mono truncate">{rule.field_path} <span className="text-emerald-300/70">{rule.operator}</span>{rule.expected !== undefined && rule.expected !== '' ? <span className="text-slate-400"> {String(rule.expected)}</span> : null}</p>
                      </div>
                      <button type="button" onClick={() => removeRule(rule._id)} className="shrink-0 text-xs text-rose-400 hover:text-rose-300">Remove</button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Images upload */}
            <section className="ui-surface p-5">
              <h2 className="mb-3 text-lg font-semibold text-slate-100">Images</h2>
              <p className="mb-3 text-xs text-slate-400">Upload images to check. Files are stored in a session thread automatically.</p>

              {/* Drop zone */}
              <div
                className="mb-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-700 bg-slate-900/30 py-8 transition-colors hover:border-emerald-400/40 hover:bg-emerald-500/5"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); void handleFileDrop(e.dataTransfer.files) }}
              >
                <span className="text-2xl">🖼️</span>
                <p className="text-sm text-slate-300">Drop images here or <span className="text-emerald-300 underline cursor-pointer">browse</span></p>
                <p className="text-xs text-slate-500">PNG, JPEG, WebP, GIF supported</p>
                {uploadMutation.isPending && <p className="text-xs text-emerald-300 animate-pulse">Uploading…</p>}
              </div>
              <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => void handleFileDrop(e.target.files)} />

              {uploadError && <p className="mb-3 text-xs text-rose-300">{uploadError}</p>}

              {/* Image thumbnails */}
              {images.length > 0 && (
                <div className="grid grid-cols-3 gap-2">
                  {images.map((img) => (
                    <div key={img.attachment.id} className="group relative overflow-hidden rounded-lg border border-slate-700/60">
                      {img.previewUrl
                        ? <img src={img.previewUrl} alt={img.attachment.file_name} className="h-20 w-full object-cover" />
                        : <div className="flex h-20 items-center justify-center bg-slate-800 text-xs text-slate-400">{img.attachment.file_name}</div>
                      }
                      <div className="absolute inset-x-0 bottom-0 bg-linear-to-t from-slate-950/90 to-transparent px-1.5 py-1">
                        <p className="truncate text-[10px] text-slate-300">{img.attachment.file_name}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeImage(img.attachment.id)}
                        className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-rose-500/80 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100"
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Run button */}
            <button
              type="button"
              onClick={() => validateMutation.mutate()}
              disabled={validateMutation.isPending || images.length === 0}
              className="ui-btn-primary rounded-xl px-6 py-3.5 text-base font-semibold disabled:opacity-40"
            >
              {validateMutation.isPending ? 'Checking images…' : `Check ${images.length} image${images.length !== 1 ? 's' : ''} against rules`}
            </button>
          </div>

          {/* ---------------------------------------------------------------- */}
          {/* Right: Results                                                    */}
          {/* ---------------------------------------------------------------- */}
          <div className="flex flex-col gap-6">
            {!batchResult ? (
              <div className="ui-surface flex flex-col items-center justify-center gap-3 py-24 text-center">
                <span className="text-4xl">🔍</span>
                <p className="text-lg font-medium text-slate-200">No results yet</p>
                <p className="max-w-xs text-sm text-slate-400">
                  Upload images and configure rules on the left, then click <strong className="text-slate-200">Check images</strong>.
                  The AI will extract data from each image and evaluate it against every rule.
                </p>
              </div>
            ) : (
              <>
                {/* Summary */}
                <section className="ui-surface p-5">
                  <h2 className="mb-4 text-lg font-semibold text-slate-100">Validation Summary</h2>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {summaryCards!.map(({ label, value, color }) => (
                      <div key={label} className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4 text-center">
                        <p className={`text-2xl font-bold ${color ?? 'text-slate-100'}`}>{value}</p>
                        <p className="mt-1 text-xs text-slate-400">{label}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-sm text-slate-300">{batchResult.summary}</p>
                </section>

                {/* Per-image results */}
                <section className="ui-surface p-5">
                  <h2 className="mb-4 text-lg font-semibold text-slate-100">Per-Image Results</h2>
                  <div className="space-y-3">
                    {batchResult.results.map((item) => (
                      <ImageResultCard key={item.image_id} item={item} />
                    ))}
                  </div>
                </section>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
