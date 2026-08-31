// Shared bingo-mode pieces: the five board-slot colours (selection order of
// the host's categories = slot = colour, like the physical board), category
// metadata mirroring the backend pool, and the 5x5 card grid component used
// by the lobby preview, the reveal and the marking phase.
import type { Messages } from './i18n'

export type BingoKind =
  | 'year_range'
  | 'exact_year'
  | 'decade'
  | 'before_year'
  | 'artist'
  | 'title'
  | 'any_text'
  | 'vs_prev'
  | 'closest_year'

export const BINGO_POOL: Record<
  string,
  { kind: BingoKind; tolerance?: number; pivot?: number; icon: string }
> = {
  year1: { kind: 'year_range', tolerance: 1, icon: '🎯' },
  year2: { kind: 'year_range', tolerance: 2, icon: '🎯' },
  year3: { kind: 'year_range', tolerance: 3, icon: '🎯' },
  year4: { kind: 'year_range', tolerance: 4, icon: '🎯' },
  year5: { kind: 'year_range', tolerance: 5, icon: '🎯' },
  decade: { kind: 'decade', icon: '🔟' },
  before1990: { kind: 'before_year', pivot: 1990, icon: '⚖️' },
  before2000: { kind: 'before_year', pivot: 2000, icon: '⚖️' },
  before2010: { kind: 'before_year', pivot: 2010, icon: '⚖️' },
  exact: { kind: 'exact_year', icon: '💎' },
  artist: { kind: 'artist', icon: '🎤' },
  title: { kind: 'title', icon: '💬' },
  anytext: { kind: 'any_text', icon: '🃏' },
  prevsong: { kind: 'vs_prev', icon: '⚔️' },
  closest: { kind: 'closest_year', icon: '🏹' },
}

export function bingoCategoryLabel(id: string, t: Messages): string {
  const cat = t.bingo.cat as Record<string, string>
  return cat[id] ?? id
}

/** Board slot 0..4 → neon colour, matching the physical board's segment
 *  order (yellow, green, violet, cyan, pink). All Tailwind classes are
 *  written out per slot so the compiler sees them. */
export const BINGO_SLOT_STYLE: {
  key: string
  color: string
  chip: string
  cellOff: string
  cellOn: string
}[] = [
  {
    key: 'yellow',
    color: 'var(--color-neon-yellow)',
    chip: 'bg-neon-yellow/10 border-neon-yellow/60 text-neon-yellow',
    cellOff: 'bg-neon-yellow/15 border-neon-yellow/30',
    cellOn:
      'bg-neon-yellow/80 border-neon-yellow shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-yellow)_60%,transparent)]',
  },
  {
    key: 'green',
    color: 'var(--color-neon-green)',
    chip: 'bg-neon-green/10 border-neon-green/60 text-neon-green',
    cellOff: 'bg-neon-green/15 border-neon-green/30',
    cellOn:
      'bg-neon-green/80 border-neon-green shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-green)_60%,transparent)]',
  },
  {
    key: 'violet',
    color: 'var(--color-neon-violet)',
    chip: 'bg-neon-violet/10 border-neon-violet/60 text-neon-violet',
    cellOff: 'bg-neon-violet/15 border-neon-violet/30',
    cellOn:
      'bg-neon-violet/80 border-neon-violet shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-violet)_60%,transparent)]',
  },
  {
    key: 'cyan',
    color: 'var(--color-neon-cyan)',
    chip: 'bg-neon-cyan/10 border-neon-cyan/60 text-neon-cyan',
    cellOff: 'bg-neon-cyan/15 border-neon-cyan/30',
    cellOn:
      'bg-neon-cyan/80 border-neon-cyan shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-cyan)_60%,transparent)]',
  },
  {
    key: 'pink',
    color: 'var(--color-neon-pink)',
    chip: 'bg-neon-pink/10 border-neon-pink/60 text-neon-pink',
    cellOff: 'bg-neon-pink/15 border-neon-pink/30',
    cellOn:
      'bg-neon-pink/80 border-neon-pink shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-pink)_60%,transparent)]',
  },
]

/** One 5x5 bingo card. `selectable` lights up the legal cells:
 *  'mark'  — own free cells of the drawn colour (activeSlot)
 *  'erase' — an opponent's marked cells (any colour)               */
export function BingoCardGrid({
  card,
  marks,
  activeSlot = null,
  selectable = 'none',
  onCellClick,
  cellAria,
}: {
  card: number[]
  marks: number[]
  activeSlot?: number | null
  selectable?: 'none' | 'mark' | 'erase'
  onCellClick?: (cell: number) => void
  cellAria?: (row: number, col: number) => string
}) {
  const marked = new Set(marks)
  return (
    <div className="grid grid-cols-5 gap-1" role="grid">
      {card.map((slot, i) => {
        const style = BINGO_SLOT_STYLE[slot] ?? BINGO_SLOT_STYLE[0]
        const isMarked = marked.has(i)
        const canMark =
          selectable === 'mark' && !isMarked && slot === activeSlot
        const canErase = selectable === 'erase' && isMarked
        const clickable = (canMark || canErase) && onCellClick != null
        const dimmed =
          selectable === 'mark' && !isMarked && slot !== activeSlot
        const cls =
          'aspect-square rounded-md border flex items-center justify-center transition ' +
          (isMarked ? style.cellOn : style.cellOff) +
          (clickable
            ? ' cursor-pointer ring-2 ring-white/70 animate-pulse hover:animate-none active:scale-95'
            : '') +
          (dimmed ? ' opacity-40' : '')
        const inner = isMarked ? (
          <span
            className="font-display font-bold text-black/80 text-[max(12px,60%)] leading-none select-none"
            aria-hidden="true"
          >
            ✕
          </span>
        ) : null
        if (clickable) {
          return (
            <button
              key={i}
              type="button"
              onClick={() => onCellClick(i)}
              aria-label={cellAria?.(Math.floor(i / 5) + 1, (i % 5) + 1)}
              className={cls}
            >
              {inner}
            </button>
          )
        }
        return (
          <div key={i} role="gridcell" className={cls}>
            {inner}
          </div>
        )
      })}
    </div>
  )
}
