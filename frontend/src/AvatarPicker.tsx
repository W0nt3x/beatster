// Avatar picker modal: three DiceBear styles with rerollable seed candidates,
// plus the custom meme catalog (src/avatars/, if any images are dropped in).
// Opened by tapping your own dancer on the lobby dance floor.
import { useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AVATAR_STYLES,
  CUSTOM_AVATARS,
  avatarUrl,
  randomSeed,
} from './avatar'
import { useI18n } from './i18n'

function makeSeeds(name: string): string[] {
  return [name, ...Array.from({ length: 7 }, randomSeed)]
}

export default function AvatarPicker({
  open,
  name,
  current,
  onPick,
  onClose,
}: {
  open: boolean
  name: string
  current: string
  onPick: (avatar: string) => void
  onClose: () => void
}) {
  const { t } = useI18n()
  const [seeds, setSeeds] = useState<string[]>(() => makeSeeds(name))
  if (!open) return null
  const styleKey = AVATAR_STYLES[0]

  const customs = Object.keys(CUSTOM_AVATARS).sort()

  const pick = (avatar: string) => {
    onPick(avatar)
    onClose()
  }

  // Portal to <body>: fixed overlays must escape transformed ancestors.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/70 p-4 anim-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t.avatarTitle}
    >
      <div
        className="card wedge-pink w-full max-w-sm my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-display text-lg font-bold mb-3">{t.avatarTitle}</h3>

        <div className="grid grid-cols-4 gap-2.5">
          {seeds.map((seed) => {
            const id = `${styleKey}:${seed}`
            const selected = id === current
            return (
              <button
                key={seed}
                type="button"
                onClick={() => pick(id)}
                className={
                  'aspect-square rounded-full overflow-hidden border-2 bg-surface-2 transition hover:scale-105 ' +
                  (selected
                    ? 'border-neon-green shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-green)_50%,transparent)]'
                    : 'border-border hover:border-neon-pink')
                }
              >
                <img
                  src={avatarUrl(id, name, false)}
                  alt=""
                  className="w-full h-full object-cover"
                />
              </button>
            )
          })}
        </div>

        <button
          type="button"
          onClick={() => setSeeds(makeSeeds(name).map((_, i) => (i === 0 ? name : randomSeed())))}
          className="btn-secondary w-full mt-3 py-2 text-sm"
        >
          🎲 {t.avatarReroll}
        </button>

        {customs.length > 0 && (
          <>
            <p className="text-[10px] uppercase tracking-wider font-semibold text-neon-violet mt-4 mb-2">
              {t.avatarCustomSection}
            </p>
            <div className="grid grid-cols-4 gap-2.5">
              {customs.map((key) => {
                const id = `img:${key}`
                const selected = id === current
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => pick(id)}
                    className={
                      'aspect-square rounded-full overflow-hidden border-2 bg-surface-2 transition hover:scale-105 ' +
                      (selected
                        ? 'border-neon-green shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-green)_50%,transparent)]'
                        : 'border-border hover:border-neon-pink')
                    }
                  >
                    <img
                      src={CUSTOM_AVATARS[key]}
                      alt={key}
                      className="w-full h-full object-cover"
                    />
                  </button>
                )
              })}
            </div>
          </>
        )}

        <button
          type="button"
          onClick={onClose}
          className="btn-secondary w-full mt-4"
        >
          {t.close}
        </button>
      </div>
    </div>,
    document.body,
  )
}
