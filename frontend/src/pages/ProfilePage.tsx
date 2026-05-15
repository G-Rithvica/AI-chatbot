import { Link } from 'react-router-dom'

import { TopWorkspaceBar } from '../components/layout/TopWorkspaceBar'
import { useAuth } from '../hooks/useAuth'

export default function ProfilePage() {
  const auth = useAuth()
  const user = auth.data?.user

  return (
    <main className="app-shell min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <TopWorkspaceBar
          title="Profile"
          subtitle="Account details and identity"
          rightActions={(
            <Link to="/chat" className="ui-btn-secondary inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium whitespace-nowrap">
              ← Back to Chat
            </Link>
          )}
        />

        <section className="ui-surface p-5">
          <h2 className="mb-4 text-lg font-semibold text-slate-100">User Information</h2>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-slate-400">Name</dt>
              <dd className="mt-1 text-sm text-slate-100">{user?.name ?? 'Not set'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400">Email</dt>
              <dd className="mt-1 text-sm text-slate-100">{user?.email ?? 'Unknown'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400">Status</dt>
              <dd className="mt-1 text-sm text-emerald-300">Active</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400">Role</dt>
              <dd className="mt-1 text-sm text-slate-100">Workspace User</dd>
            </div>
          </dl>
        </section>
      </div>
    </main>
  )
}
