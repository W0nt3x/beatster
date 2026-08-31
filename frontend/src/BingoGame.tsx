// The bingo-mode game views: the disco-ball category spin, the simultaneous
// answering phase (everyone hears the same song and types at once) and the
// reveal, which doubles as the marking/erasing phase. All rules live on the
// server — these components only render the snapshot and send intents.
import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import {
  BINGO_POOL,
  BINGO_SLOT_STYLE,
  BingoCardGrid,
  bingoCategoryLabel,
} from './bingo'
import { DiscoBall, EqBars, NoteBurst } from './fx'
import { useI18n, type Messages } from './i18n'
import { Avatar, CountdownBar, CouchIcon } from './ui'
import type { RoomSnapshot } from './types'

function CategoryPill({
  categoryId,
  slot,
  big = false,
}: {
  categoryId: string
  slot: number
  big?: boolean
}) {
  const { t } = useI18n()
  const style = BINGO_SLOT_STYLE[slot] ?? BINGO_SLOT_STYLE[0]
  const info = BINGO_POOL[categoryId]
  return (
    <span
      className={
        `inline-flex items-center gap-1.5 rounded-full border font-semibold ${style.chip} ` +
        (big ? 'px-4 py-1.5 text-base' : 'px-2.5 py-1 text-xs')
      }
      style={{
        boxShadow: `0 0 ${big ? 16 : 10}px color-mix(in oklab, ${style.color} 35%, transparent)`,
      }}
    >
      <span aria-hidden="true">{info?.icon ?? '🎵'}</span>
      {bingoCategoryLabel(categoryId, t)}
    </span>
  )
}

/** How many participants the round is actually waiting on. */
function activeCount(snapshot: RoomSnapshot): number {
  return snapshot.turn_order.filter(
    (id) =>
      !snapshot.disconnected.includes(id) &&
      snapshot.players.some((p) => p.id === id),
  ).length
}

// ---------- spin ----------

/** The disco ball picks the category: the highlight hops through the five
 *  chips with an ease-out, then settles on the server's pick. */
export function BingoSpin({ snapshot }: { snapshot: RoomSnapshot }) {
  const { t } = useI18n()
  const target = snapshot.bingo_category_index ?? 0
  const [litSlot, setLitSlot] = useState(0)
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    let cancelled = false
    let elapsed = 0
    let slot = 0
    let timerId: number | null = null
    const totalSpinMs = 2500 // ~70% of the server's 3.5s spin window

    const tick = () => {
      if (cancelled) return
      slot = (slot + 1) % 5
      setLitSlot(slot)
      const progress = Math.min(1, elapsed / totalSpinMs)
      const interval = 70 + Math.pow(progress, 2) * 330
      elapsed += interval
      if (elapsed >= totalSpinMs) {
        setLitSlot(target)
        setSettled(true)
        return
      }
      timerId = window.setTimeout(tick, interval)
    }
    timerId = window.setTimeout(tick, 70)
    return () => {
      cancelled = true
      if (timerId !== null) window.clearTimeout(timerId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshot.bingo_round])

  return (
    <div className="space-y-4 anim-fade-in">
      <div className="card wedge-violet text-center pt-5 pb-8">
        <DiscoBall size={44} />
        <p className="text-xs uppercase tracking-wider text-muted mt-2 mb-5">
          {t.bingo.round(snapshot.bingo_round)} ·{' '}
          {settled ? t.bingo.categoryIs : t.bingo.spinning}
        </p>
        <div className="flex flex-col items-center gap-2">
          {snapshot.bingo_categories.map((catId, slot) => {
            const lit = slot === litSlot
            const style = BINGO_SLOT_STYLE[slot] ?? BINGO_SLOT_STYLE[0]
            const isFinal = settled && slot === target
            return (
              <motion.div
                key={catId}
                animate={
                  isFinal ? { scale: 1.12 } : { scale: 1, opacity: lit ? 1 : 0.4 }
                }
                transition={{ type: 'spring', stiffness: 300, damping: 18 }}
                className="relative"
              >
                {isFinal && <NoteBurst count={6} />}
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-semibold transition ${style.chip}`}
                  style={
                    lit
                      ? {
                          boxShadow: `0 0 18px color-mix(in oklab, ${style.color} 55%, transparent)`,
                        }
                      : undefined
                  }
                >
                  <span aria-hidden="true">
                    {BINGO_POOL[catId]?.icon ?? '🎵'}
                  </span>
                  {bingoCategoryLabel(catId, t)}
                </span>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ---------- answering ----------

export function BingoAnswering({
  snapshot,
  myId,
  onAnswer,
}: {
  snapshot: RoomSnapshot
  myId: string | null
  onAnswer: (value: string) => void
}) {
  const { t } = useI18n()
  const catIdx = snapshot.bingo_category_index ?? 0
  const catId = snapshot.bingo_categories[catIdx] ?? 'year4'
  const info = BINGO_POOL[catId] ?? BINGO_POOL.year4
  const participating = myId !== null && snapshot.turn_order.includes(myId)
  const couchSilent =
    snapshot.audio_mode === 'couch' && snapshot.host_id !== myId
  const myCard = (myId && snapshot.bingo_cards[myId]) || null
  const myMarks = (myId && snapshot.bingo_marks[myId]) || []

  return (
    <div className="space-y-4 anim-fade-in">
      <div className="card wedge-pink">
        <div className="flex items-center justify-center gap-2.5 text-muted text-xs uppercase tracking-wider">
          <EqBars />
          {t.nowPlaying}
          <EqBars />
        </div>
        <div className="flex justify-center mt-3">
          <CategoryPill categoryId={catId} slot={catIdx} big />
        </div>
        <p className="text-center text-lg font-bold mt-3">
          {promptFor(catId, t, snapshot.bingo_prev_title, snapshot.bingo_prev_year)}
        </p>

        {participating ? (
          <div className="mt-4">
            <AnswerWidget
              key={snapshot.bingo_round}
              kind={info.kind}
              pivot={info.pivot ?? 2000}
              onSubmit={onAnswer}
            />
          </div>
        ) : (
          <p className="text-center text-muted text-sm mt-4">
            {t.spectatorBadge}
          </p>
        )}

        <p className="text-center text-xs text-muted mt-4">
          {t.bingo.answeredCount(
            snapshot.bingo_answered.length,
            activeCount(snapshot),
          )}
        </p>
        <div className="mt-3">
          <CountdownBar deadlineMs={snapshot.bingo_deadline_ms} />
        </div>
        {couchSilent && (
          <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-muted">
            <CouchIcon /> {t.audioOnHost}
          </p>
        )}
      </div>

      {myCard && (
        <div className="card">
          <p className="text-xs uppercase tracking-wider text-muted mb-3">
            {t.bingo.yourCard}
          </p>
          <div className="max-w-[260px] mx-auto">
            <BingoCardGrid card={myCard} marks={myMarks} />
          </div>
        </div>
      )}
    </div>
  )
}

function promptFor(
  catId: string,
  t: Messages,
  prevTitle: string | null = null,
  prevYear: number | null = null,
): string {
  const info = BINGO_POOL[catId]
  if (!info) return ''
  switch (info.kind) {
    case 'year_range':
      return t.bingo.promptYear(info.tolerance ?? 2)
    case 'exact_year':
      return t.bingo.promptExact
    case 'decade':
      return t.bingo.promptDecade
    case 'before_year':
      return t.bingo.promptBefore(info.pivot ?? 2000)
    case 'artist':
      return t.bingo.promptArtist
    case 'title':
      return t.bingo.promptTitle
    case 'any_text':
      return t.bingo.promptAny
    case 'vs_prev':
      return prevTitle !== null && prevYear !== null
        ? t.bingo.promptPrev(prevTitle, prevYear)
        : t.bingo.promptPrevGeneric
    case 'closest_year':
      return t.bingo.promptClosest
  }
}

const DECADES = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]

function AnswerWidget({
  kind,
  pivot,
  onSubmit,
}: {
  kind: (typeof BINGO_POOL)[string]['kind']
  pivot: number
  onSubmit: (value: string) => void
}) {
  const { t } = useI18n()
  const [value, setValue] = useState('')
  const [sent, setSent] = useState<string | null>(null)

  const submit = (v: string) => {
    const trimmed = v.trim()
    if (!trimmed) return
    setSent(trimmed)
    onSubmit(trimmed)
  }

  if (kind === 'before_year' || kind === 'vs_prev') {
    const sides =
      kind === 'before_year'
        ? (['before', 'after'] as const)
        : (['older', 'newer'] as const)
    const labelFor = (side: string) => {
      if (side === 'before') return t.bingo.beforeBtn(pivot)
      if (side === 'after') return t.bingo.afterBtn(pivot)
      if (side === 'older') return t.bingo.olderBtn
      return t.bingo.newerBtn
    }
    return (
      <div className="space-y-2.5">
        <div className="grid grid-cols-2 gap-2">
          {sides.map((side) => {
            const label = labelFor(side)
            const on = sent === side
            return (
              <button
                key={side}
                type="button"
                onClick={() => submit(side)}
                aria-pressed={on}
                className={
                  'rounded-xl border px-3 py-3.5 font-display font-bold transition active:scale-[0.97] ' +
                  (on
                    ? 'border-neon-pink/70 bg-neon-pink/15 text-neon-pink shadow-[0_0_14px_color-mix(in_oklab,var(--color-neon-pink)_35%,transparent)]'
                    : 'border-border bg-surface-2 hover:border-neon-pink/50')
                }
              >
                {label}
              </button>
            )
          })}
        </div>
        {sent && <SubmittedNote />}
      </div>
    )
  }

  if (kind === 'decade') {
    return (
      <div className="space-y-2.5">
        <div className="grid grid-cols-4 gap-1.5">
          {DECADES.map((d) => {
            const on = sent === String(d)
            return (
              <button
                key={d}
                type="button"
                onClick={() => submit(String(d))}
                aria-pressed={on}
                className={
                  'rounded-lg border px-1 py-2.5 font-display font-bold text-sm tabular-nums transition active:scale-[0.96] ' +
                  (on
                    ? 'border-neon-pink/70 bg-neon-pink/15 text-neon-pink shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-pink)_35%,transparent)]'
                    : 'border-border bg-surface-2 hover:border-neon-pink/50')
                }
              >
                {t.bingo.decadeName(d)}
              </button>
            )
          })}
        </div>
        {sent && <SubmittedNote />}
      </div>
    )
  }

  const numeric =
    kind === 'year_range' || kind === 'exact_year' || kind === 'closest_year'
  return (
    <form
      className="space-y-2.5"
      onSubmit={(e) => {
        e.preventDefault()
        submit(value)
      }}
    >
      <div className="flex gap-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          type={numeric ? 'number' : 'text'}
          inputMode={numeric ? 'numeric' : 'text'}
          maxLength={numeric ? 4 : 60}
          placeholder={numeric ? t.bingo.yearPlaceholder : t.bingo.textPlaceholder}
          autoComplete="off"
          autoCorrect="off"
          className="input-base flex-1 min-w-0 text-center text-lg font-display tabular-nums"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          className="btn-primary px-4 shrink-0"
        >
          {t.bingo.submit}
        </button>
      </div>
      {sent && <SubmittedNote />}
    </form>
  )
}

function SubmittedNote() {
  const { t } = useI18n()
  return (
    <p className="text-center text-xs text-neon-green anim-fade-in">
      ✓ {t.bingo.submitted}
    </p>
  )
}

// ---------- reveal + marking ----------

export function BingoReveal({
  snapshot,
  myId,
  onMark,
  onErase,
}: {
  snapshot: RoomSnapshot
  myId: string | null
  onMark: (cell: number) => void
  onErase: (targetId: string | null, cell: number | null) => void
}) {
  const { t } = useI18n()
  const result = snapshot.last_bingo_result
  if (!result) return null
  const catId = snapshot.bingo_categories[result.category_index] ?? 'year4'
  const iMark = myId !== null && snapshot.bingo_mark_pending.includes(myId)
  const iErase = myId !== null && snapshot.bingo_erase_pending.includes(myId)
  const waitingOn =
    snapshot.bingo_mark_pending.length + snapshot.bingo_erase_pending.length
  const myResult = result.results.find((r) => r.player_id === myId)
  const myCard = (myId && snapshot.bingo_cards[myId]) || null
  const myMarks = (myId && snapshot.bingo_marks[myId]) || []
  const others = snapshot.turn_order
    .map((id) => snapshot.players.find((p) => p.id === id))
    .filter((p): p is NonNullable<typeof p> => p != null && p.id !== myId)

  return (
    <div className="space-y-4 anim-fade-in">
      {/* the resolved track + everyone's answers */}
      <div
        className={
          'card text-center space-y-3' +
          (myResult?.correct ? ' wedge-green' : '')
        }
      >
        <div className="flex items-center justify-center gap-3">
          {result.card.artwork_url ? (
            <img
              src={result.card.artwork_url}
              alt={t.coverAlt(result.card.title)}
              className="w-16 h-16 rounded-lg shadow-xl anim-flip-in shrink-0"
            />
          ) : (
            <div className="w-16 h-16 rounded-lg bg-surface-2 border border-border shrink-0" />
          )}
          <div className="min-w-0 text-left">
            <p className="text-[10px] uppercase tracking-wider text-muted">
              {t.bingo.itWas}
            </p>
            <p className="font-bold truncate">{result.card.title}</p>
            <p className="text-sm text-muted truncate">{result.card.artist}</p>
          </div>
          <motion.p
            initial={{ scale: 0.2, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 260, damping: 14, delay: 0.15 }}
            className="font-display text-4xl font-bold tabular-nums text-accent drop-shadow-[0_0_14px_color-mix(in_oklab,var(--color-accent)_55%,transparent)] shrink-0"
          >
            {result.card.year}
          </motion.p>
        </div>
        <div>
          <CategoryPill categoryId={catId} slot={result.category_index} />
        </div>

        <div className="space-y-1.5 text-left">
          {result.results.map((r) => {
            const player = snapshot.players.find((p) => p.id === r.player_id)
            if (!player) return null
            return (
              <div
                key={r.player_id}
                className={
                  'flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 ' +
                  (r.correct ? 'bg-neon-green/10' : 'bg-surface-2/60')
                }
              >
                <Avatar
                  name={player.name}
                  avatar={player.avatar}
                  isBot={player.is_bot}
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium truncate">
                    {player.name}
                  </span>
                  <span className="block text-xs text-muted truncate">
                    {displayAnswer(r.answer, catId, t)}
                  </span>
                </span>
                {r.exact && (
                  <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider text-neon-yellow border border-neon-yellow/50 rounded-full px-1.5 py-px">
                    {t.bingo.exactBadge}
                  </span>
                )}
                <span
                  className={
                    'shrink-0 text-xs font-bold ' +
                    (r.correct ? 'text-neon-green' : 'text-red-400')
                  }
                >
                  {r.correct ? `✓ ${t.bingo.correctBadge}` : `✗ ${t.bingo.wrongBadge}`}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* my card — clickable while I owe a mark */}
      {myCard && (
        <div className={'card' + (iMark ? ' wedge-cyan' : '')}>
          <p className="text-xs uppercase tracking-wider text-muted mb-1">
            {t.bingo.yourCard}
          </p>
          {iMark && (
            <p className="text-sm font-bold mb-2">{t.bingo.markPrompt}</p>
          )}
          <div className="max-w-[280px] mx-auto">
            <BingoCardGrid
              card={myCard}
              marks={myMarks}
              activeSlot={result.category_index}
              selectable={iMark ? 'mark' : 'none'}
              onCellClick={iMark ? onMark : undefined}
              cellAria={t.bingo.cellAria}
            />
          </div>
          {!iMark && waitingOn > 0 && (
            <p className="text-center text-xs text-muted mt-3">
              {t.bingo.markWaiting(waitingOn)}
            </p>
          )}
          {snapshot.bingo_deadline_ms !== null && (
            <div className="mt-3">
              <CountdownBar deadlineMs={snapshot.bingo_deadline_ms} />
            </div>
          )}
        </div>
      )}

      {/* opponents' cards — targets while I hold an erase */}
      {others.length > 0 && (
        <div className={'card' + (iErase ? ' wedge-yellow anim-steal-pulse' : '')}>
          {iErase && (
            <div className="mb-3">
              <p className="text-sm font-bold">💥 {t.bingo.erasePrompt}</p>
              <button
                type="button"
                onClick={() => onErase(null, null)}
                className="btn-secondary w-full mt-2 py-2 text-sm"
              >
                {t.bingo.erasePass}
              </button>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            {others.map((p) => {
              const card = snapshot.bingo_cards[p.id]
              if (!card) return null
              const marks = snapshot.bingo_marks[p.id] ?? []
              return (
                <div key={p.id}>
                  <p className="flex items-center gap-1.5 text-xs text-muted mb-1.5 min-w-0">
                    <Avatar name={p.name} avatar={p.avatar} isBot={p.is_bot} />
                    <span className="truncate">{p.name}</span>
                    <span className="ml-auto font-mono font-bold tabular-nums shrink-0">
                      {marks.length}
                    </span>
                  </p>
                  <BingoCardGrid
                    card={card}
                    marks={marks}
                    selectable={iErase && marks.length > 0 ? 'erase' : 'none'}
                    onCellClick={
                      iErase ? (cell) => onErase(p.id, cell) : undefined
                    }
                    cellAria={t.bingo.cellAria}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function displayAnswer(answer: string, catId: string, t: Messages): string {
  if (!answer) return '—'
  const info = BINGO_POOL[catId]
  if (info?.kind === 'before_year') {
    if (answer === 'before') return t.bingo.beforeBtn(info.pivot ?? 2000)
    if (answer === 'after') return t.bingo.afterBtn(info.pivot ?? 2000)
  }
  if (info?.kind === 'vs_prev') {
    if (answer === 'older') return t.bingo.olderBtn
    if (answer === 'newer') return t.bingo.newerBtn
  }
  if (info?.kind === 'decade') {
    const n = parseInt(answer, 10)
    if (Number.isFinite(n)) return t.bingo.decadeName(n)
  }
  return answer
}
