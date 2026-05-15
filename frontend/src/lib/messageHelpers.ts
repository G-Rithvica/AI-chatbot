import type { Attachment } from '../types'
import { apiClient } from './api'

export function toAbsoluteAttachmentUrl(url: string): string {
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }
  const base = apiClient.baseUrl.replace(/\/$/, '')
  const suffix = url.startsWith('/') ? url : `/${url}`
  return `${base}${suffix}`
}

export function fileTypeBadge(attachment: Attachment | undefined, fileName: string): string {
  const lower = fileName.toLowerCase()
  if (attachment?.kind === 'image' || attachment?.mime_type.startsWith('image/')) return 'IMG'
  if (attachment?.kind === 'video' || attachment?.mime_type.startsWith('video/')) return 'VID'
  if (lower.endsWith('.pdf')) return 'PDF'
  if (lower.endsWith('.doc') || lower.endsWith('.docx') || lower.endsWith('.odt')) return 'DOC'
  if (lower.endsWith('.xls') || lower.endsWith('.xlsx') || lower.endsWith('.ods') || lower.endsWith('.csv')) return 'XLS'
  if (lower.endsWith('.ppt') || lower.endsWith('.pptx') || lower.endsWith('.odp')) return 'PPT'
  if (lower.endsWith('.zip') || lower.endsWith('.rar') || lower.endsWith('.7z') || lower.endsWith('.tar')) return 'ZIP'
  if (
    lower.endsWith('.txt') || lower.endsWith('.md') || lower.endsWith('.json') || lower.endsWith('.yaml') || lower.endsWith('.yml') ||
    lower.endsWith('.py') || lower.endsWith('.ts') || lower.endsWith('.tsx') || lower.endsWith('.js') || lower.endsWith('.jsx') ||
    lower.endsWith('.java') || lower.endsWith('.go') || lower.endsWith('.rs') || lower.endsWith('.c') || lower.endsWith('.cpp')
  ) return 'TXT'
  return 'FILE'
}

export function isImageGenerationPrompt(prompt: string): boolean {
  const lower = prompt.toLowerCase().trim()

  // Explicit commands always trigger image generation
  if (lower.startsWith('/image') || lower.startsWith('/img')) {
    return true
  }

  // Keywords that indicate image generation intent
  const imageKeywords = [
    'draw',
    'illustration',
    'picture of',
    'image of',
    'provide image',
    'give image',
    'show image',
    'photo of',
    'painting of',
    'artwork',
    'design',
    'wallpaper',
    'logo',
    'poster',
    'visualize',
    'imagine',
    'sketch',
    'paint',
    'digital art',
    'show me an image',
    // Phrase-level triggers: catches "an image of/a/showing..." regardless of leading verb
    'an image',
    'a picture',
    'a photo',
    'an illustration',
    'a painting',
    'a drawing',
    'a sketch',
    'a portrait',
    'a wallpaper',
  ]

  // Check if prompt contains both an action verb and an image noun
  // Handles natural asks like: "provide an Amazon forest image as per set rules"
  const actionVerbs = ['generate', 'create', 'make', 'draw', 'render', 'provide', 'give', 'show', 'produce']
  const imageNouns = ['image', 'picture', 'photo', 'illustration', 'artwork', 'poster', 'logo', 'wallpaper']
  // Also match common misspellings / partial stems (generat*, creat*)
  const actionVerbStems = ['generat', 'creat', 'produc', 'renderd']
  const hasActionVerb = actionVerbs.some((verb) => lower.includes(verb))
    || actionVerbStems.some((stem) => lower.includes(stem))
  const hasImageNoun = imageNouns.some((noun) => lower.includes(noun))

  if (hasActionVerb && hasImageNoun) {
    return true
  }

  // Check if any keyword matches
  if (imageKeywords.some((keyword) => lower.includes(keyword))) {
    return true
  }

  return false
}

export function isImageValidationPrompt(prompt: string): boolean {
  const normalized = prompt.toLowerCase().trim()
  if (!normalized) return false

  if (normalized === 'validate' || normalized === 'validation') {
    return true
  }

  if (normalized.startsWith('validate ') || normalized.startsWith('validation ')) {
    return true
  }

  if (normalized.startsWith('/validate-image') || normalized.startsWith('/validate')) {
    return true
  }

  if (normalized.includes('validate') && normalized.includes('image')) {
    return true
  }

  if (normalized.includes('check') && normalized.includes('image')) {
    return true
  }

  return false
}

export function deriveImageGenerationOptions(prompt: string): {
  prompt: string
  size: '1024x1024' | '1024x1536' | '1536x1024'
  style?: 'vivid' | 'natural'
} {
  const normalized = prompt.toLowerCase()

  let size: '1024x1024' | '1024x1536' | '1536x1024' = '1024x1024'

  if (/\b(1\s*[:x/]\s*1|square)\b/.test(normalized)) {
    size = '1024x1024'
  } else if (/\b(9\s*[:x/]\s*16|portrait|vertical|tall)\b/.test(normalized)) {
    size = '1024x1536'
  } else if (/\b(16\s*[:x/]\s*9|landscape|widescreen|wide|horizontal)\b/.test(normalized)) {
    size = '1536x1024'
  }

  let style: 'vivid' | 'natural' | undefined
  if (/\b(photo|photoreal|realistic|natural)\b/.test(normalized)) {
    style = 'natural'
  } else if (/\b(illustration|digital art|anime|cartoon|painting|vivid)\b/.test(normalized)) {
    style = 'vivid'
  }

  return {
    prompt,
    size,
    style,
  }
}
