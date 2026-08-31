// Compact in-game player strip (replaces the old tall PlayerList card):
// avatars in their neon colours with card counts, the active player pulses,
// finishers wear medals. Host taps an avatar for kick / ±1-card actions.
import { useState, type CSSProperties } from 'react'
import { motion } from 'motion/react'
import { avatarUrl } from './avatar'
import { playerNeon } from './fx'
import { useI18n } from './i18n'
import type { Player, RoomSnapshot } from './types'

const MEDALS = ['🥇', '🥈', '🥉']

export default function ScoreStrip({
  players,
  hostId,
  cumulativeScores,
  myId,
  state,
  turnOrder,
  finishedPlayers,
  currentTurnPlayerId,
  disconnected,
  isHost,
  onKick,
  onGive,
  onTake,
}: {
  players: Player[]
  hostId: string | null
  cumulativeScores: Record<string, number>
  myId: string | null
  state: RoomSnapshot['state']
  turnOrder: string[]
  finishedPlayers: string[]
  currentTurnPlayerId: string | null
  disconnected: string[]
  isHost: boolean
  onKick: (targetId: string) => void
  onGive: (targetId: string) => void
  onTake: (targetId: string) => void
}) {
  const { t } = useI18n()
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const offline = new Set(disconnected)
  const inGame = state !== 'lobby' && state !== 'game_over'
  const isBingo = state.startsWith('bingo')
  // turn order is a spoiler during the intro spinner; in bingo there is no
  // turn order at all — the strip becomes a live marks leaderboard instead
  const isPostIntro = inGame && state !== 'classic_intro' && !isBingo
  // ±1-card corrections only exist in classic
  const canAdjust = inGame && state !== 'classic_intro' && !isBingo

  const turnIndex = new Map(turnOrder.map((id, i) => [id, i] as const))
  const finishIndex = new Map(finishedPlayers.map((id, i) => [id, i] as const))

  const sorted = [...players].sort((a, b) => {
    if (isPostIntro) {
      const ai = turnIndex.get(a.id) ?? Number.MAX_SAFE_INTEGER
      const bi = turnIndex.get(b.id) ?? Number.MAX_SAFE_INTEGER
      if (ai !== bi) return ai - bi
    }
    return (cumulativeScores[b.id] ?? 0) - (cumulativeScores[a.id] ?? 0)
  })

  return (
    <div className="card wedge-cyan px-3 py-3" aria-label={t.players}>
      <div className="flex flex-wrap items-start justify-center gap-x-2.5 gap-y-2">
        {sorted.map((p) => {
          const color = playerNeon(p.id)
          const isCurrent = isPostIntro && p.id === currentTurnPlayerId
          const isSpectator = isPostIntro && !turnIndex.has(p.id)
          const isOffline = offline.has(p.id)
          const isMe = p.id === myId
          const medal = finishIndex.has(p.id)
            ? MEDALS[finishIndex.get(p.id)!] ?? '🏁'
            : null
          const canManage = isHost && !isMe

          const avatarStyle: CSSProperties = {
            border: `2px solid ${color}`,
            background: `color-mix(in oklab, ${color} 16%, var(--color-surface-2))`,
          }
          if (isCurrent) {
            ;(avatarStyle as Record<string, string>)['--ring-c'] =
              `color-mix(in oklab, ${color} 65%, transparent)`
            avatarStyle.animation = 'beatster-ring-pulse 1.2s ease-in-out infinite'
          } else {
            avatarStyle.boxShadow = `0 0 10px color-mix(in oklab, ${color} 40%, transparent)`
          }

          const avatar = (
            <span
              className={
                'relative flex w-10 h-10 items-center justify-center rounded-full select-none transition-transform ' +
                (isCurrent ? 'scale-110' : '')
              }
              style={avatarStyle}
            >
              <img
                src={avatarUrl(p.avatar, p.name, p.is_bot)}
                alt=""
                className="w-full h-full rounded-full object-cover"
              />
              <span
                className="absolute -bottom-2 -right-2 min-w-[1.5rem] rounded-full border border-border bg-surface px-1 text-center font-mono text-[13px] font-bold tabular-nums leading-[1.45rem] shadow-md"
                aria-label={t.cardWord}
              >
                {cumulativeScores[p.id] ?? 0}
              </span>
              {medal && (
                <span className="absolute -top-2 -right-1.5 text-sm" aria-hidden="true">
                  {medal}
                </span>
              )}
              {p.id === hostId && !medal && (
                <span
                  className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[11px] select-none"
                  style={{ filter: 'drop-shadow(0 0 5px var(--color-neon-yellow))' }}
                  title={t.hostBadge}
                >
                  👑
                </span>
              )}
            </span>
          )

          return (
            <motion.div
              key={p.id}
              layout
              className={
                'relative flex w-14 flex-col items-center ' +
                (isSpectator || isOffline ? 'opacity-45' : '')
              }
            >
              {menuFor === p.id && canManage && (
                <div className="absolute -top-9 z-20 flex items-center gap-1 anim-pop-in">
                  {canAdjust && (
                    <>
                      <button
                        type="button"
                        onClick={() => onTake(p.id)}
                        className="rounded-full border border-border bg-surface px-2 py-1 text-[11px] font-bold shadow-lg"
                      >
                        −1
                      </button>
                      <button
                        type="button"
                        onClick={() => onGive(p.id)}
                        className="rounded-full border border-border bg-surface px-2 py-1 text-[11px] font-bold shadow-lg"
                      >
                        +1
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      onKick(p.id)
                      setMenuFor(null)
                    }}
                    className="whitespace-nowrap rounded-full border border-border bg-surface px-2 py-1 text-[11px] font-semibold text-red-400 shadow-lg"
                  >
                    {t.kickAction}
                  </button>
                </div>
              )}
              {canManage ? (
                <button
                  type="button"
                  onClick={() =>
                    setMenuFor((cur) => (cur === p.id ? null : p.id))
                  }
                  aria-label={t.manageAria(p.name)}
                  title={t.manageAria(p.name)}
                  className="cursor-pointer"
                >
                  {avatar}
                </button>
              ) : (
                avatar
              )}
              <span
                className={
                  'mt-1.5 w-14 truncate text-center text-[10px] leading-tight ' +
                  (isMe ? 'font-bold' : 'text-muted') +
                  (isCurrent ? ' text-fg font-semibold' : '')
                }
              >
                {p.name}
                {isOffline && ' 💤'}
              </span>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
