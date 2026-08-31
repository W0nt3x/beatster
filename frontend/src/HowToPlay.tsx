import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'motion/react'
import { BingoCardGrid } from './bingo'
import { DiscoBall, Vinyl } from './fx'
import { useI18n } from './i18n'
import type { GameMode } from './types'

// A 3-step carousel explaining the game, opened from the room header ("?" icon)
// and the landing page ("How to play" link). Controlled by the parent page via
// `open` / `onClose` — there's only ever one page mounted, so no shared state.
// Each game mode has its own slide set: a room passes its `mode` (locked to
// what's being played there); the landing passes none and gets mode tabs.
export default function HowToPlay({
  open,
  onClose,
  mode,
}: {
  open: boolean
  onClose: () => void
  mode?: GameMode
}) {
  const { t } = useI18n()
  const h = t.howToPlay
  const [step, setStep] = useState(0)
  const [tab, setTab] = useState<GameMode>('classic')
  const activeMode = mode ?? tab
  const modalRef = useRef<HTMLDivElement>(null)

  // keep the latest onClose without re-running the focus-trap effect (the parent
  // passes a fresh closure each render; we only want the trap to (re)arm on open)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  // always start on the first slide (and the room's mode) when reopened
  useEffect(() => {
    if (open) {
      setStep(0)
      setTab(mode ?? 'classic')
    }
  }, [open, mode])

  // focus trap + Esc-to-close + restore focus to the trigger on close
  useEffect(() => {
    if (!open) return
    const prevFocus = document.activeElement as HTMLElement | null
    const focusables = (): HTMLElement[] => {
      const root = modalRef.current
      if (!root) return []
      return Array.from(
        root.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
        ),
      )
    }
    focusables()[0]?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return
      const f = focusables()
      if (f.length === 0) return
      const first = f[0]
      const last = f[f.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prevFocus?.focus?.()
    }
  }, [open])

  if (!open) return null

  const isLast = step === 2
  const goNext = () => {
    if (isLast) onClose()
    else setStep((s) => Math.min(2, s + 1))
  }

  // Portal to <body>: the room header carries `anim-fade-in`, whose `both`
  // fill-mode leaves a `transform` that would otherwise become the containing
  // block for this `fixed` overlay and pin it to the header (same reason the QR
  // modal portals).
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto p-4 backdrop-blur-sm"
      style={{ backgroundColor: 'rgba(8,9,12,.62)' }}
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={h.title}
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-in card wedge-violet my-auto w-full max-w-[380px]"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold">{h.title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.close}
            className="flex h-8 w-8 items-center justify-center rounded-full text-muted transition hover:bg-surface-2 hover:text-fg"
          >
            ✕
          </button>
        </div>

        {mode == null && (
          <div className="mb-4 flex rounded-lg border border-border bg-surface-2 p-0.5">
            {(['classic', 'bingo'] as const).map((m) => {
              const on = activeMode === m
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setTab(m)
                    setStep(0)
                  }}
                  aria-pressed={on}
                  className={
                    'flex-1 rounded-md px-3 py-1.5 text-sm font-semibold transition ' +
                    (on
                      ? m === 'classic'
                        ? 'bg-accent/20 text-accent'
                        : 'bg-neon-cyan/20 text-neon-cyan'
                      : 'text-muted hover:text-fg')
                  }
                >
                  {m === 'classic' ? h.modeClassic : h.modeBingo}
                </button>
              )
            })}
          </div>
        )}

        <div className="overflow-hidden">
          <motion.div
            key={activeMode}
            className="flex w-[300%]"
            animate={{ x: `-${step * 33.333}%` }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
          >
            {activeMode === 'classic' ? (
              <>
                <Slide>
                  <IconTile color="var(--color-neon-pink)">
                    <Vinyl size={56} />
                  </IconTile>
                  <StepTitle>{h.listenTitle}</StepTitle>
                  <StepBody>{h.listenBody}</StepBody>
                </Slide>

                <Slide>
                  <MiniTimeline
                    before={h.slotBefore}
                    between={h.slotBetween}
                    after={h.slotAfter}
                  />
                  <StepTitle>{h.placeTitle}</StepTitle>
                  <StepBody>{h.placeBody}</StepBody>
                </Slide>

                <Slide>
                  <IconTile color="var(--color-neon-yellow)">
                    <TrophyIcon />
                  </IconTile>
                  <StepTitle>{h.collectTitle}</StepTitle>
                  <StepBody>{h.collectBody}</StepBody>
                  <div className="mt-1 flex items-start gap-2 rounded-[10px] border border-border bg-bg px-3 py-2.5 text-left">
                    <span className="mt-0.5 shrink-0 text-accent">
                      <TrendUpIcon />
                    </span>
                    <p className="text-xs leading-relaxed text-muted">
                      {h.difficultyNote}
                    </p>
                  </div>
                </Slide>
              </>
            ) : (
              <>
                <Slide>
                  <IconTile color="var(--color-neon-violet)">
                    <DiscoBall size={44} />
                  </IconTile>
                  <StepTitle>{h.bingoSpinTitle}</StepTitle>
                  <StepBody>{h.bingoSpinBody}</StepBody>
                </Slide>

                <Slide>
                  <MiniBingoCard />
                  <StepTitle>{h.bingoMarkTitle}</StepTitle>
                  <StepBody>{h.bingoMarkBody}</StepBody>
                </Slide>

                <Slide>
                  <IconTile color="var(--color-neon-yellow)">
                    <TrophyIcon />
                  </IconTile>
                  <StepTitle>{h.bingoWinTitle}</StepTitle>
                  <StepBody>{h.bingoWinBody}</StepBody>
                  <div className="mt-1 flex items-start gap-2 rounded-[10px] border border-border bg-bg px-3 py-2.5 text-left">
                    <span className="mt-0.5 shrink-0" aria-hidden="true">
                      💥
                    </span>
                    <p className="text-xs leading-relaxed text-muted">
                      {h.bingoEraseNote}
                    </p>
                  </div>
                </Slide>
              </>
            )}
          </motion.div>
        </div>

        <div className="mt-5 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            {[0, 1, 2].map((i) => (
              <button
                key={i}
                type="button"
                onClick={() => setStep(i)}
                aria-label={String(i + 1)}
                aria-current={i === step}
                className={
                  'h-2 rounded-full transition-all duration-300 motion-reduce:transition-none ' +
                  (i === step
                    ? 'w-[22px] bg-neon-pink shadow-[0_0_8px_color-mix(in_oklab,var(--color-neon-pink)_60%,transparent)]'
                    : 'w-2 bg-border hover:bg-muted')
                }
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
              className="px-3 py-2 text-sm font-semibold text-muted transition hover:text-fg disabled:cursor-default disabled:opacity-35 disabled:hover:text-muted"
            >
              {h.back}
            </button>
            <button
              type="button"
              onClick={goNext}
              className="rounded-lg px-5 py-2 text-sm font-semibold text-accent-fg transition hover:brightness-110 active:scale-[0.98]"
              style={{
                background:
                  'linear-gradient(95deg, var(--color-accent), var(--color-neon-pink))',
                boxShadow:
                  '0 3px 16px color-mix(in oklab, var(--color-neon-pink) 35%, transparent)',
              }}
            >
              {isLast ? h.got : h.next}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function Slide({ children }: { children: ReactNode }) {
  return (
    <div className="flex w-1/3 shrink-0 flex-col items-center gap-3 px-1 pb-1 pt-2 text-center">
      {children}
    </div>
  )
}

function IconTile({
  color,
  children,
}: {
  color: string
  children: ReactNode
}) {
  return (
    <div
      className="flex h-[74px] w-[74px] items-center justify-center rounded-2xl bg-surface-2"
      style={{
        color,
        border: `1px solid color-mix(in oklab, ${color} 45%, transparent)`,
        boxShadow: `0 0 18px -4px color-mix(in oklab, ${color} 50%, transparent)`,
      }}
    >
      {children}
    </div>
  )
}

function StepTitle({ children }: { children: ReactNode }) {
  return <h3 className="font-display text-xl font-bold">{children}</h3>
}

function StepBody({ children }: { children: ReactNode }) {
  return <p className="text-sm leading-relaxed text-muted">{children}</p>
}

/** A tiny static 5x5 card, top row one mark short of a bingo — the visual for
 *  the marking slide. Deterministic latin-square colours, non-interactive. */
function MiniBingoCard() {
  const card = Array.from({ length: 25 }, (_, i) => (Math.floor(i / 5) + i) % 5)
  return (
    <div className="w-[124px] pointer-events-none" aria-hidden="true">
      <BingoCardGrid card={card} marks={[0, 1, 2, 3]} />
    </div>
  )
}

function MiniTimeline({
  before,
  between,
  after,
}: {
  before: string
  between: string
  after: string
}) {
  return (
    <div className="flex h-[74px] w-full items-center justify-center gap-1.5 pt-5">
      <SlotCell label={before} />
      <YearCard year={1971} />
      <SlotCell label={between} highlight />
      <YearCard year={1994} />
      <SlotCell label={after} />
    </div>
  )
}

function SlotCell({
  label,
  highlight = false,
}: {
  label: string
  highlight?: boolean
}) {
  return (
    <div
      className={
        'relative flex min-w-[42px] items-center justify-center rounded-md border border-dashed px-1.5 py-2.5 ' +
        (highlight
          ? 'border-neon-cyan/70 bg-neon-cyan/10 text-neon-cyan shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-cyan)_30%,transparent)]'
          : 'border-border text-muted')
      }
    >
      {highlight && (
        <span className="absolute -top-6 left-1/2 flex -translate-x-1/2 flex-col items-center">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-neon-cyan font-display text-sm font-bold text-accent-fg shadow-md">
            ?
          </span>
          <span className="-mt-px h-0 w-0 border-x-[5px] border-t-[6px] border-x-transparent border-t-neon-cyan" />
        </span>
      )}
      <span className="whitespace-nowrap text-[8px] uppercase leading-none tracking-wider">
        {label}
      </span>
    </div>
  )
}

function YearCard({ year }: { year: number }) {
  return (
    <div className="flex items-center justify-center rounded-md border border-border bg-surface-2 px-2 py-2.5 font-display text-sm font-bold tabular-nums text-accent">
      {year}
    </div>
  )
}

function TrophyIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="32"
      height="32"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
      <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
      <path d="M4 22h16" />
      <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
      <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
      <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
    </svg>
  )
}

function TrendUpIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  )
}
