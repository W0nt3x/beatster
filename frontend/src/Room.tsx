import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getStoredAvatar,
  getStoredName,
  getStoredPlayerId,
  getStoredVolume,
  roomWsUrl,
  setStoredAvatar,
  setStoredName,
  setStoredPlayerId,
  setStoredVolume,
} from './api'
import { motion } from 'motion/react'
import { DiscoBall, EqBars, NoteBurst, VinylNotes } from './fx'
import { useI18n } from './i18n'
import { navigate } from './router'
import { useUpdateAvailable } from './useUpdate'
import HowToPlay from './HowToPlay'
import AdsOverlay from './AdsOverlay'
import Lobby from './Lobby'
import ScoreStrip from './ScoreStrip'
import { applyMsg } from './applyMsg'
import { BingoAnswering, BingoReveal, BingoSpin } from './BingoGame'
import { Avatar, CouchIcon, CountdownBar, InviteQr } from './ui'
import { MysteryCard, SnippetProgress, Timeline } from './Timeline'
import type {
  AudioMode,
  ClientMsg,
  GameMode,
  PlacementResultMsg,
  Player,
  RoomSnapshot,
  ServerMsg,
} from './types'

const RECONNECT_INITIAL_MS = 500
const RECONNECT_CAP_MS = 8000
const MEDALS = ['🥇', '🥈', '🥉']

// ---- easter egg: fake-ads overlay ----
// Type these letters (no input focused) to toggle the prank for everyone else
// in the room. Change the word here if a friend ever figures it out.
const PROMO_SEQUENCE = 'godmode'

type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting'

type Props = { code: string }

export default function Room({ code }: Props) {
  const [name, setName] = useState(() => getStoredName())
  const [submittedName, setSubmittedName] = useState(getStoredName().length > 0)

  if (!submittedName) {
    return (
      <NamePrompt
        initial={name}
        onSubmit={(n) => {
          setStoredName(n)
          setName(n)
          setSubmittedName(true)
        }}
      />
    )
  }

  return <RoomConnected code={code} name={name} />
}

function NamePrompt({
  initial,
  onSubmit,
}: {
  initial: string
  onSubmit: (name: string) => void
}) {
  const { t } = useI18n()
  const [name, setName] = useState(initial)
  const trimmed = name.trim()
  return (
    <div className="min-h-full flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md anim-fade-in">
        <h1 className="font-display text-3xl font-bold text-center mb-2">
          {t.whatsYourName}
        </h1>
        <p className="text-muted text-center text-sm mb-6">{t.pickName}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (trimmed) onSubmit(trimmed)
          }}
          className="card wedge-orange space-y-3"
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
            autoFocus
            className="input-base w-full text-center text-lg"
            placeholder={t.yourName}
          />
          <button
            type="submit"
            disabled={!trimmed}
            className="btn-primary w-full"
          >
            {t.join}
          </button>
          <p className="text-center text-xs text-muted pt-1">
            <a
              href="/"
              onClick={(e) => {
                e.preventDefault()
                navigate('/')
              }}
              className="hover:text-fg transition"
            >
              {t.cancel}
            </a>
          </p>
        </form>
      </div>
    </div>
  )
}

function RoomConnected({ code, name }: { code: string; name: string }) {
  const { t } = useI18n()
  // Socket callbacks outlive renders — give them access to the current
  // translations without re-running the connection effect on language change.
  const tRef = useRef(t)
  useEffect(() => {
    tRef.current = t
  })
  const [snapshot, setSnapshot] = useState<RoomSnapshot | null>(null)
  const [myId, setMyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>('connecting')
  // set when the host kicks us — stop reconnecting and show a notice
  const [kicked, setKicked] = useState(false)
  const kickedRef = useRef(false)

  // "How to play" modal (header "?" button)
  const [helpOpen, setHelpOpen] = useState(false)

  // a newer frontend build is live — auto-reload when idle, banner mid-game
  const updateAvailable = useUpdateAvailable()
  useEffect(() => {
    if (!updateAvailable) return
    const st = snapshot?.state
    if (!st || st === 'lobby' || st === 'game_over') {
      window.location.reload()
    }
  }, [updateAvailable, snapshot?.state])

  const wsRef = useRef<WebSocket | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const [volume, setVolume] = useState<number>(getStoredVolume)
  const volumeRef = useRef(volume)
  useEffect(() => {
    volumeRef.current = volume
    setStoredVolume(volume)
    if (audioRef.current) audioRef.current.volume = volume
  }, [volume])

  // Audio is driven entirely from the snapshot (not imperatively on each
  // message): play the snippet only while listening AND only on devices that
  // should make sound. In "couch" mode that's the host's device alone (one
  // shared screen/speaker); in "online" mode it's every device. Reacting to
  // host_id / audio_mode here also means flipping the mode or migrating the
  // host takes effect immediately, and leaving listening always pauses.
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const isHost = snapshot?.host_id != null && snapshot.host_id === myId
    const shouldPlay = snapshot?.audio_mode !== 'couch' || isHost
    const url = snapshot?.current_preview_url
    const listening =
      snapshot?.state === 'hitster_listening' ||
      snapshot?.state === 'bingo_answering'
    if (listening && url && shouldPlay) {
      if (audio.src !== url) {
        audio.src = url
        audio.currentTime = 0
      }
      audio.volume = volumeRef.current
      audio.play().catch(() => setError(tRef.current.audioBlocked))
    } else {
      audio.pause()
    }
  }, [
    snapshot?.state,
    snapshot?.current_preview_url,
    snapshot?.audio_mode,
    snapshot?.host_id,
    myId,
  ])

  useEffect(() => {
    let stale = false
    let reconnectAttempt = 0
    let reconnectTimer: number | null = null

    const connect = () => {
      const ws = new WebSocket(roomWsUrl(code))
      wsRef.current = ws

      ws.onopen = () => {
        if (stale) return
        reconnectAttempt = 0
        const join: ClientMsg = {
          type: 'join',
          name,
          player_id: getStoredPlayerId(),
          avatar: getStoredAvatar(),
        }
        ws.send(JSON.stringify(join))
      }

      ws.onmessage = (e) => {
        if (stale) return
        const msg = JSON.parse(e.data) as ServerMsg

        if (msg.type === 'joined') {
          setMyId(msg.player_id)
          setStoredPlayerId(msg.player_id)
          setSnapshot(msg.snapshot)
          setConnectionStatus('connected')
          setError(null)
          return
        }

        if (msg.type === 'error') {
          setError(msg.message)
          return
        }

        // the host kicked us → stop reconnecting and show a notice
        if (
          msg.type === 'player_kicked' &&
          msg.player_id === getStoredPlayerId()
        ) {
          kickedRef.current = true
          setKicked(true)
          ws.close()
          return
        }

        setSnapshot((prev) => (prev ? applyMsg(prev, msg) : prev))

        // clear any stale "audio blocked" error on a new turn; actual playback
        // is driven reactively from the snapshot below
        if (msg.type === 'hitster_turn_changed' || msg.type === 'bingo_answering')
          setError(null)
      }

      ws.onclose = (e) => {
        if (stale || kickedRef.current) return
        if (e.code === 4404) {
          setError(tRef.current.roomNotFound(code))
          return
        }
        setConnectionStatus('reconnecting')
        const delay = Math.min(
          RECONNECT_CAP_MS,
          RECONNECT_INITIAL_MS * 2 ** reconnectAttempt,
        )
        reconnectAttempt += 1
        reconnectTimer = window.setTimeout(() => {
          if (stale) return
          connect()
        }, delay)
      }
    }

    connect()

    return () => {
      stale = true
      if (reconnectTimer !== null) clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, name])

  const send = (msg: ClientMsg) => wsRef.current?.send(JSON.stringify(msg))
  const startRound = () => send({ type: 'start_round' })
  const endGame = () => send({ type: 'end_game' })
  const rematch = () => send({ type: 'rematch' })
  const setCategoryFilter = (categories: string[]) =>
    send({ type: 'set_category_filter', categories })
  const setOnlyPlayerAdded = (only: boolean) =>
    send({ type: 'set_only_player_added', only })
  const setCardTarget = (n: number) =>
    send({ type: 'set_card_target', card_target: n })
  const setSongsPerPlayer = (n: number) =>
    send({ type: 'set_songs_per_player', songs_per_player: n })
  const setSnippetDuration = (n: number) =>
    send({ type: 'set_snippet_duration', seconds: n })
  const setPlacingSeconds = (n: number) =>
    send({ type: 'set_placing_seconds', seconds: n })
  const setStealSeconds = (n: number) =>
    send({ type: 'set_steal_seconds', seconds: n })
  const setStartingCards = (n: number) =>
    send({ type: 'set_starting_cards', count: n })
  const setAudioMode = (mode: AudioMode) =>
    send({ type: 'set_audio_mode', mode })
  const setStealEnabled = (enabled: boolean) =>
    send({ type: 'set_steal_enabled', enabled })
  const setGameMode = (mode: GameMode) => send({ type: 'set_game_mode', mode })
  const setBingoCategories = (categories: string[]) =>
    send({ type: 'set_bingo_categories', categories })
  const setBingoAnswerSeconds = (n: number) =>
    send({ type: 'set_bingo_answer_seconds', seconds: n })
  const bingoAnswer = (value: string) => send({ type: 'bingo_answer', value })
  const bingoMark = (cell: number) => send({ type: 'bingo_mark', cell })
  const bingoErase = (target_id: string | null, cell: number | null) =>
    send({ type: 'bingo_erase', target_id, cell })
  const stealPlace = (slot_index: number) =>
    send({ type: 'steal_place', slot_index })
  const placeSong = (slot_index: number) =>
    send({ type: 'place_song', slot_index })
  const addSong = (track_id: string) => send({ type: 'add_song', track_id })
  const removeSong = (track_id: string) =>
    send({ type: 'remove_song', track_id })
  const setSongCategory = (track_id: string, category: string) =>
    send({ type: 'set_song_category', track_id, category })
  const kickPlayer = (target_id: string) =>
    send({ type: 'kick_player', target_id })
  const setAvatar = (avatar: string) => {
    setStoredAvatar(avatar)
    send({ type: 'set_avatar', avatar })
  }
  const addBot = (difficulty: string) =>
    send({ type: 'add_bot', difficulty })
  const giveCard = (target_id: string) =>
    send({ type: 'give_card', target_id })
  const takeCard = (target_id: string) =>
    send({ type: 'take_card', target_id })
  const abortToLobby = () => send({ type: 'abort_to_lobby' })

  // ---- easter egg: secret key sequence toggles the fake-ads overlay ----
  const promoActiveRef = useRef(false)
  useEffect(() => {
    promoActiveRef.current = snapshot?.promo_active ?? false
  }, [snapshot?.promo_active])

  useEffect(() => {
    let buf = ''
    let timer: number | null = null
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return
      if (e.key.length !== 1) return
      buf = (buf + e.key.toLowerCase()).slice(-PROMO_SEQUENCE.length)
      if (timer) clearTimeout(timer)
      timer = window.setTimeout(() => {
        buf = ''
      }, 2000)
      if (buf === PROMO_SEQUENCE) {
        buf = ''
        wsRef.current?.send(
          JSON.stringify({
            type: 'set_promo',
            active: !promoActiveRef.current,
          }),
        )
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (timer) clearTimeout(timer)
    }
  }, [])

  if (kicked) {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-md text-center anim-fade-in">
          <p className="text-4xl mb-3" aria-hidden="true">
            👋
          </p>
          <p className="text-lg font-semibold">{t.kickedTitle}</p>
          <p className="text-muted text-sm mt-1">{t.kickedBody}</p>
          <p className="mt-5">
            <button className="btn btn-primary" onClick={() => navigate('/')}>
              {t.backToLanding}
            </button>
          </p>
        </div>
      </div>
    )
  }

  if (!snapshot) {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-md text-center anim-fade-in">
          <p className="text-muted">
            {connectionStatus === 'reconnecting'
              ? t.connectingRoom(code)
              : t.joiningRoom(code)}
          </p>
          {error && (
            <>
              <p className="text-red-400 mt-3 text-sm">{error}</p>
              <p className="mt-4">
                <a
                  href="/"
                  onClick={(e) => {
                    e.preventDefault()
                    navigate('/')
                  }}
                  className="text-accent hover:underline"
                >
                  {t.backToLanding}
                </a>
              </p>
            </>
          )}
        </div>
      </div>
    )
  }

  const isHost = snapshot.host_id !== null && snapshot.host_id === myId
  // solo vs AI: exactly one human + at least one bot → hide multiplayer-only
  // chrome (invite/QR, couch-vs-online, per-player song cap)
  const botCount = snapshot.players.filter((p) => p.is_bot).length
  const isSingleplayer =
    botCount > 0 && snapshot.players.length - botCount === 1
  // the triggerer stays ad-free; everyone else in the room gets the overlay
  const adsVisible = snapshot.promo_active && snapshot.promo_by !== myId

  return (
    <div className="min-h-full px-4 py-6 sm:py-10">
      {adsVisible && <AdsOverlay />}
      <div className="w-full max-w-md mx-auto">
        <header className="mb-5 anim-fade-in">
          <div className="text-center">
            <h1 className="font-display text-2xl font-bold tracking-tight">
              Beatster <span className="neon-text">Online</span>
            </h1>
          </div>
          {/* one compact right-aligned control group — no stray widgets */}
          <div className="mt-3 flex items-center justify-end gap-2">
            <VolumeControl volume={volume} setVolume={setVolume} />
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              aria-label={t.howToPlay.title}
              title={t.howToPlay.title}
              className="flex shrink-0 items-center justify-center w-[34px] h-[34px] rounded-full bg-surface-2 border border-neon-cyan/50 text-neon-cyan transition hover:border-neon-cyan hover:shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-cyan)_45%,transparent)]"
            >
              <span className="font-display font-bold text-base leading-none">
                ?
              </span>
            </button>
            {/* in the lobby the neon sign carries code + QR — keep the
                compact header versions for the in-game states only */}
            {!isSingleplayer && snapshot.state !== 'lobby' && (
              <InviteQr code={code} />
            )}
            {!isSingleplayer && snapshot.state !== 'lobby' && (
              <RoomCodeChip code={code} />
            )}
          </div>
        </header>

        {connectionStatus === 'reconnecting' && (
          <div className="mb-4 rounded-lg bg-amber-950/40 border border-amber-700/60 text-amber-300 px-3 py-2 text-sm flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            {t.reconnecting}
          </div>
        )}

        {updateAvailable && (
          <div className="mb-4 rounded-lg bg-accent/15 border border-accent/40 text-accent px-3 py-2 text-sm flex items-center justify-between gap-2">
            <span>{t.updateAvailable}</span>
            <button
              onClick={() => window.location.reload()}
              className="shrink-0 px-3 py-1 rounded-md bg-accent/20 hover:bg-accent/30 font-semibold transition"
            >
              {t.reloadNow}
            </button>
          </div>
        )}

        <audio ref={audioRef} />

        <HowToPlay
          open={helpOpen}
          onClose={() => setHelpOpen(false)}
          mode={snapshot.game_mode}
        />

        {/* in the lobby the players ARE the stage (Dancefloor, inside Lobby);
            the compact score strip is for the in-game states */}
        {snapshot.state !== 'lobby' && (
          <ScoreStrip
            players={snapshot.players}
            hostId={snapshot.host_id}
            cumulativeScores={snapshot.cumulative_scores}
            myId={myId}
            state={snapshot.state}
            turnOrder={snapshot.turn_order}
            finishedPlayers={snapshot.finished_players}
            currentTurnPlayerId={
              // bingo has no active player — everyone plays every round
              snapshot.state.startsWith('bingo')
                ? null
                : snapshot.current_turn_player_id
            }
            disconnected={snapshot.disconnected}
            isHost={isHost}
            onKick={kickPlayer}
            onGive={giveCard}
            onTake={takeCard}
          />
        )}

        <div className="mt-4">
          {snapshot.state === 'lobby' && (
            <Lobby
              code={code}
              players={snapshot.players}
              hostId={snapshot.host_id}
              myId={myId}
              onKick={kickPlayer}
              onSetAvatar={setAvatar}
              isHost={isHost}
              playerCount={snapshot.players.length}
              cardTarget={snapshot.card_target}
              categoryFilter={snapshot.category_filter}
              availableCategories={snapshot.available_categories}
              categoryCounts={snapshot.category_counts}
              effectivePoolSize={snapshot.effective_pool_size}
              extraTracksTotal={snapshot.extra_tracks_total}
              perPlayerCap={snapshot.per_player_cap}
              yourExtraTracks={snapshot.your_extra_tracks}
              onlyPlayerAdded={snapshot.only_player_added}
              audioMode={snapshot.audio_mode}
              stealEnabled={snapshot.steal_enabled}
              isSingleplayer={isSingleplayer}
              snippetDuration={snapshot.snippet_duration_s}
              placingSeconds={snapshot.placing_seconds}
              stealSeconds={snapshot.steal_seconds}
              startingCards={snapshot.starting_cards}
              gameMode={snapshot.game_mode}
              bingoCategories={snapshot.bingo_categories}
              bingoAnswerSeconds={snapshot.bingo_answer_seconds}
              onSetGameMode={setGameMode}
              onSetBingoCategories={setBingoCategories}
              onSetBingoAnswerSeconds={setBingoAnswerSeconds}
              onStart={startRound}
              onSetCardTarget={setCardTarget}
              onSetSongsPerPlayer={setSongsPerPlayer}
              onSetAudioMode={setAudioMode}
              onSetStealEnabled={setStealEnabled}
              onSetSnippetDuration={setSnippetDuration}
              onSetPlacingSeconds={setPlacingSeconds}
              onSetStealSeconds={setStealSeconds}
              onSetStartingCards={setStartingCards}
              onSetCategoryFilter={setCategoryFilter}
              onSetOnlyPlayerAdded={setOnlyPlayerAdded}
              onAddSong={addSong}
              onRemoveSong={removeSong}
              onSetSongCategory={setSongCategory}
              onAddBot={addBot}
            />
          )}
          {snapshot.state === 'hitster_intro' && (
            <HitsterIntro snapshot={snapshot} myId={myId} />
          )}
          {snapshot.state === 'hitster_listening' && (
            <HitsterListening
              snapshot={snapshot}
              myId={myId}
            />
          )}
          {snapshot.state === 'hitster_placing' && (
            <HitsterPlacing
              snapshot={snapshot}
              myId={myId}
              onPlace={placeSong}
            />
          )}
          {snapshot.state === 'hitster_stealing' && (
            <HitsterStealing
              snapshot={snapshot}
              myId={myId}
              onSteal={stealPlace}
            />
          )}
          {snapshot.state === 'hitster_reveal' && snapshot.last_placement_result && (
            <HitsterReveal
              result={snapshot.last_placement_result}
              snapshot={snapshot}
              isHost={isHost}
              onNext={startRound}
              onEndGame={endGame}
            />
          )}
          {snapshot.state === 'bingo_spin' && <BingoSpin snapshot={snapshot} />}
          {snapshot.state === 'bingo_answering' && (
            <BingoAnswering
              snapshot={snapshot}
              myId={myId}
              onAnswer={bingoAnswer}
            />
          )}
          {snapshot.state === 'bingo_reveal' && (
            <BingoReveal
              snapshot={snapshot}
              myId={myId}
              onMark={bingoMark}
              onErase={bingoErase}
            />
          )}
          {snapshot.state === 'game_over' && (
            <GameOver
              players={snapshot.players}
              cumulativeScores={snapshot.cumulative_scores}
              finishedPlayers={snapshot.finished_players}
              gameMode={snapshot.game_mode}
              bingoWinners={snapshot.bingo_winners}
              isHost={isHost}
              onRematch={rematch}
            />
          )}
        </div>

        {isHost &&
          snapshot.state !== 'lobby' &&
          snapshot.state !== 'game_over' && (
            <div className="mt-4">
              <button
                onClick={() => {
                  if (window.confirm(t.abortConfirm)) abortToLobby()
                }}
                className="w-full text-sm text-muted hover:text-red-400 border border-border rounded-lg px-3 py-2 transition"
              >
                {t.abortGame}
              </button>
            </div>
          )}

        {error && (
          <p className="text-red-400 text-center mt-4 text-sm">{error}</p>
        )}

        <p className="text-center text-xs text-muted mt-6">
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault()
              navigate('/')
            }}
            className="hover:text-fg transition"
          >
            {t.leaveRoom}
          </a>
        </p>
      </div>
    </div>
  )
}

function VolumeControl({
  volume,
  setVolume,
}: {
  volume: number
  setVolume: (v: number) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  // tap-outside closes the slider popover
  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  return (
    // hidden on touch devices: iOS ignores programmatic audio.volume entirely
    // and Android's hardware rocker scales media volume anyway — the slider
    // only earns its place on fine-pointer (desktop) devices
    <div className="relative hidden [@media(pointer:fine)]:block" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={t.volume}
        title={t.volume}
        aria-expanded={open}
        className={
          'flex shrink-0 items-center justify-center w-[34px] h-[34px] rounded-full bg-surface-2 border transition ' +
          (open
            ? 'border-neon-green text-neon-green shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-green)_45%,transparent)]'
            : 'border-border text-muted hover:border-neon-green hover:text-neon-green')
        }
      >
        <SpeakerIcon />
      </button>
      {open && (
        /* opens sideways into the empty header space — dropping down would
           cover the neon sign (lobby) or the score strip (in-game) */
        <div className="absolute right-full top-1/2 -translate-y-1/2 mr-2 z-30 w-40 flex items-center rounded-full border border-neon-green/40 bg-surface px-3.5 py-2.5 shadow-[0_0_22px_-4px_color-mix(in_oklab,var(--color-neon-green)_40%,transparent),0_10px_26px_rgb(0_0_0/0.45)] anim-pop-in">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={(e) => setVolume(parseFloat(e.target.value))}
            aria-label={t.volume}
            className="neon-range"
          />
        </div>
      )}
    </div>
  )
}

function HitsterIntro({
  snapshot,
  myId,
}: {
  snapshot: RoomSnapshot
  myId: string | null
}) {
  const { t } = useI18n()
  const firstId =
    snapshot.current_turn_player_id ?? snapshot.turn_order[0] ?? null
  const firstName =
    snapshot.players.find((p) => p.id === firstId)?.name ?? '?'
  const isYou = myId !== null && firstId === myId

  const names = snapshot.turn_order
    .map((id) => snapshot.players.find((p) => p.id === id)?.name ?? '?')
    .filter((n) => n.length > 0)

  const [shownName, setShownName] = useState<string>(names[0] ?? firstName)
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    if (names.length === 0) {
      setShownName(firstName)
      setSettled(true)
      return
    }
    let cancelled = false
    let idx = Math.floor(Math.random() * names.length)
    let elapsed = 0
    const totalSpinMs = 2400 // ~80% of the server's 4s intro window
    let timerId: number | null = null

    const tick = () => {
      if (cancelled) return
      idx = (idx + 1) % names.length
      setShownName(names[idx])
      // ease-out: interval grows from ~50ms to ~360ms over the spin
      const t = Math.min(1, elapsed / totalSpinMs)
      const interval = 50 + Math.pow(t, 2) * 310
      elapsed += interval
      if (elapsed >= totalSpinMs) {
        setShownName(firstName)
        setSettled(true)
        return
      }
      timerId = window.setTimeout(tick, interval)
    }
    timerId = window.setTimeout(tick, 50)
    return () => {
      cancelled = true
      if (timerId !== null) window.clearTimeout(timerId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstId])

  return (
    <div className="space-y-4 anim-fade-in">
      <div className="card wedge-violet text-center pt-5 pb-12">
        <DiscoBall size={44} />
        <p className="text-xs uppercase tracking-wider text-muted mt-2 mb-6">
          {t.pickingFirst}
        </p>
        {settled ? (
          <motion.p
            key="settled"
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 16 }}
            className="relative font-display text-5xl sm:text-6xl font-bold tabular-nums neon-text"
          >
            <NoteBurst count={8} />
            {shownName || ' '}
          </motion.p>
        ) : (
          <p className="font-display text-5xl sm:text-6xl font-bold tabular-nums text-fg">
            {shownName || ' '}
          </p>
        )}
        {settled && (
          <p className="text-muted text-sm mt-4 anim-fade-in">
            {isYou ? t.youStartGame : t.startsGame}
          </p>
        )}
      </div>
    </div>
  )
}

function HitsterListening({
  snapshot,
  myId,
}: {
  snapshot: RoomSnapshot
  myId: string | null
}) {
  const { t } = useI18n()
  const activeId = snapshot.current_turn_player_id
  const activePlayer = snapshot.players.find((p) => p.id === activeId)
  const isYourTurn = myId !== null && activeId === myId
  const hand = (activeId && snapshot.hands[activeId]) || []
  // couch mode: only the host's device plays — tell everyone else why it's quiet
  const couchSilent =
    snapshot.audio_mode === 'couch' && snapshot.host_id !== myId

  return (
    <div className="space-y-4 anim-fade-in">
      <div className="card wedge-pink text-center py-8">
        <div className="flex items-center justify-center gap-2.5 text-muted text-xs uppercase tracking-wider">
          <EqBars />
          {t.nowPlaying}
          <EqBars />
        </div>
        <div className="flex justify-center my-5">
          <VinylNotes size={150} />
        </div>
        <p className="text-2xl font-bold">
          {isYourTurn ? t.yourTurn : t.playersTurn(activePlayer?.name ?? '?')}
        </p>
        <p className="text-muted text-sm mt-1">
          {t.snippetSeconds(snapshot.snippet_duration_s ?? 15)}
        </p>
        <div className="mt-5 max-w-xs mx-auto">
          <SnippetProgress
            key={snapshot.current_preview_url ?? 'snippet'}
            durationS={snapshot.snippet_duration_s ?? 15}
          />
        </div>
        {couchSilent && (
          <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-muted">
            <CouchIcon /> {t.audioOnHost}
          </p>
        )}
      </div>

      <div className="card">
        <p className="text-xs uppercase tracking-wider text-muted mb-3">
          {isYourTurn
            ? t.yourTimeline
            : t.playersTimeline(activePlayer?.name ?? '?')}
        </p>
        <Timeline cards={hand} onSlotClick={null} />
      </div>
    </div>
  )
}

function HitsterPlacing({
  snapshot,
  myId,
  onPlace,
}: {
  snapshot: RoomSnapshot
  myId: string | null
  onPlace: (slot: number) => void
}) {
  const { t } = useI18n()
  const activeId = snapshot.current_turn_player_id
  const activePlayer = snapshot.players.find((p) => p.id === activeId)
  const isYourTurn = myId !== null && activeId === myId
  const hand = (activeId && snapshot.hands[activeId]) || []

  return (
    <div className="space-y-4 anim-fade-in">
      <div className="card wedge-cyan">
        <div className="flex items-center gap-4 mb-5">
          <div className="anim-float">
            <MysteryCard size="sm" />
          </div>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-muted">
              {t.placeSong}
            </p>
            <p className="text-lg font-bold mt-1">
              {isYourTurn
                ? t.pickWhereFits
                : t.isPlacing(activePlayer?.name ?? '?')}
            </p>
          </div>
        </div>
        <Timeline cards={hand} onSlotClick={isYourTurn ? onPlace : null} />
        <div className="mt-5">
          <CountdownBar deadlineMs={snapshot.placing_deadline_ms} />
        </div>
      </div>
    </div>
  )
}

function HitsterStealing({
  snapshot,
  myId,
  onSteal,
}: {
  snapshot: RoomSnapshot
  myId: string | null
  onSteal: (slot: number) => void
}) {
  const { t } = useI18n()
  const misser = snapshot.players.find((p) => p.id === snapshot.steal_placer_id)
  const misserName = misser?.name ?? '?'
  const isMisser = myId !== null && myId === snapshot.steal_placer_id
  const myHand = (myId && snapshot.hands[myId]) || []
  const eligible =
    myId !== null &&
    snapshot.turn_order.includes(myId) &&
    !isMisser &&
    !snapshot.finished_players.includes(myId) &&
    !snapshot.disconnected.includes(myId)

  // lock the UI the instant we click, before the server confirms in/out
  const [localTried, setLocalTried] = useState(false)
  useEffect(() => {
    setLocalTried(false)
  }, [snapshot.steal_deadline_ms])
  const tried =
    localTried || (myId !== null && snapshot.steal_attempted.includes(myId))
  const myTurnToSteal = eligible && !tried

  const handleSteal = (slot: number) => {
    setLocalTried(true)
    onSteal(slot)
  }

  const subtitle = myTurnToSteal
    ? t.stealPrompt
    : tried
      ? t.stealLockedIn
      : isMisser
        ? t.stealMisserWatch
        : t.stealWatching

  return (
    <div className="space-y-4 anim-fade-in">
      <div className="card wedge-yellow anim-steal-pulse text-center py-6">
        <div className="flex items-center justify-center gap-2 text-amber-400 text-xs uppercase tracking-wider font-semibold">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          {t.stealEyebrow}
        </div>
        <div className="flex justify-center my-4 anim-float">
          <MysteryCard size="sm" />
        </div>
        <p className="text-xl font-bold">
          {isMisser ? t.stealMissedYou : t.stealMissedOther(misserName)}
        </p>
        <p className="text-muted text-sm mt-1">{subtitle}</p>
        <div className="mt-4 max-w-xs mx-auto">
          <CountdownBar deadlineMs={snapshot.steal_deadline_ms} />
        </div>
      </div>

      {(myTurnToSteal || tried) && (
        <div className="card">
          <p className="text-xs uppercase tracking-wider text-muted mb-3">
            {myTurnToSteal ? t.stealPlaceOnTimeline : t.yourTimeline}
          </p>
          <Timeline
            cards={myHand}
            onSlotClick={myTurnToSteal ? handleSteal : null}
          />
        </div>
      )}
    </div>
  )
}

function HitsterReveal({
  result,
  snapshot,
  isHost,
  onNext,
  onEndGame,
}: {
  result: PlacementResultMsg
  snapshot: RoomSnapshot
  isHost: boolean
  onNext: () => void
  onEndGame: () => void
}) {
  const { t } = useI18n()
  const placer = snapshot.players.find((p) => p.id === result.placer_id)
  const placerName = placer?.name ?? t.unknownPlayer
  const stolen = result.steal_offered && result.stolen_by !== null
  const stealer = stolen
    ? snapshot.players.find((p) => p.id === result.stolen_by)
    : undefined
  const stealerName = stealer?.name ?? t.unknownPlayer
  // a correct placement OR a successful steal counts as a "win" for the card
  const cardWon = result.correct || stolen
  // when stolen, spotlight the thief's timeline (they got the card)
  const timelineOwnerName = stolen ? stealerName : placerName
  const timelineHand = stolen
    ? snapshot.hands[result.stolen_by!] ?? result.stealer_new_hand ?? []
    : snapshot.hands[result.placer_id] ?? result.placer_new_hand

  return (
    <div className="space-y-4 anim-fade-in">
      <div className={'card space-y-4 text-center' + (cardWon ? ' wedge-green' : '')}>
        <div className="flex justify-center [perspective:800px]">
          <div className={cardWon ? '' : 'anim-shake'}>
            {result.card.artwork_url ? (
              <img
                src={result.card.artwork_url}
                alt={t.coverAlt(result.card.title)}
                className={
                  'w-32 h-32 sm:w-40 sm:h-40 rounded-xl shadow-2xl anim-flip-in ' +
                  (cardWon
                    ? 'ring-2 ring-emerald-400/50'
                    : 'ring-2 ring-red-500/60')
                }
              />
            ) : (
              <div className="w-32 h-32 sm:w-40 sm:h-40 rounded-xl bg-surface-2 border border-border flex items-center justify-center text-muted text-xs uppercase tracking-wider anim-flip-in">
                {t.noCover}
              </div>
            )}
          </div>
        </div>
        <div className="anim-fade-in anim-delay-200">
          <h2 className="text-xl font-bold">{result.card.title}</h2>
          <p className="text-muted">{result.card.artist}</p>
          {result.card.added_by && (
            <p className="text-xs uppercase tracking-wider text-muted mt-1">
              {t.addedByLabel}{' '}
              <span className="text-accent">{result.card.added_by}</span>
            </p>
          )}
        </div>
        <div className="relative">
          {cardWon && <NoteBurst count={12} />}
          <p className="text-xs uppercase tracking-wider text-muted">
            {t.releasedIn}
          </p>
          <motion.p
            initial={{ scale: 0.2, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 260, damping: 14, delay: 0.25 }}
            className="font-display text-5xl font-bold tabular-nums text-accent drop-shadow-[0_0_14px_color-mix(in_oklab,var(--color-accent)_55%,transparent)]"
          >
            {result.card.year}
          </motion.p>
        </div>
        <p
          className={
            'text-lg font-bold anim-fade-in anim-delay-400 ' +
            (result.correct
              ? 'text-emerald-300'
              : 'text-red-400')
          }
        >
          {result.correct
            ? t.gotItRight(placerName)
            : t.placedWrong(placerName)}
        </p>
        {result.placer_finished_place !== null && (
          <p className="text-base font-bold text-accent anim-fade-in anim-delay-600">
            {MEDALS[result.placer_finished_place - 1] ?? '🏁'}{' '}
            {t.locksPlace(placerName, result.placer_finished_place)}
          </p>
        )}
        {result.steal_offered &&
          (stolen ? (
            <p className="text-lg font-bold text-amber-400 anim-fade-in anim-delay-600">
              🥷 {t.stealWon(stealerName)}
            </p>
          ) : (
            <p className="text-muted text-sm anim-fade-in anim-delay-600">
              {t.stealNobody}
            </p>
          ))}
        {stolen && result.stealer_finished_place !== null && (
          <p className="text-base font-bold text-accent anim-fade-in anim-delay-600">
            {MEDALS[result.stealer_finished_place - 1] ?? '🏁'}{' '}
            {t.locksPlace(stealerName, result.stealer_finished_place)}
          </p>
        )}
      </div>

      <div className="card">
        <p className="text-xs uppercase tracking-wider text-muted mb-3">
          {t.playersTimeline(timelineOwnerName)}
        </p>
        <Timeline
          cards={timelineHand}
          onSlotClick={null}
          highlightTrackId={cardWon ? result.card.track_id : null}
        />
      </div>

      <div className="card space-y-3">
        {result.pool_exhausted && !result.game_finished && (
          <p className="text-center text-muted text-xs uppercase tracking-wider">
            {t.poolExhausted}
          </p>
        )}
        {isHost ? (
          result.game_finished || result.pool_exhausted ? (
            <button onClick={onEndGame} className="btn-primary w-full">
              {t.finalScoreboard}
            </button>
          ) : (
            <button onClick={onNext} className="btn-primary w-full">
              {t.nextTurn}
            </button>
          )
        ) : (
          <p className="text-center text-muted text-sm">
            {result.game_finished || result.pool_exhausted
              ? t.waitingHostScoreboard
              : t.waitingHostNextTurn}
          </p>
        )}
      </div>
    </div>
  )
}

function SpeakerIcon() {
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
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
    </svg>
  )
}

function rankColor(i: number): string {
  if (i === 0) return 'text-amber-300'
  if (i === 1) return 'text-zinc-300'
  if (i === 2) return 'text-orange-400'
  return 'text-muted'
}

function RoomCodeChip({ code }: { code: string }) {
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
      .catch(() => { })
  }

  return (
    <button
      onClick={copy}
      title={t.copyInvite}
      aria-label={t.copyInvite}
      className="flex items-center gap-2 rounded-full bg-surface border border-border hover:border-accent px-3 py-1.5 transition shadow-sm"
    >
      <span className="text-[10px] uppercase tracking-wider text-muted">
        {copied ? (
          <span className="text-accent">{t.copied}</span>
        ) : (
          t.roomLabel
        )}
      </span>
      <span className="font-mono font-bold tracking-widest text-sm">
        {code}
      </span>
      {copied ? <CheckIcon /> : <CopyIcon />}
    </button>
  )
}

function CopyIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-muted"
      aria-hidden="true"
    >
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-accent"
      aria-hidden="true"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function GameOver({
  players,
  cumulativeScores,
  finishedPlayers,
  gameMode,
  bingoWinners,
  isHost,
  onRematch,
}: {
  players: Player[]
  cumulativeScores: Record<string, number>
  finishedPlayers: string[]
  gameMode: GameMode
  bingoWinners: string[]
  isHost: boolean
  onRematch: () => void
}) {
  const { t } = useI18n()
  const isBingo = gameMode === 'bingo'
  // finishers rank first (in finish order), everyone else by card count.
  // In bingo, finishedPlayers already IS the full ranking (winners first,
  // then marks desc) and simultaneous winners share the top spot.
  const finishedSet = new Set(finishedPlayers)
  const finishers = finishedPlayers
    .map((id) => players.find((p) => p.id === id))
    .filter((p): p is Player => p !== undefined)
  const others = players
    .filter((p) => !finishedSet.has(p.id))
    .sort(
      (a, b) => (cumulativeScores[b.id] ?? 0) - (cumulativeScores[a.id] ?? 0),
    )
  const ranked = [...finishers, ...others]
  const topScore = ranked.length ? cumulativeScores[ranked[0].id] ?? 0 : 0
  const winners = isBingo
    ? bingoWinners
        .map((id) => players.find((p) => p.id === id))
        .filter((p): p is Player => p !== undefined)
    : finishers.length > 0
      ? [finishers[0]]
      : topScore > 0
        ? ranked.filter((p) => (cumulativeScores[p.id] ?? 0) === topScore)
        : []

  const podium = ranked.slice(0, 3)
  const rest = ranked.slice(3)

  return (
    <div className="card wedge-yellow space-y-6 text-center anim-fade-in">
      {winners.length > 0 && <Confetti />}
      <div>
        <p className="text-xs uppercase tracking-wider text-muted">
          {t.gameOver}
        </p>
        {winners.length > 0 ? (
          <div className="mt-2 anim-pop-in">
            {isBingo && (
              <p className="font-display text-xl font-bold text-neon-green drop-shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-green)_60%,transparent)] mb-1">
                {t.bingo.bingoWin}
              </p>
            )}
            <p className="font-display text-3xl sm:text-4xl font-bold neon-text">
              {winners.map((w) => w.name).join(', ')}
            </p>
            <p className="text-muted text-sm mt-1">
              {isBingo
                ? t.bingo.bingoWinsWith(winners.length, topScore)
                : t.winsWith(winners.length, topScore)}
            </p>
          </div>
        ) : (
          <p className="text-2xl font-bold mt-2">{t.noPointsScored}</p>
        )}
      </div>

      <div className="border-b border-border anim-fade-in anim-delay-200">
        <Podium entries={podium} scores={cumulativeScores} />
      </div>

      {rest.length > 0 && (
        <div className="space-y-2 anim-fade-in anim-delay-400">
          {rest.map((p, i) => (
            <div
              key={p.id}
              className="flex items-center justify-between rounded-md px-3 py-2 gap-2 bg-surface-2"
            >
              <span className="flex items-center gap-3 min-w-0 flex-1">
                <span className="font-mono font-bold w-5 text-center text-sm text-muted">
                  {i + 4}
                </span>
                <Avatar name={p.name} avatar={p.avatar} isBot={p.is_bot} />
                <span className="truncate">{p.name}</span>
              </span>
              <span className="font-mono font-bold tabular-nums shrink-0">
                {cumulativeScores[p.id] ?? 0}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="anim-fade-in anim-delay-400">
        {isHost ? (
          <button onClick={onRematch} className="btn-primary w-full">
            {t.rematch}
          </button>
        ) : (
          <p className="text-muted text-sm">{t.waitingHostRematch}</p>
        )}
      </div>
    </div>
  )
}

function Podium({
  entries,
  scores,
}: {
  entries: Player[]
  scores: Record<string, number>
}) {
  // classic arrangement: 2nd left, 1st middle, 3rd right
  const order = [1, 0, 2].filter((rank) => rank < entries.length)
  const blockHeight = ['h-24', 'h-16', 'h-11']
  return (
    <div className="flex items-end justify-center gap-3">
      {order.map((rank) => {
        const p = entries[rank]
        return (
          <div
            key={p.id}
            className="flex flex-col items-center gap-2 flex-1 max-w-[110px] min-w-0"
          >
            <Avatar name={p.name} avatar={p.avatar} isBot={p.is_bot} size="lg" />
            <span className="text-sm font-medium truncate w-full">
              {p.name}
            </span>
            <motion.div
              initial={{ scaleY: 0, opacity: 0 }}
              animate={{ scaleY: 1, opacity: 1 }}
              style={{ originY: 1 }}
              transition={{
                type: 'spring',
                stiffness: 240,
                damping: 22,
                delay: 0.3 + rank * 0.18,
              }}
              className={
                `w-full rounded-t-xl border border-b-0 flex flex-col items-center justify-end pb-2 ${blockHeight[rank]} ` +
                (rank === 0
                  ? 'border-neon-yellow/50 bg-neon-yellow/10 shadow-[0_0_24px_-4px_color-mix(in_oklab,var(--color-neon-yellow)_55%,transparent)]'
                  : 'bg-surface-2 border-border')
              }
            >
              <span
                className={`font-display text-2xl font-bold ${rankColor(rank)}`}
              >
                {rank + 1}
              </span>
              <span className="text-xs text-muted tabular-nums">
                {scores[p.id] ?? 0}
              </span>
            </motion.div>
          </div>
        )
      })}
    </div>
  )
}

const CONFETTI_COLORS = [
  'var(--color-accent)',
  'oklch(0.7 0.15 160)',
  'oklch(0.65 0.18 250)',
  'oklch(0.7 0.19 0)',
]

function Confetti() {
  // deterministic pseudo-random spread so re-renders don't reshuffle
  const pieces = useMemo(
    () =>
      Array.from({ length: 28 }, (_, i) => ({
        left: (i * 37) % 100,
        delay: ((i * 53) % 140) / 100,
        duration: 2.6 + ((i * 29) % 100) / 70,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      })),
    [],
  )
  return (
    <div
      className="pointer-events-none fixed inset-0 overflow-hidden z-40"
      aria-hidden="true"
    >
      {pieces.map((p, i) => (
        <span
          key={i}
          className="confetti-piece absolute w-1.5 h-3 rounded-[1px]"
          style={{
            left: `${p.left}%`,
            backgroundColor: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
    </div>
  )
}

// ---- easter egg: fake-ads overlay ----

