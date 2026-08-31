// The lobby stage: a disco ball over a neon dance floor, the players as
// glowing, gently bobbing dancers. Presentation + the host's kick popover —
// no game logic lives here.
import { useState, type CSSProperties } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { avatarUrl } from './avatar'
import AvatarPicker from './AvatarPicker'
import { DiscoBall, NEON_COLORS, playerNeon } from './fx'
import { useI18n } from './i18n'
import type { Player } from './types'

const TILE_COLS = 8
const TILE_COUNT = 32
const LIT = new Set([2, 6, 9, 13, 18, 22, 27, 29])

export default function Dancefloor({
  code,
  players,
  hostId,
  myId,
  isHost,
  isSingleplayer,
  onKick,
  onSetAvatar,
}: {
  code: string
  players: Player[]
  hostId: string | null
  myId: string | null
  isHost: boolean
  isSingleplayer: boolean
  onKick: (targetId: string) => void
  onSetAvatar: (avatar: string) => void
}) {
  const { t } = useI18n()
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const me = players.find((p) => p.id === myId)

  const copyInvite = () => {
    navigator.clipboard
      ?.writeText(`${window.location.origin}/r/${code}`)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1600)
      })
      .catch(() => {})
  }

  return (
    // side fade on the CONTAINER: the floor plane is cropped by this box's
    // overflow, so without a mask here its cut edges show as hard verticals
    // (the plane's own radial mask can't help against the container crop)
    <div
      className="relative h-56 overflow-hidden"
      style={{
        maskImage:
          'linear-gradient(90deg, transparent, black 9%, black 91%, transparent)',
        WebkitMaskImage:
          'linear-gradient(90deg, transparent, black 9%, black 91%, transparent)',
      }}
      aria-label={t.players}
    >
      <div className="absolute top-0 left-1/2 -translate-x-1/2 z-0">
        <DiscoBall size={46} />
      </div>

      <div
        className="absolute -bottom-9 left-1/2 grid gap-[3px] z-0"
        style={{
          width: '160%',
          height: 160,
          gridTemplateColumns: `repeat(${TILE_COLS}, 1fr)`,
          transform: 'translateX(-50%) perspective(430px) rotateX(58deg)',
          // fade the plane out toward all edges — without this the tile grid
          // reads as a hard-edged rectangle instead of a pool of light
          maskImage:
            'radial-gradient(ellipse 52% 78% at 50% 72%, black 42%, transparent 95%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 52% 78% at 50% 72%, black 42%, transparent 95%)',
        }}
        aria-hidden="true"
      >
        {Array.from({ length: TILE_COUNT }, (_, i) => {
          const lit = LIT.has(i)
          return (
            <i
              key={i}
              className={'floor-tile' + (lit ? ' lit' : '')}
              style={
                {
                  '--tile': NEON_COLORS[(i * 3 + (i >> 3)) % NEON_COLORS.length],
                  animationDelay: lit ? `${-(i % 7) * 0.37}s` : undefined,
                } as CSSProperties
              }
            />
          )
        })}
      </div>

      {/* fade the bottom crop line of the floor into the page background */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-8 z-[5]"
        style={{
          background: 'linear-gradient(180deg, transparent, var(--color-bg))',
        }}
        aria-hidden="true"
      />

      <div className="absolute inset-x-0 bottom-9 z-10 flex flex-wrap items-end justify-center gap-x-3.5 gap-y-2 px-2">
        <AnimatePresence>
          {players.map((p, i) => (
            <Dancer
              key={p.id}
              player={p}
              color={playerNeon(p.id)}
              isHostPlayer={p.id === hostId}
              isMe={p.id === myId}
              canManage={isHost && p.id !== myId}
              menuOpen={menuFor === p.id}
              onToggleMenu={() =>
                setMenuFor((cur) => (cur === p.id ? null : p.id))
              }
              onKick={() => {
                onKick(p.id)
                setMenuFor(null)
              }}
              onOpenPicker={() => setPickerOpen(true)}
              delayIndex={i}
            />
          ))}
        </AnimatePresence>
        {!isSingleplayer && (
          /* the open spot IS an invite button — tap copies the invite link
             (same quick action as tapping the room code; QR stays on the
             neon-sign chip) */
          <button
            type="button"
            onClick={copyInvite}
            aria-label={t.copyInvite}
            title={t.copyInvite}
            className="group flex flex-col items-center w-16 pb-px cursor-pointer"
          >
            <span
              className={
                'w-11 h-11 rounded-full border-2 border-dashed flex items-center justify-center text-lg select-none transition ' +
                (copied
                  ? 'border-neon-green text-neon-green shadow-[0_0_14px_color-mix(in_oklab,var(--color-neon-green)_45%,transparent)]'
                  : 'border-border text-muted group-hover:border-neon-pink group-hover:text-neon-pink group-hover:shadow-[0_0_14px_color-mix(in_oklab,var(--color-neon-pink)_40%,transparent)]')
              }
              style={
                copied
                  ? undefined
                  : { animation: 'beatster-wait-pulse 2s ease-in-out infinite' }
              }
            >
              {copied ? '✓' : '+'}
            </span>
            <span
              className={
                'text-[11px] mt-1 transition ' +
                (copied
                  ? 'text-neon-green font-semibold'
                  : 'text-muted group-hover:text-neon-pink')
              }
            >
              {copied ? t.copied : t.invite}
            </span>
          </button>
        )}
      </div>

      {me && (
        <AvatarPicker
          open={pickerOpen}
          name={me.name}
          current={me.avatar}
          onPick={onSetAvatar}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  )
}

function Dancer({
  player,
  color,
  isHostPlayer,
  isMe,
  canManage,
  menuOpen,
  onToggleMenu,
  onKick,
  onOpenPicker,
  delayIndex,
}: {
  player: Player
  color: string
  isHostPlayer: boolean
  isMe: boolean
  canManage: boolean
  menuOpen: boolean
  onToggleMenu: () => void
  onKick: () => void
  onOpenPicker: () => void
  delayIndex: number
}) {
  const { t } = useI18n()

  const badge = (
    <span
      className="block w-11 h-11 rounded-full overflow-hidden select-none"
      style={{
        border: `2px solid ${color}`,
        background: `color-mix(in oklab, ${color} 16%, var(--color-surface-2))`,
        boxShadow: `0 0 12px color-mix(in oklab, ${color} 55%, transparent)`,
      }}
    >
      <img
        src={avatarUrl(player.avatar, player.name, player.is_bot)}
        alt=""
        className="w-full h-full object-cover"
      />
    </span>
  )

  return (
    <motion.div
      layout
      initial={{ scale: 0, y: 18, opacity: 0 }}
      animate={{ scale: 1, y: 0, opacity: 1 }}
      exit={{ scale: 0, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 320, damping: 22 }}
      className="relative flex flex-col items-center w-16"
    >
      {menuOpen && (
        <div className="absolute -top-8 z-20 anim-pop-in">
          <button
            type="button"
            onClick={onKick}
            className="text-xs font-semibold text-red-400 bg-surface border border-border rounded-full px-3 py-1 shadow-lg whitespace-nowrap"
          >
            {t.kickAction}
          </button>
        </div>
      )}
      <div
        className="relative anim-bob"
        style={{ animationDelay: `${-(delayIndex % 5) * 0.35}s` }}
      >
        {isHostPlayer && (
          <span
            className="absolute -top-3.5 left-1/2 -translate-x-1/2 text-sm select-none"
            style={{ filter: 'drop-shadow(0 0 6px var(--color-neon-yellow))' }}
            title={t.hostBadge}
            aria-label={t.hostBadge}
          >
            👑
          </span>
        )}
        {canManage ? (
          <button
            type="button"
            onClick={onToggleMenu}
            aria-label={t.manageAria(player.name)}
            title={t.manageAria(player.name)}
            className="block cursor-pointer"
          >
            {badge}
          </button>
        ) : isMe ? (
          <button
            type="button"
            onClick={onOpenPicker}
            aria-label={t.avatarTitle}
            title={t.avatarTitle}
            className="block cursor-pointer transition hover:scale-105"
          >
            {badge}
          </button>
        ) : (
          badge
        )}
      </div>
      <span
        className={
          'text-[11px] mt-1 max-w-16 truncate ' + (isMe ? 'font-bold' : '')
        }
      >
        {player.name}
      </span>
    </motion.div>
  )
}
