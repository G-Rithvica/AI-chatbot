import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../lib/api'
import type {
  DatabaseConnectionInput,
  DatabaseConnectResponse,
  DatabaseQueryResponse,
  SupportedDatabaseType,
} from '../types'

type ConnectionFormState = {
  db_type: SupportedDatabaseType
  host: string
  port: string
  database: string
  username: string
  password: string
  schema: string
  sqlite_path: string
  url: string
  ssl_required: boolean
}

const INITIAL_CONNECTION: ConnectionFormState = {
  db_type: 'postgresql',
  host: '',
  port: '',
  database: '',
  username: '',
  password: '',
  schema: 'public',
  sqlite_path: '',
  url: '',
  ssl_required: false,
}

function normalizeConnection(state: ConnectionFormState): DatabaseConnectionInput {
  const trimmed = {
    db_type: state.db_type,
    host: state.host.trim() || undefined,
    port: state.port.trim() ? Number(state.port.trim()) : undefined,
    database: state.database.trim() || undefined,
    username: state.username.trim() || undefined,
    password: state.password || undefined,
    schema: state.schema.trim() || undefined,
    sqlite_path: state.sqlite_path.trim() || undefined,
    url: state.url.trim() || undefined,
    ssl_required: state.ssl_required,
  }

  if (state.db_type === 'sqlite') {
    return {
      db_type: trimmed.db_type,
      sqlite_path: trimmed.sqlite_path,
      database: trimmed.database,
      url: trimmed.url,
    }
  }

  return trimmed
}

function resultTable(result: DatabaseQueryResponse | null) {
  if (!result || !result.columns.length || !result.rows.length) {
    return null
  }

  return (
    <div className="ui-chat-table-wrap rounded-xl border border-slate-800/70">
      <table className="ui-chat-table text-sm">
        <thead>
          <tr>
            {result.columns.map((column) => (
              <th key={column} className="ui-chat-table-th text-left">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, index) => (
            <tr key={index} className="ui-chat-table-row">
              {result.columns.map((column) => (
                <td key={`${index}-${column}`} className="ui-chat-table-td align-top">
                  {String(row[column] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DatabasePage() {
  const [connection, setConnection] = useState<ConnectionFormState>(INITIAL_CONNECTION)
  const [question, setQuestion] = useState('Show all customers from Hyderabad')
  const [maxRows, setMaxRows] = useState('50')
  const [connectResult, setConnectResult] = useState<DatabaseConnectResponse | null>(null)
  const [queryResult, setQueryResult] = useState<DatabaseQueryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const normalizedConnection = useMemo(() => normalizeConnection(connection), [connection])

  const connectMutation = useMutation({
    mutationFn: () => api.databaseConnect({ connection: normalizedConnection }),
    onSuccess: (data) => {
      setConnectResult(data)
      setError(null)
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const queryMutation = useMutation({
    mutationFn: () => api.databaseQuery({
      question,
      max_rows: Number(maxRows) || 50,
      connection: normalizedConnection,
    }),
    onSuccess: (data) => {
      setQueryResult(data)
      setError(null)
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const isSqlite = connection.db_type === 'sqlite'
  const isUrlDriven = connection.db_type === 'supabase'

  return (
    <main className="app-shell min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-emerald-200/70">Project 8</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-50">Natural Language Database QA</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-300">
              Connect to MySQL, PostgreSQL, SQLite, or Supabase, generate a safe read-only SQL query,
              and inspect the results without changing existing chat behavior. You can also paste a public CSV
              or Google Sheets URL into the connection URL field and query it as a temporary SQLite source.
            </p>
          </div>
          <Link
            to="/chat"
            className="ui-btn-secondary inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium"
          >
            Back to Chat
          </Link>
        </div>

        <section className="grid gap-6 lg:grid-cols-[minmax(340px,420px)_1fr]">
          <div className="ui-surface-accent p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-100">Database Connection</h2>
              <span className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-100">
                Isolated module
              </span>
            </div>

            <div className="space-y-4">
              <label className="block">
                <span className="mb-1 block text-sm text-slate-300">Database Type</span>
                <select
                  value={connection.db_type}
                  onChange={(event) => setConnection((current) => ({ ...current, db_type: event.target.value as SupportedDatabaseType }))}
                  className="ui-input"
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                  <option value="sqlite">SQLite</option>
                  <option value="supabase">Supabase</option>
                </select>
              </label>

              <label className="block">
                <span className="mb-1 block text-sm text-slate-300">Connection URL</span>
                <input
                  value={connection.url}
                  onChange={(event) => setConnection((current) => ({ ...current, url: event.target.value }))}
                  className="ui-input"
                  placeholder={isSqlite ? 'sqlite:///relative/or/absolute/path.db or public CSV/Google Sheet URL' : 'Optional SQLAlchemy URL or public CSV/Google Sheet URL'}
                />
              </label>

              {isSqlite ? (
                <label className="block">
                  <span className="mb-1 block text-sm text-slate-300">SQLite File Path</span>
                  <input
                    value={connection.sqlite_path}
                    onChange={(event) => setConnection((current) => ({ ...current, sqlite_path: event.target.value }))}
                    className="ui-input"
                    placeholder="data/app.sqlite"
                  />
                </label>
              ) : (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block text-sm text-slate-300">Host</span>
                      <input
                        value={connection.host}
                        onChange={(event) => setConnection((current) => ({ ...current, host: event.target.value }))}
                        className="ui-input"
                        placeholder={isUrlDriven ? 'db.xxx.supabase.co' : 'localhost'}
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-sm text-slate-300">Port</span>
                      <input
                        value={connection.port}
                        onChange={(event) => setConnection((current) => ({ ...current, port: event.target.value }))}
                        className="ui-input"
                        placeholder={connection.db_type === 'mysql' ? '3306' : '5432'}
                      />
                    </label>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block text-sm text-slate-300">Database Name</span>
                      <input
                        value={connection.database}
                        onChange={(event) => setConnection((current) => ({ ...current, database: event.target.value }))}
                        className="ui-input"
                        placeholder="postgres"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-sm text-slate-300">Schema</span>
                      <input
                        value={connection.schema}
                        onChange={(event) => setConnection((current) => ({ ...current, schema: event.target.value }))}
                        className="ui-input"
                        placeholder="public"
                      />
                    </label>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block text-sm text-slate-300">Username</span>
                      <input
                        value={connection.username}
                        onChange={(event) => setConnection((current) => ({ ...current, username: event.target.value }))}
                        className="ui-input"
                        placeholder="postgres"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-sm text-slate-300">Password</span>
                      <input
                        type="password"
                        value={connection.password}
                        onChange={(event) => setConnection((current) => ({ ...current, password: event.target.value }))}
                        className="ui-input"
                        placeholder="••••••••"
                      />
                    </label>
                  </div>

                  <label className="flex items-center gap-3 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={connection.ssl_required}
                      onChange={(event) => setConnection((current) => ({ ...current, ssl_required: event.target.checked }))}
                    />
                    Require SSL
                  </label>
                </>
              )}

              <button
                onClick={() => connectMutation.mutate()}
                disabled={connectMutation.isPending}
                className="ui-btn-primary w-full rounded-xl px-4 py-3 text-sm font-semibold disabled:opacity-50"
              >
                {connectMutation.isPending ? 'Connecting…' : 'Connect Database'}
              </button>

              {connectResult && (
                <div className="rounded-xl border border-emerald-400/25 bg-emerald-500/10 p-4 text-sm text-emerald-50">
                  <p className="font-medium">{connectResult.message}</p>
                  <p className="mt-1 text-emerald-100/80">
                    Type: {connectResult.db_type || 'unknown'} · Database: {connectResult.database || 'n/a'}
                  </p>
                  <p className="mt-2 text-xs text-emerald-100/75">
                    Tables discovered: {connectResult.tables.length}
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-6">
            <section className="ui-surface p-5">
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-100">Ask in Natural Language</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    The backend detects database intent, generates read-only SQL, validates it, executes it securely,
                    and returns friendly results.
                  </p>
                </div>
              </div>

              <div className="grid gap-4">
                <label className="block">
                  <span className="mb-1 block text-sm text-slate-300">Question</span>
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    rows={4}
                    className="ui-input min-h-30"
                    placeholder="What is the total revenue this month?"
                  />
                </label>

                <div className="grid gap-4 sm:grid-cols-[160px_1fr] sm:items-end">
                  <label className="block">
                    <span className="mb-1 block text-sm text-slate-300">Max Rows</span>
                    <input
                      value={maxRows}
                      onChange={(event) => setMaxRows(event.target.value)}
                      className="ui-input"
                      placeholder="50"
                    />
                  </label>
                  <button
                    onClick={() => queryMutation.mutate()}
                    disabled={queryMutation.isPending || !question.trim()}
                    className="ui-btn-primary rounded-xl px-4 py-3 text-sm font-semibold disabled:opacity-50"
                  >
                    {queryMutation.isPending ? 'Running Query…' : 'Generate and Execute'}
                  </button>
                </div>

                {error && <div className="ui-error-banner px-4 py-3 text-sm">{error}</div>}
              </div>
            </section>

            <section className="ui-surface p-5">
              <h2 className="text-lg font-semibold text-slate-100">Response</h2>
              {!queryResult ? (
                <p className="mt-3 text-sm text-slate-400">Run a query to see the generated SQL, friendly explanation, and results.</p>
              ) : (
                <div className="mt-4 space-y-5">
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Intent</p>
                      <p className="mt-2 text-sm font-medium text-slate-100">{queryResult.detected_intent}</p>
                    </div>
                    <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Status</p>
                      <p className="mt-2 text-sm font-medium text-slate-100">{queryResult.allowed ? 'Allowed' : 'Blocked'}</p>
                    </div>
                    <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rows</p>
                      <p className="mt-2 text-sm font-medium text-slate-100">{queryResult.row_count}</p>
                    </div>
                    <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Message</p>
                      <p className="mt-2 text-sm font-medium text-slate-100">{queryResult.message}</p>
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium text-slate-200">Generated SQL</p>
                    <pre className="overflow-x-auto rounded-xl border border-slate-800/70 bg-slate-950/60 p-4 text-xs text-emerald-100">
                      {queryResult.sql || 'No SQL generated.'}
                    </pre>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium text-slate-200">Friendly Explanation</p>
                    <div className="rounded-xl border border-slate-800/70 bg-slate-950/35 p-4 text-sm text-slate-200">
                      {queryResult.explanation || 'No explanation available.'}
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium text-slate-200">Query Result</p>
                    {resultTable(queryResult) || (
                      <div className="rounded-xl border border-slate-800/70 bg-slate-950/35 p-4 text-sm text-slate-400">
                        No rows returned.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </section>

            <section className="ui-surface p-5">
              <h2 className="text-lg font-semibold text-slate-100">Schema Preview</h2>
              {!connectResult ? (
                <p className="mt-3 text-sm text-slate-400">Connect to a database to inspect tables and columns.</p>
              ) : connectResult.tables.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">No tables were discovered for this connection.</p>
              ) : (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  {connectResult.tables.slice(0, 12).map((table) => (
                    <div key={table.name} className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4">
                      <p className="text-sm font-semibold text-slate-100">{table.name}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {table.columns.slice(0, 8).map((column) => (
                          <span
                            key={`${table.name}-${column.name}`}
                            className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-100"
                          >
                            {column.name} · {column.data_type}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </section>
      </div>
    </main>
  )
}