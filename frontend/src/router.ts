import { useEffect, useState } from 'react'

export type Route =
  | { kind: 'landing' }
  | { kind: 'room'; code: string }
  | { kind: 'unknown' }

const NAV_EVENT = 'beatster:nav'

function parse(pathname: string): Route {
  if (pathname === '/' || pathname === '') return { kind: 'landing' }
  const m = pathname.match(/^\/r\/([A-Za-z0-9]+)\/?$/)
  if (m) return { kind: 'room', code: m[1].toUpperCase() }
  return { kind: 'unknown' }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.pathname))

  useEffect(() => {
    const handler = () => setRoute(parse(window.location.pathname))
    window.addEventListener('popstate', handler)
    window.addEventListener(NAV_EVENT, handler)
    return () => {
      window.removeEventListener('popstate', handler)
      window.removeEventListener(NAV_EVENT, handler)
    }
  }, [])

  return route
}

export function navigate(path: string): void {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new Event(NAV_EVENT))
}
