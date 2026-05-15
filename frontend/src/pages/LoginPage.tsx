import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../hooks/useAuth'
import { api, apiClient } from '../lib/api'

type FieldKey = 'name' | 'email' | 'password' | 'confirmPassword'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MIN_PASSWORD_LENGTH = 8

export default function LoginPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const authQuery = useAuth()

  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [touched, setTouched] = useState<Record<FieldKey, boolean>>({
    name: false,
    email: false,
    password: false,
    confirmPassword: false,
  })
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [invalidCredentialsError, setInvalidCredentialsError] = useState<string | null>(null)

  useEffect(() => {
    if (authQuery.data?.authenticated) {
      navigate('/chat', { replace: true })
    }
  }, [authQuery.data?.authenticated, navigate])

  const signInMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) => api.emailLogin({ email, password }),
    onSuccess: async () => {
      setInvalidCredentialsError(null)
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      navigate('/chat')
    },
    onError: (err: Error) => {
      if (err.message.toLowerCase().includes('invalid email or password')) {
        setInvalidCredentialsError('Invalid email or password.')
        setFormError(null)
        return
      }
      setInvalidCredentialsError(null)
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

  const fieldErrors: Partial<Record<FieldKey, string>> = {}

  if (mode === 'signup' && !name.trim()) {
    fieldErrors.name = 'Name is required.'
  }

  if (!email.trim()) {
    fieldErrors.email = 'Email is required.'
  } else if (!EMAIL_REGEX.test(email.trim())) {
    fieldErrors.email = 'Enter a valid email address.'
  }

  if (!password) {
    fieldErrors.password = 'Password is required.'
  } else if (mode === 'signup' && password.length < MIN_PASSWORD_LENGTH) {
    fieldErrors.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`
  }

  if (mode === 'signup' && !confirmPassword) {
    fieldErrors.confirmPassword = 'Confirm password is required.'
  } else if (mode === 'signup' && confirmPassword && password !== confirmPassword) {
    fieldErrors.confirmPassword = 'Passwords do not match.'
  }

  const shouldShowFieldError = (field: FieldKey) => submitAttempted || touched[field]
  const hasValidationErrors = Object.keys(fieldErrors).length > 0

  const inputClass = (field: FieldKey) => `ui-input ${shouldShowFieldError(field) && fieldErrors[field] ? 'ui-input-error' : ''}`

  const markTouched = (field: FieldKey) => {
    setTouched((prev) => ({ ...prev, [field]: true }))
  }

  const resetErrorsOnInput = (field: FieldKey) => {
    setFormError(null)
    if (field === 'password') {
      setInvalidCredentialsError(null)
    }
    if (!touched[field] && !submitAttempted) return
    setTouched((prev) => ({ ...prev, [field]: true }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitAttempted(true)
    setTouched({
      name: true,
      email: true,
      password: true,
      confirmPassword: true,
    })

    if (hasValidationErrors) {
      return
    }

    setFormError(null)
    setInvalidCredentialsError(null)
    if (mode === 'signup') {
      signUpMutation.mutate({ email, password, name })
      return
    }
    signInMutation.mutate({ email, password })
  }

  return (
    <main className="app-shell">
      <section className="mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center gap-7 px-5 py-12 sm:px-6">
        {/* Header */}
        <div className="text-center">
          <p className="text-xs uppercase tracking-[0.3em] text-emerald-200">Amzur AI Chat</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">
            {mode === 'signup' ? 'Create your account.' : 'Sign in to continue.'}
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            {mode === 'signup' ? 'Join the workspace with your company credentials.' : 'Welcome back. Continue to your assistant workspace.'}
          </p>
        </div>

        {/* Card */}
        <div className="ui-surface w-full p-6 shadow-[0_18px_48px_rgba(0,0,0,0.35)]">
          <div className="mb-5 grid grid-cols-2 rounded-xl bg-slate-950/60 p-1">
            <button
              type="button"
              onClick={() => {
                setMode('signin')
                setFormError(null)
                setInvalidCredentialsError(null)
                setSubmitAttempted(false)
                setTouched({ name: false, email: false, password: false, confirmPassword: false })
              }}
              className={`rounded-lg px-3 py-2 text-sm transition ${
                mode === 'signin' ? 'ui-tab-active' : 'text-slate-400 hover:text-slate-100'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('signup')
                setFormError(null)
                setInvalidCredentialsError(null)
                setSubmitAttempted(false)
                setTouched({ name: false, email: false, password: false, confirmPassword: false })
              }}
              className={`rounded-lg px-3 py-2 text-sm transition ${
                mode === 'signup' ? 'ui-tab-active' : 'text-slate-400 hover:text-slate-100'
              }`}
            >
              Sign Up
            </button>
          </div>

          {/* Email + Password form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {mode === 'signup' && (
              <div className="flex flex-col gap-1">
                <label htmlFor="name" className="text-xs text-slate-400">Name</label>
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => { setName(e.target.value); resetErrorsOnInput('name') }}
                  onBlur={() => markTouched('name')}
                  placeholder="Your name"
                  className={inputClass('name')}
                />
                <p className="ui-error-text">{shouldShowFieldError('name') ? fieldErrors.name : ''}</p>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label htmlFor="email" className="text-xs text-slate-400">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); resetErrorsOnInput('email') }}
                onBlur={() => markTouched('email')}
                placeholder="you@amzur.com"
                className={inputClass('email')}
              />
              <p className="ui-error-text">{shouldShowFieldError('email') ? fieldErrors.email : ''}</p>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="password" className="text-xs text-slate-400">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); resetErrorsOnInput('password') }}
                onBlur={() => markTouched('password')}
                placeholder="••••••••"
                className={inputClass('password')}
              />
              <p className="ui-error-text">{shouldShowFieldError('password') ? fieldErrors.password : ''}</p>
              {mode === 'signin' && invalidCredentialsError && (
                <p className="ui-error-text">{invalidCredentialsError}</p>
              )}
            </div>

            {mode === 'signup' && (
              <div className="flex flex-col gap-1">
                <label htmlFor="confirmPassword" className="text-xs text-slate-400">Confirm Password</label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => { setConfirmPassword(e.target.value); resetErrorsOnInput('confirmPassword') }}
                  onBlur={() => markTouched('confirmPassword')}
                  placeholder="••••••••"
                  className={inputClass('confirmPassword')}
                />
                <p className="ui-error-text">{shouldShowFieldError('confirmPassword') ? fieldErrors.confirmPassword : ''}</p>
              </div>
            )}

            {formError && (
              <p className="ui-error-banner px-3 py-2 text-sm">
                {formError}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || hasValidationErrors}
              className="ui-btn-primary py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? (mode === 'signup' ? 'Creating account…' : 'Signing in…') : (mode === 'signup' ? 'Sign Up' : 'Sign In')}
            </button>
          </form>

          {/* Divider */}
          <div className="my-5 flex items-center gap-3">
            <hr className="flex-1 border-slate-700" />
            <span className="text-xs text-slate-500">or</span>
            <hr className="flex-1 border-slate-700" />
          </div>

          {/* Google */}
          <a
            href={`${apiClient.baseUrl}/api/auth/google/login`}
            className="ui-btn-secondary flex w-full items-center justify-center gap-2 py-2.5 text-sm font-medium"
          >
            Continue with Google
          </a>
        </div>
      </section>
    </main>
  )
}
