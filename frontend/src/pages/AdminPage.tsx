import { Link } from 'react-router-dom'

import { TopWorkspaceBar } from '../components/layout/TopWorkspaceBar'
import { DataGrid } from '../components/ui/DataGrid'

export default function AdminPage() {
  return (
    <main className="app-shell min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <TopWorkspaceBar
          title="Admin Panel"
          subtitle="Users, permissions, and governance"
          rightActions={(
            <Link to="/chat" className="ui-btn-secondary inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium whitespace-nowrap">
              ← Back to Chat
            </Link>
          )}
        />

        <section className="ui-surface p-5">
          <h2 className="mb-4 text-lg font-semibold text-slate-100">Workspace Users</h2>
          <DataGrid
            columns={['Name', 'Email', 'Role', 'Status']}
            rows={[
              ['Workspace Admin', 'admin@amzur.com', 'Admin', 'Active'],
              ['Research Lead', 'research@amzur.com', 'Editor', 'Active'],
              ['Analyst', 'analyst@amzur.com', 'Viewer', 'Pending'],
            ]}
          />
        </section>
      </div>
    </main>
  )
}
