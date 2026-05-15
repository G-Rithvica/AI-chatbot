import { useState } from 'react'
import { Link } from 'react-router-dom'

import { TopWorkspaceBar } from '../components/layout/TopWorkspaceBar'
import { useTheme } from '../hooks/useTheme'

export default function SettingsPage() {
  const { theme, toggleTheme } = useTheme()
  const [companyName, setCompanyName] = useState('Amzur AI Workspace')
  const [timezone, setTimezone] = useState('UTC')

  return (
    <main className="app-shell min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <TopWorkspaceBar
          title="Settings"
          subtitle="Workspace preferences and defaults"
          rightActions={(
            <>
              <button type="button" className="ui-btn-secondary px-3 py-1.5 text-xs" onClick={toggleTheme}>
                {theme === 'dark' ? 'Light' : 'Dark'}
              </button>
              <Link to="/chat" className="ui-btn-secondary inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium whitespace-nowrap">
                ← Back to Chat
              </Link>
            </>
          )}
        />

        <section className="ui-surface p-5">
          <h2 className="mb-4 text-lg font-semibold text-slate-100">General</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs text-slate-400">Workspace Name</span>
              <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="ui-input" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-slate-400">Timezone</span>
              <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className="ui-input">
                <option value="UTC">UTC</option>
                <option value="America/New_York">America/New_York</option>
                <option value="Europe/London">Europe/London</option>
                <option value="Asia/Kolkata">Asia/Kolkata</option>
              </select>
            </label>
          </div>
          <div className="mt-4 flex justify-end">
            <button type="button" className="ui-btn-primary rounded-xl px-4 py-2 text-sm font-semibold">Save Changes</button>
          </div>
        </section>
      </div>
    </main>
  )
}
