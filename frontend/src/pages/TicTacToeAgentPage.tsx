import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { TopWorkspaceBar } from '../components/layout/TopWorkspaceBar'
import { StateBlock } from '../components/ui/StateBlock'
import { api } from '../lib/api'
import type { TicTacToeMoveResponse } from '../types'

const EMPTY_BOARD = Array.from({ length: 9 }, () => '')

function statusLabel(status: string): string {
  if (status === 'user_won') return 'You won this round.'
  if (status === 'agent_won') return 'Agent won this round.'
  if (status === 'draw') return 'Round ended in a draw.'
  return 'Your turn. Pick a neon tile.'
}

export default function TicTacToeAgentPage() {
  const navigate = useNavigate()
  const authQuery = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: api.getCurrentUser,
  })

  const userDisplayName = useMemo(() => {
    const name = authQuery.data?.user?.name?.trim()
    if (name) return name

    const email = authQuery.data?.user?.email ?? ''
    if (email.includes('@')) {
      return email.split('@')[0]
    }
    return 'Logged-in User'
  }, [authQuery.data])

  const [board, setBoard] = useState<string[]>(EMPTY_BOARD)
  const [status, setStatus] = useState<string>('in_progress')
  const [winner, setWinner] = useState<string | null>(null)
  const [agentReason, setAgentReason] = useState<string>('Agent is ready to play.')
  const [agentSource, setAgentSource] = useState<string>('none')
  const [error, setError] = useState<string | null>(null)

  const ended = useMemo(() => status === 'user_won' || status === 'agent_won' || status === 'draw', [status])
  const winnerName = useMemo(() => {
    if (winner === 'X') return userDisplayName
    if (winner === 'O') return 'Agent'
    return null
  }, [userDisplayName, winner])

  const moveMutation = useMutation({
    mutationFn: ({ userMove, boardBefore }: { userMove: number; boardBefore: string[] }) => api.ticTacToeAgentMove({
      board: boardBefore,
      user_move: userMove,
      user_mark: 'X',
      agent_mark: 'O',
    }),
    onSuccess: (result: TicTacToeMoveResponse) => {
      setBoard(result.board)
      setStatus(result.status)
      setWinner(result.winner ?? null)
      setAgentReason(result.agent_reason)
      setAgentSource(result.agent_source)
      setError(null)
    },
    onError: (moveError: Error, variables) => {
      setBoard(variables.boardBefore)
      setError(moveError.message)
    },
  })

  const handleCellClick = async (index: number) => {
    if (moveMutation.isPending || ended) return
    if (board[index]) return

    const boardBefore = [...board]
    const optimisticBoard = [...boardBefore]
    optimisticBoard[index] = 'X'
    setBoard(optimisticBoard)
    setError(null)

    moveMutation.mutate({ userMove: index, boardBefore })
  }

  const handleReset = () => {
    setBoard(EMPTY_BOARD)
    setStatus('in_progress')
    setWinner(null)
    setAgentReason('Agent is ready to play.')
    setAgentSource('none')
    setError(null)
  }

  return (
    <div className="app-shell min-h-screen">
      <TopWorkspaceBar
        title="Project 11 - Tic Tac Toe Agent"
        subtitle="LLM-powered opponent with validated legal play"
        leftActions={(
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className="ui-btn-secondary px-3 py-1.5 text-xs"
          >
            ← Back to Chat
          </button>
        )}
        rightActions={(
          <button
            type="button"
            onClick={handleReset}
            className="ui-btn-secondary px-3 py-1.5 text-xs"
          >
            New Round
          </button>
        )}
      />

      <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
        <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
          <section className="ui-surface-accent relative isolate p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-cyan-200/75">Neon Arena</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-100">Human vs AI Agent</h2>
            <p className="mt-2 text-sm text-slate-300">You play as X. The agent plays as O using LLM decisioning with safe fallback intelligence.</p>
            {ended && winnerName && (
              <div className="ttt-ribbon-backdrop" aria-hidden>
                <span className="ttt-ribbon ttt-ribbon-1" />
                <span className="ttt-ribbon ttt-ribbon-2" />
                <span className="ttt-ribbon ttt-ribbon-3" />
                <span className="ttt-ribbon ttt-ribbon-4" />
              </div>
            )}

            <div className="mt-5 grid grid-cols-3 gap-2.5 sm:gap-3">
              {board.map((cell, index) => {
                const occupied = cell !== ''
                return (
                  <button
                    key={index}
                    type="button"
                    disabled={moveMutation.isPending || ended || occupied}
                    onClick={() => handleCellClick(index)}
                    className={`ttt-cell ${cell === 'X' ? 'ttt-cell-x' : ''} ${cell === 'O' ? 'ttt-cell-o' : ''}`}
                  >
                    {cell || <span className="text-slate-600">{index + 1}</span>}
                  </button>
                )
              })}
            </div>
          </section>

          <section className="ui-surface p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-cyan-200/75">Game Telemetry</p>
            <h3 className="mt-1 text-lg font-semibold text-slate-100">Round Status</h3>

            <div className="mt-4 space-y-3 text-sm text-slate-300">
              <div className="rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-2">
                {statusLabel(status)}
              </div>

              <div className="rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2">
                <p className="text-xs text-slate-400">Winner</p>
                <p className="font-semibold text-cyan-100">{winnerName ?? 'None yet'}</p>
              </div>

              {ended && winnerName && (
                <div className="rounded-lg border border-cyan-300/45 bg-cyan-500/14 px-3 py-2">
                  <p className="text-xs text-cyan-100/80">Round Winner</p>
                  <p className="text-base font-bold text-cyan-100">{winnerName}</p>
                </div>
              )}

              <div className="rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2">
                <p className="text-xs text-slate-400">Decision Source</p>
                <p className="font-medium text-slate-100">{agentSource}</p>
              </div>

              <div className="rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2">
                <p className="text-xs text-slate-400">Agent Reasoning</p>
                <p className="text-sm text-slate-200">{agentReason}</p>
              </div>

              {moveMutation.isPending && (
                <StateBlock tone="neutral" title="Agent is thinking" message="Evaluating board and selecting optimal legal move..." />
              )}

              {error && <StateBlock tone="error" title="Move failed" message={error} />}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
