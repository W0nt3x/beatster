// Lobby song-pool card: submit-only iTunes search, add/remove contributions,
// tap-to-correct category pill and the 30s preview player (own <audio>,
// isolated from the game audio).
import { useEffect, useRef, useState } from 'react'
import {
  getStoredVolume,
  searchSongs,
  type SongSearchResult,
} from './api'
import { useI18n } from './i18n'
import type { ExtraTrackSummary } from './types'
import { Checkbox } from './ui'

export default function SongPool({
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
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SongSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)

  // 30s preview playback, isolated from the game audio (separate element) —
  // listen before/after adding a custom song. The URL comes free with the
  // search / resolved track, so no extra iTunes calls.
  const previewRef = useRef<HTMLAudioElement | null>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  useEffect(() => () => previewRef.current?.pause(), [])
  const togglePreview = (id: string, url: string) => {
    const audio = previewRef.current
    if (!audio || !url) return
    if (previewId === id) {
      audio.pause()
      setPreviewId(null)
      return
    }
    audio.src = url
    audio.currentTime = 0
    audio.volume = getStoredVolume()
    audio.play().catch(() => setPreviewId(null))
    setPreviewId(id)
  }

  // Search only fires on submit (button / Enter), never per keystroke — a
  // search-as-you-type flood from several players at once trips iTunes' rate
  // limiter and the API starts returning nothing.
  const runSearch = async () => {
    const q = query.trim()
    if (!q || searching) return
    setSearching(true)
    setSearched(true)
    try {
      setResults(await searchSongs(q))
    } finally {
      setSearching(false)
    }
  }

  const clearSearch = () => {
    setResults([])
    setSearched(false)
  }

  const yourCount = yourTracks.length
  const disabled = !unlimited && perPlayerCap === 0
  const atCap = !unlimited && yourCount >= perPlayerCap
  const overCap = !unlimited && yourCount > perPlayerCap
  const remaining = unlimited ? 0 : Math.max(0, perPlayerCap - yourCount)

  const handleAdd = (trackId: string) => {
    onAdd(trackId)
    setQuery('')
    clearSearch()
  }

  return (
    <div className="space-y-3">
      <audio ref={previewRef} onEnded={() => setPreviewId(null)} />
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-muted">
          {t.songPool}
        </h3>
        <span className="text-xs text-muted tabular-nums">
          {unlimited
            ? t.poolStatsUnlimited(extraTracksTotal, yourCount)
            : t.poolStats(extraTracksTotal, yourCount, perPlayerCap)}
        </span>
      </div>

      <Checkbox
        checked={onlyPlayerAdded}
        disabled={!isHost}
        onChange={(v) => onSetOnlyPlayerAdded(v)}
        label={t.onlyPlayerAddedToggle}
      />

      {disabled ? (
        <p className="text-xs text-muted">{t.contributionsDisabled}</p>
      ) : atCap ? (
        <p className="text-xs text-muted">
          {overCap
            ? t.overCap(yourCount, perPlayerCap)
            : t.allSlotsUsed(perPlayerCap)}
        </p>
      ) : (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                if (!e.target.value.trim()) clearSearch()
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void runSearch()
                }
              }}
              placeholder={t.searchSong}
              className="input-base flex-1"
            />
            <button
              type="button"
              onClick={() => void runSearch()}
              disabled={!query.trim() || searching}
              className="shrink-0 rounded-lg border border-neon-pink/50 px-4 text-sm font-semibold text-neon-pink transition hover:shadow-[0_0_12px_color-mix(in_oklab,var(--color-neon-pink)_35%,transparent)] active:scale-[0.98] disabled:opacity-50 disabled:shadow-none"
            >
              {t.searchButton}
            </button>
          </div>
          {searching && <p className="text-xs text-muted">{t.searching}</p>}
          {!searching && searched && results.length === 0 && (
            <p className="text-xs text-muted">{t.noMatches}</p>
          )}
          {results.length > 0 && (
            <ul className="space-y-1">
              {results.map((r) => (
                <li
                  key={r.track_id}
                  className="flex items-center gap-2 rounded-lg border border-border/60 bg-surface-2/70 px-3 py-2 text-sm transition hover:border-neon-pink/50"
                >
                  <span className="flex-1 min-w-0 truncate">
                    <span className="font-medium">{r.title}</span>
                    <span className="text-muted ml-2">{r.artist}</span>
                  </span>
                  <PreviewButton
                    playing={previewId === r.track_id}
                    hasPreview={!!r.preview_url}
                    onClick={() => togglePreview(r.track_id, r.preview_url)}
                  />
                  <button
                    onClick={() => handleAdd(r.track_id)}
                    className="shrink-0 rounded-full px-3 py-1 text-xs font-bold text-accent-fg transition hover:brightness-110 active:scale-[0.97]"
                    style={{
                      background:
                        'linear-gradient(95deg, var(--color-accent), var(--color-neon-pink))',
                      boxShadow:
                        '0 2px 10px color-mix(in oklab, var(--color-neon-pink) 30%, transparent)',
                    }}
                  >
                    ＋ {t.add}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!query.trim() && remaining > 0 && (
            <p className="text-xs text-muted">{t.slotsRemaining(remaining)}</p>
          )}
        </div>
      )}

      {yourTracks.length > 0 && (
        <div className="space-y-1 pt-1">
          <p className="text-xs uppercase tracking-wider text-muted">
            {t.yourContributions(yourTracks.length)}
          </p>
          <ul className="space-y-1">
            {yourTracks.map((track) => (
              <li
                key={track.track_id}
                className="flex items-center gap-2 rounded-lg border border-border/60 bg-surface-2/70 px-3 py-2 text-sm"
              >
                <span className="flex-1 min-w-0 truncate">
                  <span aria-hidden="true">💿</span>{' '}
                  <span className="font-medium">{track.title}</span>
                  <span className="text-muted ml-2">{track.artist}</span>
                </span>
                <PreviewButton
                  playing={previewId === track.track_id}
                  hasPreview={!!track.preview_url}
                  onClick={() => togglePreview(track.track_id, track.preview_url)}
                />
                <button
                  type="button"
                  onClick={() =>
                    onSetCategory(
                      track.track_id,
                      track.category === 'film_tv' ? 'music' : 'film_tv',
                    )
                  }
                  title={t.tapToChangeCategory}
                  aria-label={t.tapToChangeCategory}
                  className={
                    'shrink-0 px-1.5 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-semibold transition border ' +
                    (track.category === 'film_tv'
                      ? 'bg-neon-cyan/15 text-neon-cyan border-neon-cyan/50 hover:bg-neon-cyan/25'
                      : 'bg-neon-pink/15 text-neon-pink border-neon-pink/50 hover:bg-neon-pink/25')
                  }
                >
                  {track.category === 'film_tv'
                    ? `🎬 ${t.categoryFilmTv}`
                    : `🎵 ${t.categoryMusic}`}
                </button>
                <button
                  onClick={() => onRemove(track.track_id)}
                  className="text-xs text-muted hover:text-red-400 shrink-0 px-2 py-1 transition"
                  title={t.remove}
                >
                  {t.remove}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function PreviewButton({
  playing,
  hasPreview,
  onClick,
}: {
  playing: boolean
  hasPreview: boolean
  onClick: () => void
}) {
  const { t } = useI18n()
  if (!hasPreview) return null
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={playing ? t.pausePreview : t.playPreview}
      title={playing ? t.pausePreview : t.playPreview}
      className={
        'shrink-0 flex items-center justify-center w-7 h-7 rounded-full border transition ' +
        (playing
          ? 'bg-neon-cyan/20 border-neon-cyan/60 text-neon-cyan shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-cyan)_40%,transparent)]'
          : 'bg-surface border-border text-muted hover:text-neon-cyan hover:border-neon-cyan')
      }
    >
      {playing ? <PauseIcon /> : <PlayIcon />}
    </button>
  )
}

function PlayIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M8 5v14l11-7z" />
    </svg>
  )
}

function PauseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="currentColor"
      aria-hidden="true"
    >
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  )
}

