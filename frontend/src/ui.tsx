// Shared UI primitives used across the room screens (steppers, toggles,
// countdowns, avatars, invite QR). Extracted from Room.tsx — no logic here.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { QRCodeSVG } from 'qrcode.react'
import { avatarUrl } from './avatar'
import { useI18n } from './i18n'

export function SettingRow({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm">{label}</span>
      {children}
    </div>
  )
}

export function NumberStepper({
  value,
  min,
  max,
  onChange,
  ariaLabel,
}: {
  value: number
  min: number
  max: number
  onChange: (n: number) => void
  ariaLabel?: string
}) {
  const [local, setLocal] = useState(value.toString())
  useEffect(() => {
    setLocal(value.toString())
  }, [value])

  const commit = (raw: string) => {
    const n = parseInt(raw, 10)
    if (!Number.isFinite(n)) {
      setLocal(value.toString())
      return
    }
    const clamped = Math.min(max, Math.max(min, n))
    setLocal(clamped.toString())
    if (clamped !== value) onChange(clamped)
  }

  const step = (delta: number) => {
    const next = Math.min(max, Math.max(min, value + delta))
    if (next !== value) onChange(next)
  }

  return (
    <div className="flex items-stretch h-10 rounded-lg border border-border bg-surface-2 overflow-hidden transition focus-within:border-neon-violet focus-within:ring-2 focus-within:ring-neon-violet/30">
      <input
        type="text"
        inputMode="numeric"
        value={local}
        aria-label={ariaLabel}
        onChange={(e) => {
          const v = e.target.value.replace(/\D/g, '').slice(0, 2)
          setLocal(v)
          const n = parseInt(v, 10)
          if (Number.isFinite(n) && n >= min && n <= max && n !== value) {
            onChange(n)
          }
        }}
        onBlur={(e) => commit(e.target.value)}
        className="w-12 bg-transparent text-center font-mono font-bold text-fg focus:outline-none"
      />
      <div className="flex flex-col w-7 border-l border-border">
        <button
          type="button"
          onClick={() => step(1)}
          disabled={value >= max}
          aria-label="+1"
          className="flex-1 flex items-center justify-center text-neon-violet hover:bg-neon-violet/15 active:bg-neon-violet/25 disabled:opacity-25 disabled:hover:bg-transparent transition"
        >
          <Chevron dir="up" />
        </button>
        <button
          type="button"
          onClick={() => step(-1)}
          disabled={value <= min}
          aria-label="-1"
          className="flex-1 flex items-center justify-center text-neon-violet hover:bg-neon-violet/15 active:bg-neon-violet/25 disabled:opacity-25 disabled:hover:bg-transparent transition border-t border-border"
        >
          <Chevron dir="down" />
        </button>
      </div>
    </div>
  )
}

export function Checkbox({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (checked: boolean) => void
  label: string
}) {
  return (
    <label
      className={
        'flex items-center gap-2.5 text-sm select-none ' +
        (disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer group')
      }
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => !disabled && onChange(e.target.checked)}
        className="sr-only"
      />
      <span
        className={
          'shrink-0 w-5 h-5 rounded-md border flex items-center justify-center transition ' +
          (checked
            ? 'bg-neon-green border-neon-green text-accent-fg shadow-[0_0_10px_color-mix(in_oklab,var(--color-neon-green)_45%,transparent)]'
            : 'bg-surface-2 border-border ' +
            (disabled ? '' : 'group-hover:border-neon-green'))
        }
      >
        {checked && (
          <svg
            viewBox="0 0 24 24"
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            className="anim-pop-in"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}
      </span>
      {label}
    </label>
  )
}

export function Chevron({ dir }: { dir: 'up' | 'down' }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="12"
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={dir === 'down' ? 'rotate-180' : ''}
    >
      <path d="M5 15l7-7 7 7" />
    </svg>
  )
}

export function CouchIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3" />
      <path d="M2 11v5a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v2H6v-2a2 2 0 0 0-4 0Z" />
      <path d="M4 18v2" />
      <path d="M20 18v2" />
    </svg>
  )
}

export function GlobeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  )
}

export function CountdownBar({ deadlineMs }: { deadlineMs: number | null }) {
  const { t } = useI18n()
  const [now, setNow] = useState(Date.now())
  const totalRef = useRef(0)

  useEffect(() => {
    if (!deadlineMs) return
    totalRef.current = Math.max(1, deadlineMs - Date.now())
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 100)
    return () => window.clearInterval(id)
  }, [deadlineMs])

  if (!deadlineMs) return null

  const remaining = Math.max(0, deadlineMs - now)
  const pct = Math.max(0, Math.min(100, (remaining / totalRef.current) * 100))
  const seconds = Math.ceil(remaining / 1000)
  const low = pct < 20

  const barStyle: React.CSSProperties = {
    width: `${pct}%`,
    background: low
      ? 'linear-gradient(90deg, #ff5d5d, var(--color-neon-pink))'
      : pct < 50
        ? 'linear-gradient(90deg, var(--color-neon-yellow), var(--color-accent))'
        : 'linear-gradient(90deg, var(--color-neon-green), var(--color-neon-cyan))',
    boxShadow: low
      ? '0 0 12px color-mix(in oklab, var(--color-neon-pink) 70%, transparent)'
      : '0 0 8px color-mix(in oklab, var(--color-neon-cyan) 35%, transparent)',
  }

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted">
        <span className="uppercase tracking-wider">{t.timeRemaining}</span>
        <span
          className={
            'font-mono tabular-nums font-semibold' +
            (low ? ' text-red-400 animate-pulse' : '')
          }
        >
          {seconds}s
        </span>
      </div>
      <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
        <div
          className="h-full rounded-full transition-[width] duration-100 ease-linear"
          style={barStyle}
        />
      </div>
    </div>
  )
}

export function QrIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M3 3h8v8H3V3zm2 2v4h4V5H5zm8-2h8v8h-8V3zm2 2v4h4V5h-4zM3 13h8v8H3v-8zm2 2v4h4v-4H5zm10-2h2v2h-2v-2zm4 0h2v2h-2v-2zm-4 4h2v2h-2v-2zm0 0v-2h-2v2h2zm2 2h2v2h-2v-2zm2 0v-2h-2v2h2zm0 0h2v2h-2v-2z" />
    </svg>
  )
}

/** The invite modal itself (QR + code + copy-link) — reusable behind any
 *  trigger (header icon, lobby chip, the dance-floor "open spot" ghost). */
export function InviteQrModal({
  code,
  open,
  onClose,
}: {
  code: string
  open: boolean
  onClose: () => void
}) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!open) setCopied(false)
  }, [open])
  if (!open) return null

  const url = `${window.location.origin}/r/${code}`
  const copy = () => {
    navigator.clipboard
      ?.writeText(url)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1600)
      })
      .catch(() => {})
  }

  // Portal to <body>: ancestors may carry an `anim-fade-in` whose fill-mode
  // leaves a `transform`, which would otherwise become the containing block
  // for this `fixed` modal and pin/cut it off.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/70 p-4 anim-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="card wedge-pink w-full max-w-xs text-center p-6 my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-xs uppercase tracking-wider text-muted mb-4">
          {t.scanToJoin}
        </p>
        <div className="inline-block rounded-xl bg-white p-3">
          <QRCodeSVG value={url} size={208} />
        </div>
        <p className="font-mono font-bold tracking-widest text-2xl mt-4">
          {code}
        </p>
        <p className="text-muted text-xs mt-1 break-all">{url}</p>
        <button onClick={copy} className="btn-primary w-full mt-5">
          {copied ? `✓ ${t.copied}` : `🔗 ${t.copyLink}`}
        </button>
        <button onClick={onClose} className="btn-secondary w-full mt-2">
          {t.close}
        </button>
      </div>
    </div>,
    document.body,
  )
}

export function InviteQr({
  code,
  variant = 'icon',
}: {
  code: string
  variant?: 'icon' | 'chip'
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <>
      {variant === 'icon' ? (
        <button
          onClick={() => setOpen(true)}
          title={t.showQr}
          aria-label={t.showQr}
          className="flex items-center justify-center w-9 h-9 rounded-full bg-surface border border-border hover:border-accent transition shadow-sm text-fg"
        >
          <QrIcon />
        </button>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-full border border-neon-pink/50 px-3 py-1.5 text-xs font-semibold text-neon-pink transition hover:shadow-[0_0_16px_color-mix(in_oklab,var(--color-neon-pink)_40%,transparent)]"
        >
          <QrIcon />
          {t.inviteFriends}
        </button>
      )}
      <InviteQrModal code={code} open={open} onClose={() => setOpen(false)} />
    </>
  )
}

export function Avatar({
  name,
  avatar = '',
  isBot = false,
  size = 'sm',
}: {
  name: string
  avatar?: string
  isBot?: boolean
  size?: 'sm' | 'lg'
}) {
  const dim = size === 'lg' ? 'w-11 h-11' : 'w-6 h-6'
  return (
    <span
      className={`${dim} rounded-full overflow-hidden bg-surface-2 shrink-0 select-none`}
      aria-hidden="true"
    >
      <img
        src={avatarUrl(avatar, name, isBot)}
        alt=""
        className="w-full h-full object-cover"
        loading="lazy"
      />
    </span>
  )
}

