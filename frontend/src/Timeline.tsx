// The core Hitster visuals: a player's year-sorted timeline, the mystery
// card and the snippet progress bar. The timeline has TWO layouts:
// - touch devices (phones/tablets): the HORIZONTAL strip (2026-07-24, like
//   cards on the physical table) — vertical stacking scrolled forever there.
// - mouse devices (pointer: fine): the original VERTICAL stack (restored
//   2026-08-16) — full-width row cards with labeled slot buttons. The
//   hidden-scrollbar strip was unusable with a mouse (nothing to swipe, the
//   wheel scrolls vertically, cards vanished behind the edge fade).
import { Fragment, useEffect, useRef, useState } from 'react'
import { Vinyl } from './fx'
import { useI18n } from './i18n'
import type { CardSnapshot } from './types'

// pointer capability effectively never changes at runtime, but stay
// subscribed anyway (docking a tablet, dev tools emulation)
function usePointerFine(): boolean {
  const [fine, setFine] = useState(
    () => window.matchMedia('(pointer: fine)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(pointer: fine)')
    const onChange = (e: MediaQueryListEvent) => setFine(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return fine
}

export function Timeline({
  cards,
  onSlotClick,
  highlightTrackId,
}: {
  cards: CardSnapshot[]
  onSlotClick: ((slot: number) => void) | null
  highlightTrackId?: string | null
}) {
  const { t } = useI18n()
  const desktop = usePointerFine()

  const slotLabel = (i: number) => {
    const prev = i > 0 ? cards[i - 1].year : null
    const next = i < cards.length ? cards[i].year : null
    return prev === null
      ? t.beforeYear(next!)
      : next === null
        ? t.afterYear(prev)
        : t.betweenYears(prev, next)
  }

  if (desktop) {
    // vertical stack: full-width row cards, slot buttons carry their label
    const renderSlot = (i: number) => (
      <button
        key={`slot-${i}`}
        type="button"
        onClick={() => onSlotClick!(i)}
        className="w-full rounded-lg border border-dashed border-border text-muted px-3 py-2 text-xs uppercase tracking-wider transition flex items-center justify-center gap-1.5 cursor-pointer hover:border-neon-cyan hover:text-neon-cyan hover:bg-neon-cyan/10 hover:shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-cyan)_30%,transparent)] active:scale-[0.98]"
      >
        <PlusIcon />
        {slotLabel(i)}
      </button>
    )
    return (
      <div className="space-y-1.5">
        {onSlotClick && renderSlot(0)}
        {cards.map((card, i) => (
          <Fragment key={card.track_id}>
            <TimelineRowCard
              card={card}
              highlight={highlightTrackId === card.track_id}
            />
            {onSlotClick && renderSlot(i + 1)}
          </Fragment>
        ))}
      </div>
    )
  }

  // touch: horizontal scroll strip, bleeding under the parent card's padding
  const renderSlot = (i: number) => (
    <button
      key={`slot-${i}`}
      type="button"
      onClick={() => onSlotClick!(i)}
      aria-label={slotLabel(i)}
      title={slotLabel(i)}
      className="w-11 shrink-0 self-stretch rounded-lg border border-dashed border-border text-muted transition flex items-center justify-center cursor-pointer hover:border-neon-cyan hover:text-neon-cyan hover:bg-neon-cyan/10 hover:shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-cyan)_30%,transparent)] active:scale-[0.96]"
    >
      <PlusIcon />
    </button>
  )
  return (
    <div className="timeline-scroll -mx-5 px-5">
      <div className="flex items-stretch gap-1.5 min-w-max py-1">
        {onSlotClick && renderSlot(0)}
        {cards.map((card, i) => (
          <Fragment key={card.track_id}>
            <TimelineCard
              card={card}
              highlight={highlightTrackId === card.track_id}
            />
            {onSlotClick && renderSlot(i + 1)}
          </Fragment>
        ))}
      </div>
    </div>
  )
}

// brings the freshly won card into view on the reveal (both layouts)
function useHighlightScroll(highlight: boolean | undefined) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (highlight) {
      ref.current?.scrollIntoView({
        inline: 'center',
        block: 'nearest',
        behavior: 'smooth',
      })
    }
  }, [highlight])
  return ref
}

// desktop: full-width row card (artwork left, big year right, blur backdrop)
function TimelineRowCard({
  card,
  highlight,
}: {
  card: CardSnapshot
  highlight?: boolean
}) {
  const ref = useHighlightScroll(highlight)
  const cls = highlight
    ? 'border-neon-green/70 ring-2 ring-neon-green/40 shadow-[0_0_18px_-2px_color-mix(in_oklab,var(--color-neon-green)_50%,transparent)] anim-pop-in'
    : 'border-border'
  return (
    <div
      ref={ref}
      className={`relative overflow-hidden rounded-xl border bg-surface-2 p-3 shadow-lg ${cls}`}
    >
      {card.artwork_url && (
        <img
          src={card.artwork_url}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 w-full h-full object-cover opacity-15 blur-xl scale-125"
          loading="lazy"
        />
      )}
      <div className="relative flex items-center gap-3">
        {card.artwork_url ? (
          <img
            src={card.artwork_url}
            alt=""
            className="w-14 h-14 rounded-lg shadow-md shrink-0"
            loading="lazy"
          />
        ) : (
          <div className="w-14 h-14 rounded-lg bg-surface shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold truncate">{card.title}</div>
          <div className="text-xs text-muted truncate mt-0.5">
            {card.artist}
          </div>
        </div>
        <div className="font-display text-2xl font-bold tabular-nums text-accent shrink-0">
          {card.year}
        </div>
      </div>
    </div>
  )
}

// touch: compact 104px portrait card for the horizontal strip
function TimelineCard({
  card,
  highlight,
}: {
  card: CardSnapshot
  highlight?: boolean
}) {
  const ref = useHighlightScroll(highlight)
  const cls = highlight
    ? 'border-neon-green/70 ring-2 ring-neon-green/40 shadow-[0_0_18px_-2px_color-mix(in_oklab,var(--color-neon-green)_50%,transparent)] anim-pop-in'
    : 'border-border'
  return (
    <div
      ref={ref}
      className={`w-[104px] shrink-0 rounded-xl border bg-surface-2 p-1.5 shadow-lg flex flex-col ${cls}`}
    >
      <div className="font-display text-lg font-bold tabular-nums text-accent text-center leading-tight">
        {card.year}
      </div>
      {card.artwork_url ? (
        <img
          src={card.artwork_url}
          alt=""
          className="w-full aspect-square rounded-lg shadow-md mt-1"
          loading="lazy"
        />
      ) : (
        <div className="w-full aspect-square rounded-lg bg-surface mt-1" />
      )}
      <div className="text-[10px] font-semibold truncate mt-1.5 text-center">
        {card.title}
      </div>
      <div className="text-[9px] text-muted truncate text-center">
        {card.artist}
      </div>
    </div>
  )
}

function PlusIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

export function MysteryCard({
  size = 'lg',
  spinning = false,
}: {
  size?: 'sm' | 'lg'
  spinning?: boolean
}) {
  const dim = size === 'lg' ? 'w-32 h-32 sm:w-36 sm:h-36' : 'w-20 h-20'
  return (
    <div
      className={`${dim} relative rounded-xl border border-neon-violet/40 bg-gradient-to-br from-surface-2 to-bg shadow-[0_0_18px_-4px_color-mix(in_oklab,var(--color-neon-violet)_45%,transparent)] flex items-center justify-center shrink-0`}
      aria-hidden="true"
    >
      <Vinyl size={size === 'lg' ? 104 : 58} spinning={spinning} />
      <span
        className="absolute font-display text-2xl font-bold text-neon-pink select-none"
        style={{ textShadow: '0 0 12px var(--color-neon-pink)' }}
      >
        ?
      </span>
    </div>
  )
}

export function SnippetProgress({ durationS }: { durationS: number }) {
  const [pct, setPct] = useState(0)
  useEffect(() => {
    const start = Date.now()
    setPct(0)
    const id = window.setInterval(() => {
      const p = Math.min(100, ((Date.now() - start) / (durationS * 1000)) * 100)
      setPct(p)
      if (p >= 100) window.clearInterval(id)
    }, 100)
    return () => window.clearInterval(id)
  }, [durationS])
  return (
    <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden">
      <div
        className="h-full rounded-full transition-[width] duration-100 ease-linear"
        style={{
          width: `${pct}%`,
          background:
            'linear-gradient(90deg, var(--color-accent), var(--color-neon-pink))',
          boxShadow:
            '0 0 10px color-mix(in oklab, var(--color-neon-pink) 60%, transparent)',
        }}
      />
    </div>
  )
}
