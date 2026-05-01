import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, apiClient } from '../lib/api'

export default function LoginPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  // Single mutation: tries login first; if no password set yet, registers (sets password) then signs in
  const signInMutation = useMutation({
    mutationFn: async ({ email, password }: { email: string; password: string }) => {
      try {
        return await api.emailLogin({ email, password })
      } catch (loginErr) {
        const msg = loginErr instanceof Error ? loginErr.message : ''
        // If credentials failed because no password exists yet, set it and log in
        if (msg.includes('Invalid email or password')) {
          return await api.emailRegister({ email, password })
        }
        throw loginErr
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      navigate('/chat')
    },
    onError: (err: Error) => {
      setFormError(err.message)
    },
  })

  const signUpMutation = useMutation({
    mutationFn: ({ email, password, name }: { email: string; password: string; name: string }) =>
      api.emailRegister({ email, password, name: name.trim() || undefined }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      navigate('/chat')
    },
    onError: (err: Error) => {
      setFormError(err.message)
    },
  })

  const busy = signInMutation.isPending || signUpMutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (mode === 'signup') {
      signUpMutation.mutate({ email, password, name })
      return
    }
    signInMutation.mutate({ email, password })
  }

  return (
    <main className="min-h-screen bg-stone-950 text-stone-100">
      <section className="mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center gap-8 px-6 py-16">
        {/* Header */}
        <div className="text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-amber-300">Amzur AI Chat</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            {mode === 'signup' ? 'Create your account.' : 'Sign in to continue.'}
          </h1>
        </div>

        {/* Card */}
        <div className="w-full rounded-2xl border border-stone-800 bg-stone-900/70 p-6">
          <div className="mb-5 grid grid-cols-2 rounded-xl bg-stone-950 p-1">
            <button
              type="button"
              onClick={() => {
                setMode('signin')
                setFormError(null)
              }}
              className={`rounded-lg px-3 py-2 text-sm transition ${
                mode === 'signin' ? 'bg-amber-300 font-medium text-stone-950' : 'text-stone-400 hover:text-stone-100'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('signup')
                setFormError(null)
              }}
              className={`rounded-lg px-3 py-2 text-sm transition ${
                mode === 'signup' ? 'bg-amber-300 font-medium text-stone-950' : 'text-stone-400 hover:text-stone-100'
              }`}
            >
              Sign Up
            </button>
          </div>

          {/* Email + Password form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {mode === 'signup' && (
              <div className="flex flex-col gap-1">
                <label htmlFor="name" className="text-xs text-stone-400">Name</label>
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => { setName(e.target.value); setFormError(null) }}
                  placeholder="Your name"
                  className="rounded-xl border border-stone-700 bg-stone-950 px-3 py-2 text-sm outline-none placeholder:text-stone-500 focus:border-amber-300"
                />
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label htmlFor="email" className="text-xs text-stone-400">Email</label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => { setEmail(e.target.value); setFormError(null) }}
                placeholder="you@amzur.com"
                className="rounded-xl border border-stone-700 bg-stone-950 px-3 py-2 text-sm outline-none placeholder:text-stone-500 focus:border-amber-300"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="password" className="text-xs text-stone-400">Password</label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => { setPassword(e.target.value); setFormError(null) }}
                placeholder="••••••••"
                className="rounded-xl border border-stone-700 bg-stone-950 px-3 py-2 text-sm outline-none placeholder:text-stone-500 focus:border-amber-300"
              />
            </div>

            {formError && (
              <p className="rounded-lg border border-rose-800 bg-rose-950/50 px-3 py-2 text-sm text-rose-300">
                {formError}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="rounded-xl bg-amber-300 py-2.5 text-sm font-medium text-stone-950 transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? (mode === 'signup' ? 'Creating account…' : 'Signing in…') : (mode === 'signup' ? 'Sign Up' : 'Sign In')}
            </button>
          </form>

          {/* Divider */}
          <div className="my-5 flex items-center gap-3">
            <hr className="flex-1 border-stone-700" />
            <span className="text-xs text-stone-500">or</span>
            <hr className="flex-1 border-stone-700" />
          </div>

          {/* Google */}
          <a
            href={`${apiClient.baseUrl}/api/auth/google/login`}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-stone-700 py-2.5 text-sm font-medium text-stone-100 transition hover:bg-stone-800"
          >
            Continue with Google
          </a>
        </div>
      </section>
    </main>
  )
}
