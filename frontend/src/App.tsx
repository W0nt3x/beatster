import { MotionConfig } from 'motion/react'
import Landing from './Landing'
import Room from './Room'
import LanguageToggle from './LanguageToggle'
import { FxLayers } from './fx'
import { I18nProvider, useI18n } from './i18n'
import { navigate, useRoute } from './router'

export default function App() {
  return (
    <I18nProvider>
      <MotionConfig reducedMotion="user">
        <FxLayers />
        <div className="fixed top-3 right-3 z-50">
          <LanguageToggle />
        </div>
        <Routes />
      </MotionConfig>
    </I18nProvider>
  )
}

function Routes() {
  const route = useRoute()

  return (
    <>
      {route.kind === 'landing' && <Landing />}
      {route.kind === 'room' && <Room code={route.code} />}
      {route.kind === 'unknown' && <NotFound />}
    </>
  )
}

function NotFound() {
  const { t } = useI18n()
  return (
    <div className="min-h-full flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md text-center anim-fade-in">
        <h1 className="font-display text-3xl font-bold">{t.pageNotFound}</h1>
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
      </div>
    </div>
  )
}
