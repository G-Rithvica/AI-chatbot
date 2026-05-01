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
      <main className="grid min-h-screen place-items-center bg-stone-950 text-stone-200">
        <p>Checking session...</p>
      </main>
    )
  }

  if (isError || !data?.authenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
