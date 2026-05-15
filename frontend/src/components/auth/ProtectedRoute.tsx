import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../../hooks/useAuth'

type ProtectedRouteProps = {
  children: ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { data, isLoading, isError } = useAuth()

  if (isLoading) {
    return (
      <main className="app-shell grid min-h-screen place-items-center px-4">
        <div className="ui-surface-accent px-6 py-4 text-sm text-slate-200">Checking session...</div>
      </main>
    )
  }

  if (isError || !data?.authenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
