import { useEffect, useState } from 'react'

// True once a newer frontend build has been deployed than the one this tab is
// running. Polls the (no-cache) version.json that the build writes, and also
// re-checks when the tab regains focus. Callers decide what to do (auto-reload
// when idle, show a banner mid-game).
export function useUpdateAvailable(): boolean {
  const [stale, setStale] = useState(false)
  useEffect(() => {
    let active = true
    const check = async () => {
      try {
        const r = await fetch('/version.json', { cache: 'no-store' })
        if (!r.ok) return
        const data = (await r.json()) as { v?: string }
        if (active && data.v && data.v !== __BUILD_ID__) setStale(true)
      } catch {
        // offline / transient — ignore, try again next tick
      }
    }
    void check()
    const id = window.setInterval(() => void check(), 60_000)
    const onFocus = () => void check()
    window.addEventListener('focus', onFocus)
    return () => {
      active = false
      window.clearInterval(id)
      window.removeEventListener('focus', onFocus)
    }
  }, [])
  return stale
}
