import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchStats, type StatsResponse } from './api'
import { useI18n } from './i18n'

// Persistent career leaderboard (multiplayer games only, bots excluded —
// aggregated server-side from SQLite). Opened from the landing page.
export default function Leaderboard({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { t } = useI18n()
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    fetchStats()
      .then(setStats)
      .finally(() => setLoading(false))
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open) return null

  const rows = stats?.leaderboard ?? []
  const games = stats?.totals.multiplayer_games ?? 0

  // Portal to <body> — same transform/containing-block reason as the other modals.
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm anim-fade-in"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t.leaderboard}
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-in my-auto w-full max-w-sm card"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold">🏆 {t.leaderboard}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.close}
            className="flex h-8 w-8 items-center justify-center rounded-full text-muted transition hover:bg-surface-2 hover:text-fg"
          >
            ✕
          </button>
        </div>

        {loading ? (
          <p className="py-8 text-center text-sm text-muted">{t.lbLoading}</p>
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted">{t.lbEmpty}</p>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-muted">
                  <th className="pb-2 text-left font-semibold" colSpan={2}>
                    {t.lbPlayer}
                  </th>
                  <th className="pb-2 text-right font-semibold">{t.lbWins}</th>
                  <th className="pb-2 text-right font-semibold">{t.lbGames}</th>
                  <th
                    className="pb-2 text-right font-semibold"
                    title={t.lbStealsTitle}
                  >
                    🥷
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={r.name}
                    className={
                      'border-t border-border ' +
                      (i === 0 ? 'text-accent font-semibold' : '')
                    }
                  >
                    <td className="w-6 py-2 font-mono text-muted">{i + 1}</td>
                    <td className="max-w-[10rem] truncate py-2 pr-2">
                      {r.name}
                    </td>
                    <td className="py-2 text-right font-mono font-bold tabular-nums">
                      {r.wins}
                    </td>
                    <td className="py-2 text-right font-mono tabular-nums text-muted">
                      {r.games}
                    </td>
                    <td className="py-2 text-right font-mono tabular-nums text-muted">
                      {r.steals_won}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-center text-xs text-muted">
              {t.lbGamesRecorded(games)}
            </p>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
