import { Link } from 'react-router-dom'

import { TopWorkspaceBar } from '../components/layout/TopWorkspaceBar'

function StatCard({ label, value, trend }: { label: string; value: string; trend: string }) {
  return (
    <div className="ui-surface p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-100">{value}</p>
      <p className="mt-1 text-xs text-emerald-300">{trend}</p>
    </div>
  )
}

export default function AnalyticsPage() {
  return (
    <main className="app-shell min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <TopWorkspaceBar
          title="Analytics"
          subtitle="Usage, throughput, and quality metrics"
          rightActions={(
            <Link to="/chat" className="ui-btn-secondary inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium whitespace-nowrap">
              ← Back to Chat
            </Link>
          )}
        />

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Active Threads" value="128" trend="+12% vs last week" />
          <StatCard label="Avg. Response Time" value="1.6s" trend="-8% improved" />
          <StatCard label="Model Calls" value="9,842" trend="+4%" />
          <StatCard label="Validation Pass Rate" value="93%" trend="+2%" />
        </section>

        <section className="ui-surface p-5">
          <h2 className="mb-2 text-lg font-semibold text-slate-100">Report Snapshot</h2>
          <p className="text-sm text-slate-300">Interactive charts can be connected here to your telemetry backend.</p>
          <div className="mt-4 h-56 rounded-xl border border-slate-700/50 bg-slate-900/35 p-4">
            <div className="ui-skeleton h-full rounded-lg" />
          </div>
        </section>
      </div>
    </main>
  )
}
