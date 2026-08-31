import { useEffect, useState } from 'react'
import { createRoom } from './api'
import { DiscoBall } from './fx'
import { useI18n } from './i18n'
import { navigate } from './router'
import { useUpdateAvailable } from './useUpdate'
import HowToPlay from './HowToPlay'
import Leaderboard from './Leaderboard'

export default function Landing() {
  const { t } = useI18n()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [boardOpen, setBoardOpen] = useState(false)

  // pick up a freshly deployed frontend without a manual hard-refresh
  const updateAvailable = useUpdateAvailable()
  useEffect(() => {
    if (updateAvailable) window.location.reload()
  }, [updateAvailable])

  async function onCreate(bots = 0) {
    setBusy(true)
    setError(null)
    try {
      const c = await createRoom(bots)
      navigate(`/r/${c}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function onJoin(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = code.trim().toUpperCase()
    if (trimmed.length === 0) return
    navigate(`/r/${trimmed}`)
  }

  return (
    <div className="min-h-full flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md anim-fade-in">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <DiscoBall size={64} />
          </div>
          <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">
            Beatster{' '}
            <span className="neon-text anim-flicker">Online</span>
          </h1>
          <p className="text-muted mt-3 text-sm sm:text-base">{t.tagline}</p>
        </div>

        <div className="card wedge-orange">
          <button
            onClick={() => onCreate(0)}
            disabled={busy}
            className="btn-primary w-full text-base"
          >
            {busy ? t.creatingRoom : t.createRoom}
          </button>

          <button
            onClick={() => onCreate(2)}
            disabled={busy}
            className="btn-secondary w-full mt-3"
          >
            {t.singleplayer}
          </button>

          <div className="my-5 flex items-center gap-3 text-muted text-xs uppercase tracking-wider">
            <div className="flex-1 h-px bg-border" />
            <span>{t.orJoinExisting}</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <form onSubmit={onJoin} className="space-y-3">
            <input
              placeholder={t.roomCodePlaceholder}
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              autoFocus
              maxLength={6}
              className="input-base w-full text-center uppercase tracking-[0.4em] font-bold text-xl py-3"
            />
            <button
              type="submit"
              disabled={code.trim().length === 0}
              className="btn-secondary w-full"
            >
              {t.join}
            </button>
          </form>
        </div>

        {error && (
          <p className="text-red-400 text-center mt-4 text-sm">
            {error}
          </p>
        )}

        <p className="text-center mt-5 flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => setHelpOpen(true)}
            className="text-muted text-sm underline hover:text-accent transition"
          >
            {t.howToPlay.title}
          </button>
          <span className="text-border select-none" aria-hidden="true">
            ·
          </span>
          <button
            type="button"
            onClick={() => setBoardOpen(true)}
            className="text-muted text-sm underline hover:text-accent transition"
          >
            🏆 {t.leaderboard}
          </button>
        </p>

        <p className="text-center text-xs text-muted/70 mt-8">
          {t.credit}
          <span className="mx-1.5 select-none" aria-hidden="true">·</span>
          <a
            href="https://ko-fi.com/wontex"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-accent transition"
          >
            ☕ {t.kofi}
          </a>
        </p>
      </div>

      <HowToPlay open={helpOpen} onClose={() => setHelpOpen(false)} />
      <Leaderboard open={boardOpen} onClose={() => setBoardOpen(false)} />
    </div>
  )
}

