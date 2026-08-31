// The lobby, rebuilt as a stage (2026-07 neon redesign): neon room-code sign,
// dance floor with the players, mode tiles, a compact settings-summary chip
// row (the full settings live in a bottom sheet) and the song pool as a
// collapsed ticker card. All game logic stays in Room/the server.
import { useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'motion/react'
import Dancefloor from './Dancefloor'
import { BINGO_SLOT_STYLE, bingoCategoryLabel } from './bingo'
import { useI18n, type Messages } from './i18n'
import type { AudioMode, ExtraTrackSummary, GameMode, Player } from './types'
import SongPool from './SongPool'
import {
  Checkbox,
  CouchIcon,
  GlobeIcon,
  InviteQr,
  NumberStepper,
  SettingRow,
} from './ui'

export default function Lobby({
  code,
  players,
  hostId,
  myId,
  isHost,
  playerCount,
  cardTarget,
  categoryFilter,
  availableCategories,
  categoryCounts,
  effectivePoolSize,
  extraTracksTotal,
  perPlayerCap,
  yourExtraTracks,
  onlyPlayerAdded,
  audioMode,
  stealEnabled,
  isSingleplayer,
  snippetDuration,
  placingSeconds,
  stealSeconds,
  startingCards,
  gameMode,
  bingoCategories,
  bingoAnswerSeconds,
  onStart,
  onKick,
  onSetAvatar,
  onSetGameMode,
  onSetBingoCategories,
  onSetBingoAnswerSeconds,
  onSetCardTarget,
  onSetSongsPerPlayer,
  onSetAudioMode,
  onSetStealEnabled,
  onSetSnippetDuration,
  onSetPlacingSeconds,
  onSetStealSeconds,
  onSetStartingCards,
  onSetCategoryFilter,
  onSetOnlyPlayerAdded,
  onAddSong,
  onRemoveSong,
  onSetSongCategory,
  onAddBot,
}: {
  code: string
  players: Player[]
  hostId: string | null
  myId: string | null
  isHost: boolean
  playerCount: number
  cardTarget: number
  categoryFilter: string[]
  availableCategories: string[]
  categoryCounts: Record<string, number>
  effectivePoolSize: number
  extraTracksTotal: number
  perPlayerCap: number
  yourExtraTracks: ExtraTrackSummary[]
  onlyPlayerAdded: boolean
  audioMode: AudioMode
  stealEnabled: boolean
  isSingleplayer: boolean
  snippetDuration: number
  placingSeconds: number
  stealSeconds: number
  startingCards: number
  gameMode: GameMode
  bingoCategories: string[]
  bingoAnswerSeconds: number
  onStart: () => void
  onKick: (targetId: string) => void
  onSetAvatar: (avatar: string) => void
  onSetGameMode: (mode: GameMode) => void
  onSetBingoCategories: (categories: string[]) => void
  onSetBingoAnswerSeconds: (n: number) => void
  onSetCardTarget: (n: number) => void
  onSetSongsPerPlayer: (n: number) => void
  onSetAudioMode: (mode: AudioMode) => void
  onSetStealEnabled: (enabled: boolean) => void
  onSetSnippetDuration: (n: number) => void
  onSetPlacingSeconds: (n: number) => void
  onSetStealSeconds: (n: number) => void
  onSetStartingCards: (n: number) => void
  onSetCategoryFilter: (categories: string[]) => void
  onSetOnlyPlayerAdded: (only: boolean) => void
  onAddSong: (trackId: string) => void
  onRemoveSong: (trackId: string) => void
  onSetSongCategory: (trackId: string, category: string) => void
  onAddBot: (difficulty: string) => void
}) {
  const { t } = useI18n()
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <div className="space-y-4">
      {!isSingleplayer && <NeonSign code={code} />}

      <Dancefloor
        code={code}
        players={players}
        hostId={hostId}
        myId={myId}
        isHost={isHost}
        isSingleplayer={isSingleplayer}
        onKick={onKick}
        onSetAvatar={onSetAvatar}
      />

      <ModeTiles mode={gameMode} isHost={isHost} onSetMode={onSetGameMode} />

      <SummaryChips
        cardTarget={cardTarget}
        categoryFilter={categoryFilter}
        snippetDuration={snippetDuration}
        audioMode={audioMode}
        isSingleplayer={isSingleplayer}
        gameMode={gameMode}
        bingoAnswerSeconds={bingoAnswerSeconds}
        onOpenSettings={() => setSheetOpen(true)}
      />

      <SongPoolCard
        extraTracksTotal={extraTracksTotal}
        perPlayerCap={perPlayerCap}
        unlimited={isSingleplayer}
        yourTracks={yourExtraTracks}
        isHost={isHost}
        onlyPlayerAdded={onlyPlayerAdded}
        onSetOnlyPlayerAdded={onSetOnlyPlayerAdded}
        onAdd={onAddSong}
        onRemove={onRemoveSong}
        onSetCategory={onSetSongCategory}
      />

      {isHost ? (
        <button
          onClick={onStart}
          disabled={playerCount < 1}
          className="btn-primary w-full text-base"
        >
          {t.startGame}
        </button>
      ) : (
        <p className="text-center text-muted text-sm">
          {t.waitingHostStartGame}
        </p>
      )}

      <SettingsSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        isHost={isHost}
        isSingleplayer={isSingleplayer}
        cardTarget={cardTarget}
        startingCards={startingCards}
        categoryFilter={categoryFilter}
        availableCategories={availableCategories}
        categoryCounts={categoryCounts}
        effectivePoolSize={effectivePoolSize}
        onlyPlayerAdded={onlyPlayerAdded}
        audioMode={audioMode}
        stealEnabled={stealEnabled}
        snippetDuration={snippetDuration}
        placingSeconds={placingSeconds}
        stealSeconds={stealSeconds}
        perPlayerCap={perPlayerCap}
        gameMode={gameMode}
        bingoCategories={bingoCategories}
        bingoAnswerSeconds={bingoAnswerSeconds}
        onSetBingoCategories={onSetBingoCategories}
        onSetBingoAnswerSeconds={onSetBingoAnswerSeconds}
        onSetCardTarget={onSetCardTarget}
        onSetStartingCards={onSetStartingCards}
        onSetCategoryFilter={onSetCategoryFilter}
        onSetAudioMode={onSetAudioMode}
        onSetStealEnabled={onSetStealEnabled}
        onSetSnippetDuration={onSetSnippetDuration}
        onSetPlacingSeconds={onSetPlacingSeconds}
        onSetStealSeconds={onSetStealSeconds}
        onSetSongsPerPlayer={onSetSongsPerPlayer}
        onAddBot={onAddBot}
      />
    </div>
  )
}

/** The room code as a neon sign — tap to copy the invite link. */
function NeonSign({ code }: { code: string }) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)

  const copy = () => {
    const url = `${window.location.origin}/r/${code}`
    navigator.clipboard
      ?.writeText(url)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1600)
      })
      .catch(() => {})
  }

  return (
    <div className="text-center">
      <p className="text-[10px] uppercase tracking-[0.22em] text-muted">
        {copied ? (
          <span className="text-accent">{t.copied}</span>
        ) : (
          t.roomCodeLabel
        )}
      </p>
      <button
        type="button"
        onClick={copy}
        title={t.copyInvite}
        aria-label={t.copyInvite}
        className="neon-sign-code font-display text-4xl font-bold tracking-[0.26em] pl-[0.26em] mt-0.5 anim-flicker cursor-pointer"
      >
        {code}
      </button>
      <div className="mt-2.5">
        <InviteQr code={code} variant="chip" />
      </div>
    </div>
  )
}

/** Game-mode picker: Classic (orange) vs Bingo (cyan). Host taps to switch;
 *  everyone else sees which one is lit. */
function ModeTiles({
  mode,
  isHost,
  onSetMode,
}: {
  mode: GameMode
  isHost: boolean
  onSetMode: (mode: GameMode) => void
}) {
  const { t } = useI18n()
  const tiles: {
    key: GameMode
    icon: string
    label: string
    sub: string
    onCls: string
  }[] = [
    {
      key: 'classic',
      icon: '💿',
      label: t.modeClassic,
      sub: t.modeClassicSub,
      onCls:
        'border-accent/60 shadow-[0_0_0_1px_color-mix(in_oklab,var(--color-accent)_40%,transparent),0_0_22px_-2px_color-mix(in_oklab,var(--color-accent)_45%,transparent)]',
    },
    {
      key: 'bingo',
      icon: '🪩',
      label: t.modeBingo,
      sub: t.modeBingoSub,
      onCls:
        'border-neon-cyan/60 shadow-[0_0_0_1px_color-mix(in_oklab,var(--color-neon-cyan)_40%,transparent),0_0_22px_-2px_color-mix(in_oklab,var(--color-neon-cyan)_45%,transparent)]',
    },
  ]
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {tiles.map((tile) => {
        const on = mode === tile.key
        const cls =
          'rounded-2xl border bg-surface px-3.5 py-3 text-left transition ' +
          (on
            ? tile.onCls
            : 'border-border opacity-60' +
              (isHost ? ' hover:opacity-90 cursor-pointer' : ''))
        const inner = (
          <>
            <span className="text-xl block mb-1" aria-hidden="true">
              {tile.icon}
            </span>
            <p className="font-display font-bold leading-tight">{tile.label}</p>
            <p className="text-xs text-muted mt-0.5">{tile.sub}</p>
          </>
        )
        if (!isHost) {
          return (
            <div key={tile.key} className={cls}>
              {inner}
            </div>
          )
        }
        return (
          <button
            key={tile.key}
            type="button"
            onClick={() => onSetMode(tile.key)}
            aria-pressed={on}
            className={cls}
          >
            {inner}
          </button>
        )
      })}
    </div>
  )
}

function SummaryChips({
  cardTarget,
  categoryFilter,
  snippetDuration,
  audioMode,
  isSingleplayer,
  gameMode,
  bingoAnswerSeconds,
  onOpenSettings,
}: {
  cardTarget: number
  categoryFilter: string[]
  snippetDuration: number
  audioMode: AudioMode
  isSingleplayer: boolean
  gameMode: GameMode
  bingoAnswerSeconds: number
  onOpenSettings: () => void
}) {
  const { t } = useI18n()
  const bingo = gameMode === 'bingo'
  const cats = [
    categoryFilter.includes('music') ? '🎵' : null,
    categoryFilter.includes('film_tv') ? '🎬' : null,
  ]
    .filter(Boolean)
    .join(' + ')

  const chip =
    'inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-muted'

  return (
    <div className="flex flex-wrap items-center justify-center gap-1.5">
      {bingo ? (
        <span className={chip}>🪩 {t.modeBingo}</span>
      ) : (
        <span className={chip}>🏆 {t.chipCards(cardTarget)}</span>
      )}
      {cats && <span className={chip}>{cats}</span>}
      <span className={chip}>⏱ {bingo ? bingoAnswerSeconds : snippetDuration}s</span>
      {!isSingleplayer && (
        <span className={chip}>
          {audioMode === 'couch' ? (
            <>
              <CouchIcon /> {t.audioCouch}
            </>
          ) : (
            <>
              <GlobeIcon /> {t.audioOnline}
            </>
          )}
        </span>
      )}
      <button
        type="button"
        onClick={onOpenSettings}
        className="inline-flex items-center gap-1 rounded-full border border-neon-violet/50 bg-surface px-2.5 py-1 text-xs font-semibold text-neon-violet transition hover:shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-violet)_35%,transparent)]"
      >
        ⚙️ {t.settingsChip}
      </button>
    </div>
  )
}

/** Song pool as a collapsed card: status + marquee of your contributions;
 *  the full search/manage UI (SongPool) expands on demand. */
function SongPoolCard({
  extraTracksTotal,
  perPlayerCap,
  unlimited,
  yourTracks,
  isHost,
  onlyPlayerAdded,
  onSetOnlyPlayerAdded,
  onAdd,
  onRemove,
  onSetCategory,
}: {
  extraTracksTotal: number
  perPlayerCap: number
  unlimited: boolean
  yourTracks: ExtraTrackSummary[]
  isHost: boolean
  onlyPlayerAdded: boolean
  onSetOnlyPlayerAdded: (only: boolean) => void
  onAdd: (trackId: string) => void
  onRemove: (trackId: string) => void
  onSetCategory: (trackId: string, category: string) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const disabled = !unlimited && perPlayerCap === 0

  if (open) {
    return (
      <section className="card wedge-pink">
        <SongPool
          extraTracksTotal={extraTracksTotal}
          perPlayerCap={perPlayerCap}
          unlimited={unlimited}
          yourTracks={yourTracks}
          isHost={isHost}
          onlyPlayerAdded={onlyPlayerAdded}
          onSetOnlyPlayerAdded={onSetOnlyPlayerAdded}
          onAdd={onAdd}
          onRemove={onRemove}
          onSetCategory={onSetCategory}
        />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="w-full mt-3 text-xs text-muted hover:text-fg transition"
        >
          {t.hideSongSearch}
        </button>
      </section>
    )
  }

  return (
    <section className="card wedge-pink">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-muted">
          {t.songPool}
        </h3>
        <span className="text-xs text-muted">
          {unlimited
            ? t.poolStatsUnlimited(extraTracksTotal, yourTracks.length)
            : t.poolStats(extraTracksTotal, yourTracks.length, perPlayerCap)}
        </span>
      </div>
      {yourTracks.length >= 2 && (
        <div className="ticker-mask mt-3" aria-hidden="true">
          <div className="ticker-run text-xs text-muted">
            {[...yourTracks, ...yourTracks].map((tr, i) => (
              <span key={`${tr.track_id}-${i}`}>
                💿 {tr.title} — {tr.artist}
              </span>
            ))}
          </div>
        </div>
      )}
      {disabled ? (
        <p className="text-xs text-muted mt-3">{t.contributionsDisabled}</p>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="btn-secondary w-full mt-3 py-2.5 text-sm"
        >
          ＋ {t.addSongCta}
        </button>
      )}
    </section>
  )
}

/** All host knobs, tucked into a bottom sheet (read-only for non-hosts). */
function SettingsSheet({
  open,
  onClose,
  isHost,
  isSingleplayer,
  cardTarget,
  startingCards,
  categoryFilter,
  availableCategories,
  categoryCounts,
  effectivePoolSize,
  onlyPlayerAdded,
  audioMode,
  stealEnabled,
  snippetDuration,
  placingSeconds,
  stealSeconds,
  perPlayerCap,
  gameMode,
  bingoCategories,
  bingoAnswerSeconds,
  onSetBingoCategories,
  onSetBingoAnswerSeconds,
  onSetCardTarget,
  onSetStartingCards,
  onSetCategoryFilter,
  onSetAudioMode,
  onSetStealEnabled,
  onSetSnippetDuration,
  onSetPlacingSeconds,
  onSetStealSeconds,
  onSetSongsPerPlayer,
  onAddBot,
}: {
  open: boolean
  onClose: () => void
  isHost: boolean
  isSingleplayer: boolean
  cardTarget: number
  startingCards: number
  categoryFilter: string[]
  availableCategories: string[]
  categoryCounts: Record<string, number>
  effectivePoolSize: number
  onlyPlayerAdded: boolean
  audioMode: AudioMode
  stealEnabled: boolean
  snippetDuration: number
  placingSeconds: number
  stealSeconds: number
  perPlayerCap: number
  gameMode: GameMode
  bingoCategories: string[]
  bingoAnswerSeconds: number
  onSetBingoCategories: (categories: string[]) => void
  onSetBingoAnswerSeconds: (n: number) => void
  onSetCardTarget: (n: number) => void
  onSetStartingCards: (n: number) => void
  onSetCategoryFilter: (categories: string[]) => void
  onSetAudioMode: (mode: AudioMode) => void
  onSetStealEnabled: (enabled: boolean) => void
  onSetSnippetDuration: (n: number) => void
  onSetPlacingSeconds: (n: number) => void
  onSetStealSeconds: (n: number) => void
  onSetSongsPerPlayer: (n: number) => void
  onAddBot: (difficulty: string) => void
}) {
  const { t } = useI18n()

  // Portal to <body>: fixed overlays must escape transformed ancestors
  // (anim-fade-in fill-mode leaves a transform on the page container).
  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-black/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-md max-h-[85dvh] overflow-y-auto rounded-t-3xl border border-b-0 border-neon-violet/40 bg-surface px-5 pb-6 pt-3 shadow-[0_0_34px_-4px_color-mix(in_oklab,var(--color-neon-violet)_50%,transparent)]"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            role="dialog"
            aria-modal="true"
            aria-label={t.gameSettings}
          >
            <div className="w-11 h-1 rounded-full bg-border mx-auto mb-4" />
            <h3 className="font-display text-lg font-bold mb-4">
              {t.gameSettings}
            </h3>

            <div className="space-y-3.5">
              <SheetSection label={t.sectionGame}>
                {gameMode === 'classic' && (
                  <>
                    <SettingRow label={t.cardsToWin}>
                      {isHost ? (
                        <NumberStepper
                          value={cardTarget}
                          min={2}
                          max={30}
                          onChange={onSetCardTarget}
                          ariaLabel={t.cardsToWin}
                        />
                      ) : (
                        <span className="font-mono font-bold">{cardTarget}</span>
                      )}
                    </SettingRow>
                    <SettingRow label={t.startingCards}>
                      {isHost ? (
                        <NumberStepper
                          value={startingCards}
                          min={1}
                          max={5}
                          onChange={onSetStartingCards}
                          ariaLabel={t.startingCards}
                        />
                      ) : (
                        <span className="font-mono font-bold">
                          {startingCards}
                        </span>
                      )}
                    </SettingRow>
                  </>
                )}
                {gameMode === 'bingo' && (
                  <>
                    <div>
                      <p className="text-sm mb-1">{t.bingo.categoriesLabel}</p>
                      <p className="text-xs text-muted mb-2">{t.bingo.pickFive}</p>
                      <BingoCategoryPicker
                        selected={bingoCategories}
                        isHost={isHost}
                        onChange={onSetBingoCategories}
                      />
                    </div>
                    <SettingRow label={t.bingo.answerTime}>
                      {isHost ? (
                        <NumberStepper
                          value={bingoAnswerSeconds}
                          min={10}
                          max={60}
                          onChange={onSetBingoAnswerSeconds}
                          ariaLabel={t.bingo.answerTime}
                        />
                      ) : (
                        <span className="font-mono font-bold">
                          {bingoAnswerSeconds}s
                        </span>
                      )}
                    </SettingRow>
                  </>
                )}
                <div>
                  <p className="text-sm mb-2">{t.categoriesLabel}</p>
                  <CategoryPicker
                    available={availableCategories}
                    selected={categoryFilter}
                    counts={categoryCounts}
                    isHost={isHost}
                    onChange={onSetCategoryFilter}
                  />
                </div>
              </SheetSection>

              <SheetSection label={t.sectionSoundRules}>
                {isHost && !isSingleplayer && (
                  <div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm">{t.audioOutput}</span>
                      <AudioModeToggle value={audioMode} onChange={onSetAudioMode} />
                    </div>
                    <p className="text-xs text-muted mt-1.5">{t.audioModeHint}</p>
                  </div>
                )}
                {gameMode === 'classic' && (
                  <div>
                    <Checkbox
                      checked={stealEnabled}
                      disabled={!isHost}
                      onChange={onSetStealEnabled}
                      label={t.stealToggle}
                    />
                    <p className="text-xs text-muted mt-1.5">{t.stealHint}</p>
                  </div>
                )}
              </SheetSection>

              {gameMode === 'classic' && (
                <SheetSection label={t.timingLabel}>
                  <div className="grid grid-cols-3 gap-2">
                    <TimingStepper
                      label={t.snippetLabel}
                      value={snippetDuration}
                      min={5}
                      max={30}
                      isHost={isHost}
                      onChange={onSetSnippetDuration}
                    />
                    <TimingStepper
                      label={t.guessLabel}
                      value={placingSeconds}
                      min={5}
                      max={60}
                      isHost={isHost}
                      onChange={onSetPlacingSeconds}
                    />
                    <TimingStepper
                      label={t.stealLabel}
                      value={stealSeconds}
                      min={5}
                      max={30}
                      isHost={isHost}
                      onChange={onSetStealSeconds}
                    />
                  </div>
                </SheetSection>
              )}

              {!isSingleplayer && (
                <SheetSection label={t.songPool}>
                  <SettingRow label={t.songsPerPlayer}>
                    {isHost ? (
                      <NumberStepper
                        value={perPlayerCap}
                        min={0}
                        max={20}
                        onChange={onSetSongsPerPlayer}
                        ariaLabel={t.songsPerPlayer}
                      />
                    ) : (
                      <span className="font-mono font-bold">{perPlayerCap}</span>
                    )}
                  </SettingRow>
                </SheetSection>
              )}

              {isHost && (
                <SheetSection label={t.aiOpponents}>
                  <BotAdder onAdd={onAddBot} />
                </SheetSection>
              )}
            </div>

            <p className="text-xs text-muted text-center mt-4">
              {t.tracksInPool(effectivePoolSize)}
              {onlyPlayerAdded ? t.playerAddedOnlySuffix : ''}
            </p>

            <button
              type="button"
              onClick={onClose}
              className="btn-secondary w-full mt-4"
            >
              {t.close}
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  )
}

function SheetSection({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border border-border/70 bg-surface-2/40 p-3.5 space-y-3.5">
      <p className="text-[10px] uppercase tracking-wider font-semibold text-neon-violet">
        {label}
      </p>
      {children}
    </section>
  )
}

function BotAdder({ onAdd }: { onAdd: (difficulty: string) => void }) {
  const { t } = useI18n()
  const [difficulty, setDifficulty] = useState('medium')
  const levels: { key: string; label: string }[] = [
    { key: 'easy', label: t.botEasy },
    { key: 'medium', label: t.botMedium },
    { key: 'hard', label: t.botHard },
  ]
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-surface-2 p-0.5">
        {levels.map((l) => {
          const on = difficulty === l.key
          return (
            <button
              key={l.key}
              type="button"
              onClick={() => setDifficulty(l.key)}
              aria-pressed={on}
              className={
                'rounded-md px-2 py-1.5 text-sm font-medium transition ' +
                (on
                  ? 'bg-neon-violet text-accent-fg shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-violet)_40%,transparent)]'
                  : 'text-muted hover:text-fg')
              }
            >
              {l.label}
            </button>
          )
        })}
      </div>
      <button
        type="button"
        onClick={() => onAdd(difficulty)}
        className="btn-secondary w-full py-2 text-sm"
      >
        ＋ {t.addBot}
      </button>
    </div>
  )
}

function TimingStepper({
  label,
  value,
  min,
  max,
  isHost,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  isHost: boolean
  onChange: (n: number) => void
}) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span className="text-xs text-muted text-center">{label}</span>
      {isHost ? (
        <NumberStepper
          value={value}
          min={min}
          max={max}
          onChange={onChange}
          ariaLabel={label}
        />
      ) : (
        <span className="font-mono font-bold tabular-nums flex h-10 items-center">
          {value}s
        </span>
      )}
    </div>
  )
}

function categoryLabel(c: string, t: Messages): string {
  switch (c) {
    case 'music':
      return t.categoryMusic
    case 'film_tv':
      return t.categoryFilmTv
    default:
      return c
  }
}

function AudioModeToggle({
  value,
  onChange,
}: {
  value: AudioMode
  onChange: (mode: AudioMode) => void
}) {
  const { t } = useI18n()
  const opts = [
    { key: 'couch' as AudioMode, label: t.audioCouch, icon: <CouchIcon /> },
    { key: 'online' as AudioMode, label: t.audioOnline, icon: <GlobeIcon /> },
  ]
  return (
    <div className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {opts.map((o) => {
        const on = value === o.key
        return (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key)}
            aria-pressed={on}
            className={
              'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ' +
              (on
                ? 'bg-neon-violet text-accent-fg shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-violet)_40%,transparent)]'
                : 'text-muted hover:text-fg')
            }
          >
            {o.icon}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/** Pick 5 of the bingo-category pool; selection ORDER assigns the five board
 *  colours (like the physical board sides). Presets = the real sides A/B. */
function BingoCategoryPicker({
  selected,
  isHost,
  onChange,
}: {
  selected: string[]
  isHost: boolean
  onChange: (categories: string[]) => void
}) {
  const { t } = useI18n()
  const PRESET_BEGINNER = ['year4', 'year3', 'decade', 'year2', 'before2000']
  const PRESET_ADVANCED = ['artist', 'title', 'decade', 'year3', 'exact']
  const ALL = [
    'year1',
    'year2',
    'year3',
    'year4',
    'year5',
    'decade',
    'before1990',
    'before2000',
    'before2010',
    'exact',
    'artist',
    'title',
    'anytext',
    'prevsong',
    'closest',
  ]

  // the server only accepts exactly 5 — while re-picking, the in-between
  // state lives here and is sent the moment the 5th choice lands
  const [draft, setDraft] = useState<string[] | null>(null)
  const shown = draft ?? selected

  const commit = (next: string[]) => {
    if (next.length === 5) {
      setDraft(null)
      onChange(next)
    } else {
      setDraft(next)
    }
  }

  const toggle = (id: string) => {
    if (shown.includes(id)) {
      commit(shown.filter((c) => c !== id))
    } else if (shown.length < 5) {
      commit([...shown, id])
    }
  }

  const presetBtn = (label: string, preset: string[]) => (
    <button
      type="button"
      onClick={() => commit(preset)}
      className={
        'rounded-full border px-2.5 py-1 text-xs font-semibold transition ' +
        (shown.join() === preset.join()
          ? 'border-neon-violet/70 text-neon-violet bg-neon-violet/10'
          : 'border-border text-muted hover:text-fg')
      }
    >
      {label}
    </button>
  )

  return (
    <div className="space-y-2.5">
      {isHost && (
        <div className="flex gap-1.5">
          {presetBtn(t.bingo.presetBeginner, PRESET_BEGINNER)}
          {presetBtn(t.bingo.presetAdvanced, PRESET_ADVANCED)}
        </div>
      )}
      <div className="grid grid-cols-2 gap-1.5">
        {ALL.map((id) => {
          const slot = shown.indexOf(id)
          const on = slot >= 0
          const style = on ? BINGO_SLOT_STYLE[slot] : null
          const full = !on && shown.length >= 5
          const base =
            'rounded-lg border px-2.5 py-2 text-sm text-left transition flex items-center gap-2 select-none'
          const cls = style
            ? `${base} ${style.chip}`
            : `${base} bg-surface-2 border-border text-muted ${full ? 'opacity-40' : 'opacity-70'}`
          const inner = (
            <>
              {style && (
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{
                    background: style.color,
                    boxShadow: `0 0 8px ${style.color}`,
                  }}
                  aria-hidden="true"
                />
              )}
              <span className="font-medium">{bingoCategoryLabel(id, t)}</span>
            </>
          )
          if (!isHost) {
            return (
              <span key={id} className={cls}>
                {inner}
              </span>
            )
          }
          return (
            <button
              key={id}
              type="button"
              onClick={() => toggle(id)}
              aria-pressed={on}
              disabled={full}
              className={`${cls} ${full ? 'cursor-not-allowed' : 'cursor-pointer hover:opacity-95 active:scale-[0.98]'}`}
            >
              {inner}
            </button>
          )
        })}
      </div>
    </div>
  )
}

const CATEGORY_STYLE: Record<string, { icon: string; on: string }> = {
  music: {
    icon: '🎵',
    on: 'bg-neon-pink/15 border-neon-pink/60 text-neon-pink shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-pink)_25%,transparent)]',
  },
  film_tv: {
    icon: '🎬',
    on: 'bg-neon-cyan/15 border-neon-cyan/60 text-neon-cyan shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-cyan)_25%,transparent)]',
  },
}

function CategoryPicker({
  available,
  selected,
  counts,
  isHost,
  onChange,
}: {
  available: string[]
  selected: string[]
  counts: Record<string, number>
  isHost: boolean
  onChange: (categories: string[]) => void
}) {
  const { t } = useI18n()
  const selectedSet = new Set(selected)

  const toggle = (category: string) => {
    const next = new Set(selectedSet)
    if (next.has(category)) {
      if (next.size <= 1) return
      next.delete(category)
    } else {
      next.add(category)
    }
    onChange([...next].sort())
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {available.map((c) => {
        const isOn = selectedSet.has(c)
        const lockOn = isOn && selectedSet.size <= 1
        const count = counts[c] ?? 0
        const style = CATEGORY_STYLE[c] ?? CATEGORY_STYLE.music
        const baseClass =
          'rounded-lg border text-center py-2.5 text-sm transition select-none'
        const onClass = isOn
          ? style.on
          : 'bg-surface-2 border-border text-muted opacity-50'
        const hostInteract = isHost
          ? lockOn
            ? ' cursor-not-allowed'
            : ' cursor-pointer hover:opacity-90 active:scale-[0.97]'
          : ''

        const inner = (
          <>
            <span aria-hidden="true">{style.icon}</span>{' '}
            <span className="font-medium">{categoryLabel(c, t)}</span>
            <span className="ml-1 text-xs opacity-70">({count})</span>
          </>
        )

        if (!isHost) {
          return (
            <span key={c} className={`${baseClass} ${onClass}`}>
              {inner}
            </span>
          )
        }
        return (
          <label
            key={c}
            className={`${baseClass} ${onClass}${hostInteract}`}
          >
            <input
              type="checkbox"
              checked={isOn}
              onChange={() => toggle(c)}
              disabled={lockOn}
              className="sr-only"
            />
            {inner}
          </label>
        )
      })}
    </div>
  )
}
