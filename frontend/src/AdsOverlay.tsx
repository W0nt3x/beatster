// ---- easter egg: fake-ads overlay (see CLAUDE.md — intentional prank,
// NOT dead code). Triggered via the secret sequence handled in Room.tsx. ----
import { useEffect, useRef, useState } from 'react'

// Ad images live in src/ads/ and are auto-collected by filename prefix — just
// drop more PNGs in (skyscraper-left*, skyscraper-right*, banner-*, popup-*)
// and they join the rotation, no code change needed. Vite hashes them too.
function adUrls(mod: Record<string, unknown>): string[] {
  return Object.keys(mod)
    .sort()
    .map((k) => mod[k] as string)
}
const AD_SKY_LEFT = adUrls(
  import.meta.glob('./ads/skyscraper-left*.png', {
    eager: true,
    query: '?url',
    import: 'default',
  }),
)
const AD_SKY_RIGHT = adUrls(
  import.meta.glob('./ads/skyscraper-right*.png', {
    eager: true,
    query: '?url',
    import: 'default',
  }),
)
const AD_BANNERS = adUrls(
  import.meta.glob('./ads/banner-*.png', {
    eager: true,
    query: '?url',
    import: 'default',
  }),
)
const AD_POPUPS = adUrls(
  import.meta.glob('./ads/popup-*.png', {
    eager: true,
    query: '?url',
    import: 'default',
  }),
)

// Pick a uniformly random index that isn't `current`, so the image always
// actually changes (and so two viewers rarely land on the same one).
function randomOther(current: number, count: number): number {
  if (count <= 1) return current
  let next = Math.floor(Math.random() * (count - 1))
  if (next >= current) next += 1
  return next
}

// Cycle an index through `count` items on a timer; random start + random next
// so each user sees a different ad rotation. Pauses at 0/1 items.
function useRotatingIndex(count: number, intervalMs: number): number {
  const [i, setI] = useState(() =>
    count > 0 ? Math.floor(Math.random() * count) : 0,
  )
  useEffect(() => {
    if (count <= 1) return
    const id = window.setInterval(
      () => setI((cur) => randomOther(cur, count)),
      intervalMs,
    )
    return () => window.clearInterval(id)
  }, [count, intervalMs])
  return count > 0 ? i % count : 0
}

export default function AdsOverlay() {
  return (
    <>
      <AdSkyscraper urls={AD_SKY_LEFT} side="left" />
      <AdSkyscraper urls={AD_SKY_RIGHT} side="right" />
      <AdBottomBanner />
      <AdPopup />
    </>
  )
}

function AdSkyscraper({
  urls,
  side,
}: {
  urls: string[]
  side: 'left' | 'right'
}) {
  const idx = useRotatingIndex(urls.length, 6000)
  if (urls.length === 0) return null
  return (
    <div
      className={
        'hidden lg:block fixed top-1/2 -translate-y-1/2 z-30 w-[160px] anim-fade-in ' +
        (side === 'left' ? 'left-3' : 'right-3')
      }
    >
      <AdLabel />
      <img src={urls[idx]} alt="" className="w-full rounded shadow-2xl" />
    </div>
  )
}

function AdBottomBanner() {
  const [closed, setClosed] = useState(false)
  const idx = useRotatingIndex(AD_BANNERS.length, 7000)
  if (closed || AD_BANNERS.length === 0) return null
  return (
    <div className="fixed bottom-0 inset-x-0 z-40 flex justify-center px-2 pb-2 pointer-events-none anim-fade-in">
      <div className="relative pointer-events-auto w-full max-w-2xl">
        <AdCloseButton onClick={() => setClosed(true)} />
        <img
          src={AD_BANNERS[idx]}
          alt=""
          className="w-full rounded-lg shadow-2xl"
        />
      </div>
    </div>
  )
}

function AdPopup() {
  const [open, setOpen] = useState(false)
  const [idx, setIdx] = useState(() =>
    AD_POPUPS.length > 0 ? Math.floor(Math.random() * AD_POPUPS.length) : 0,
  )
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    // appears a few seconds in, then nags back after each close
    timerRef.current = window.setTimeout(() => setOpen(true), 4500)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  if (AD_POPUPS.length === 0) return null

  const close = () => {
    setOpen(false)
    // random different image each time it nags back
    setIdx((i) => randomOther(i, AD_POPUPS.length))
    timerRef.current = window.setTimeout(() => setOpen(true), 16000)
  }

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 anim-fade-in">
      <div className="relative anim-pop-in">
        <AdCloseButton onClick={close} />
        <img
          src={AD_POPUPS[idx]}
          alt=""
          className="max-w-[88vw] max-h-[80vh] rounded-xl shadow-2xl"
        />
      </div>
    </div>
  )
}

function AdLabel() {
  return (
    <div className="text-[9px] uppercase tracking-widest text-zinc-500 mb-0.5 select-none">
      Anzeige
    </div>
  )
}

function AdCloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label="Werbung schließen"
      className="absolute -top-2.5 -right-2.5 z-10 w-6 h-6 rounded-full bg-zinc-800 border border-zinc-600 text-zinc-300 hover:text-white hover:border-zinc-400 flex items-center justify-center text-[11px] leading-none shadow-lg transition"
    >
      ✕
    </button>
  )
}
