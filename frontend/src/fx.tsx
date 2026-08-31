// Neon-club visual effects: global background layers, the disco ball, the
// spinning vinyl (+ flying music notes while a snippet plays), equalizer bars
// and the one-shot note burst for the reveal. Pure presentation — no game
// logic. Also home of the shared per-player neon colour.
import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

export const NEON_COLORS = [
  'var(--color-neon-pink)',
  'var(--color-neon-cyan)',
  'var(--color-neon-yellow)',
  'var(--color-neon-violet)',
  'var(--color-neon-green)',
]

/** Stable per-player neon colour: same id → same colour on every client. */
export function playerNeon(id: string): string {
  let h = 0
  for (const ch of id) h = (h * 31 + (ch.codePointAt(0) ?? 0)) >>> 0
  return NEON_COLORS[h % NEON_COLORS.length]
}

/** Rotating light beams + film grain, mounted once in the app shell. */
export function FxLayers() {
  return (
    <>
      <div className="fx-beams" aria-hidden="true" />
      <div className="fx-grain" aria-hidden="true" />
    </>
  )
}

export function DiscoBall({
  size = 58,
  hang = true,
}: {
  size?: number
  hang?: boolean
}) {
  return (
    <div className="relative inline-flex flex-col items-center" aria-hidden="true">
      {hang && <div className="w-px h-7 bg-border" />}
      <div className="disco-ball" style={{ width: size, height: size }} />
    </div>
  )
}

/** Spinning vinyl whose rotation is actually VISIBLE: broken groove arcs, a
 *  curved label print and a bright rim marker rotate; a specular sheen stays
 *  static on top (like light on a real record). */
export function Vinyl({
  size = 150,
  spinning = true,
}: {
  size?: number
  spinning?: boolean
}) {
  return (
    <div
      className="relative inline-block"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 96 96"
        className={
          'w-full h-full drop-shadow-[0_0_18px_color-mix(in_oklab,var(--color-neon-pink)_45%,transparent)]' +
          (spinning ? ' anim-spin-vinyl' : '')
        }
      >
        <defs>
          <path
            id="vinyl-label-arc"
            d="M 48 35.5 a 12.5 12.5 0 1 1 -0.01 0"
            fill="none"
          />
        </defs>
        <circle cx="48" cy="48" r="46" fill="oklch(0.17 0.02 285)" />
        {/* broken groove arcs — the gaps make the spin readable */}
        <circle
          cx="48" cy="48" r="41"
          fill="none" stroke="oklch(0.34 0.03 285)" strokeWidth="1.4"
          strokeDasharray="30 12 52 18"
        />
        <circle
          cx="48" cy="48" r="35"
          fill="none" stroke="oklch(0.31 0.03 285)" strokeWidth="1.2"
          strokeDasharray="44 16 24 10"
        />
        <circle
          cx="48" cy="48" r="29"
          fill="none" stroke="oklch(0.34 0.03 285)" strokeWidth="1.4"
          strokeDasharray="18 9 38 14"
        />
        <circle
          cx="48" cy="48" r="23.5"
          fill="none" stroke="oklch(0.3 0.03 285)" strokeWidth="1"
          strokeDasharray="52 20"
        />
        {/* bright rim marker — the clearest rotation cue */}
        <circle cx="48" cy="5.5" r="1.7" fill="var(--color-neon-cyan)" />
        {/* label with curved print + notch */}
        <circle cx="48" cy="48" r="17" fill="var(--color-accent)" />
        <text
          fontSize="5.2"
          fontWeight="bold"
          letterSpacing="1.2"
          fill="oklch(0.2 0.03 285)"
          fontFamily="Space Grotesk, sans-serif"
        >
          <textPath href="#vinyl-label-arc" startOffset="2">
            BEATSTER · ONLINE
          </textPath>
        </text>
        <circle cx="48" cy="61.5" r="1.4" fill="oklch(0.2 0.03 285)" />
        <circle cx="48" cy="48" r="3" fill="oklch(0.17 0.02 285)" />
      </svg>
      {/* static specular sheen — does NOT rotate, sells the motion underneath */}
      <div
        className="absolute inset-0 rounded-full pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 30% 24%, rgb(255 255 255 / 0.2), transparent 42%),' +
            'radial-gradient(circle at 72% 80%, rgb(255 255 255 / 0.06), transparent 38%)',
        }}
      />
    </div>
  )
}

const NOTE_GLYPHS = ['♪', '♫', '♬', '♩']

type Note = {
  id: number
  glyph: string
  color: string
  x0: number
  y0: number
  x1: number
  y1: number
  rot: number
  dur: number
}

/** Spinning vinyl that emits floating neon music notes while `playing`. */
export function VinylNotes({
  size = 150,
  playing = true,
}: {
  size?: number
  playing?: boolean
}) {
  const reduced = useReducedMotion()
  const [notes, setNotes] = useState<Note[]>([])
  const nextId = useRef(0)

  useEffect(() => {
    if (!playing || reduced) return
    const spawn = () => {
      setNotes((cur) => {
        const trimmed = cur.length > 7 ? cur.slice(cur.length - 7) : cur
        const side = Math.random() < 0.5 ? -1 : 1
        const x0 = side * (14 + Math.random() * 40)
        const y0 = -6 - Math.random() * 30
        const note: Note = {
          id: nextId.current++,
          glyph: NOTE_GLYPHS[Math.floor(Math.random() * NOTE_GLYPHS.length)],
          color: NEON_COLORS[Math.floor(Math.random() * NEON_COLORS.length)],
          x0,
          y0,
          x1: x0 + side * (26 + Math.random() * 46),
          y1: y0 - (64 + Math.random() * 56),
          rot: side * (12 + Math.random() * 26),
          dur: 1.7 + Math.random() * 0.9,
        }
        return [...trimmed, note]
      })
    }
    spawn()
    const id = window.setInterval(spawn, 460)
    return () => window.clearInterval(id)
  }, [playing, reduced])

  useEffect(() => {
    if (!playing) setNotes([])
  }, [playing])

  return (
    <div
      className="relative inline-block"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Vinyl size={size} />
      <div className="absolute inset-0 flex items-center justify-center overflow-visible pointer-events-none">
        <AnimatePresence>
          {notes.map((n) => (
            <motion.span
              key={n.id}
              className="absolute font-bold select-none"
              style={{
                color: n.color,
                fontSize: '1.35rem',
                textShadow: `0 0 10px ${n.color}`,
              }}
              initial={{ opacity: 0, x: n.x0, y: n.y0, scale: 0.7, rotate: 0 }}
              animate={{
                opacity: [0, 1, 1, 0],
                x: n.x1,
                y: n.y1,
                scale: 1.15,
                rotate: n.rot,
              }}
              exit={{ opacity: 0 }}
              transition={{ duration: n.dur, ease: 'easeOut', times: [0, 0.15, 0.75, 1] }}
              onAnimationComplete={() =>
                setNotes((cur) => cur.filter((x) => x.id !== n.id))
              }
            >
              {n.glyph}
            </motion.span>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

/** Little bouncing equalizer, e.g. next to a "now playing" label. */
export function EqBars({ className = '' }: { className?: string }) {
  return (
    <span
      className={'inline-flex items-end gap-[2.5px] h-3.5 ' + className}
      aria-hidden="true"
    >
      {[0, 1, 2, 3].map((i) => (
        <i key={i} className="eq-bar" style={{ animationDelay: `${-i * 0.23}s` }} />
      ))}
    </span>
  )
}

/** One-shot radial burst of glowing notes — mount it on a win moment.
 *  Deterministic spread so re-renders don't reshuffle. */
export function NoteBurst({ count = 10 }: { count?: number }) {
  const reduced = useReducedMotion()
  const parts = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => {
        const angle = (i / count) * Math.PI * 2 + (i % 3) * 0.25
        const dist = 58 + ((i * 37) % 46)
        return {
          id: i,
          glyph: NOTE_GLYPHS[i % NOTE_GLYPHS.length],
          color: NEON_COLORS[i % NEON_COLORS.length],
          x: Math.cos(angle) * dist,
          y: Math.sin(angle) * dist - 16,
          rot: ((i * 53) % 60) - 30,
          dur: 1.05 + ((i * 29) % 50) / 100,
        }
      }),
    [count],
  )
  if (reduced) return null
  return (
    <span
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
      aria-hidden="true"
    >
      {parts.map((p) => (
        <motion.span
          key={p.id}
          className="absolute font-bold select-none"
          style={{
            color: p.color,
            textShadow: `0 0 10px ${p.color}`,
            fontSize: '1.25rem',
          }}
          initial={{ opacity: 1, x: 0, y: 0, scale: 0.5 }}
          animate={{ opacity: 0, x: p.x, y: p.y, scale: 1.25, rotate: p.rot }}
          transition={{ duration: p.dur, ease: 'easeOut' }}
        >
          {p.glyph}
        </motion.span>
      ))}
    </span>
  )
}
