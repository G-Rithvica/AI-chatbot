import { useEffect, useState } from 'react'

export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'ui:theme'

function resolveInitialTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'dark'
  const persisted = window.localStorage.getItem(STORAGE_KEY)
  if (persisted === 'light' || persisted === 'dark') return persisted
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>(() => resolveInitialTheme())

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggleTheme = () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))

  return { theme, setTheme, toggleTheme }
}
