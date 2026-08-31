import { useI18n } from './i18n'

export default function LanguageToggle() {
  const { lang, setLang } = useI18n()
  const target = lang === 'de' ? 'en' : 'de'
  // Label in the target language — it describes what the button switches TO.
  const label = lang === 'de' ? 'Switch to English' : 'Auf Deutsch wechseln'

  return (
    <button
      onClick={() => setLang(target)}
      aria-label={label}
      title={label}
      className="w-10 h-10 rounded-full bg-surface border border-border transition flex items-center justify-center shadow-lg hover:border-neon-violet hover:shadow-[0_0_14px_color-mix(in_oklab,var(--color-neon-violet)_45%,transparent)]"
    >
      <span className="block w-6 h-6 rounded-full overflow-hidden border border-border">
        {lang === 'de' ? <UkFlag /> : <DeFlag />}
      </span>
    </button>
  )
}

function UkFlag() {
  return (
    <svg
      viewBox="0 0 60 30"
      preserveAspectRatio="xMidYMid slice"
      className="w-full h-full"
      aria-hidden="true"
    >
      <clipPath id="uk-quadrants">
        <path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
      </clipPath>
      <path d="M0,0 v30 h60 v-30 z" fill="#012169" />
      <path d="M0,0 60,30 M60,0 0,30" stroke="#fff" strokeWidth="6" />
      <path
        d="M0,0 60,30 M60,0 0,30"
        clipPath="url(#uk-quadrants)"
        stroke="#C8102E"
        strokeWidth="4"
      />
      <path d="M30,0 v30 M0,15 h60" stroke="#fff" strokeWidth="10" />
      <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" strokeWidth="6" />
    </svg>
  )
}

function DeFlag() {
  return (
    <svg
      viewBox="0 0 5 3"
      preserveAspectRatio="xMidYMid slice"
      className="w-full h-full"
      aria-hidden="true"
    >
      <rect width="5" height="1" y="0" fill="#000" />
      <rect width="5" height="1" y="1" fill="#DD0000" />
      <rect width="5" height="1" y="2" fill="#FFCE00" />
    </svg>
  )
}
