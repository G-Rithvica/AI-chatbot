import { useEffect, useRef } from 'react'

interface AutoResizeTextareaProps {
  value: string
  onChange: (value: string) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  placeholder?: string
  disabled?: boolean
  maxRows?: number
}

export function AutoResizeTextarea({
  value,
  onChange,
  onKeyDown,
  placeholder,
  disabled,
  maxRows = 8,
}: AutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      const scrollHeight = textareaRef.current.scrollHeight
      const lineHeight = parseInt(window.getComputedStyle(textareaRef.current).lineHeight, 10)
      const lines = Math.ceil(scrollHeight / lineHeight)
      const limitedHeight = Math.min(lines, maxRows) * lineHeight
      textareaRef.current.style.height = `${limitedHeight}px`
    }
  }, [value, maxRows])

  return (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      disabled={disabled}
      rows={1}
      className="ui-input resize-none"
    />
  )
}
