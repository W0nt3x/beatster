// In production the frontend is served from the same origin as the backend
// (nginx proxies /api and /ws to uvicorn), so we use relative paths.
// In dev, vite proxies /api and /ws to localhost:8000 (see vite.config.ts).
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_BASE = `${wsProtocol}//${window.location.host}`

export async function createRoom(bots = 0): Promise<string> {
  const query = bots > 0 ? `?bots=${bots}` : ''
  const res = await fetch(`/api/rooms${query}`, { method: 'POST' })
  if (!res.ok) throw new Error(`create room failed: ${res.status}`)
  const data = (await res.json()) as { code: string }
  return data.code
}

export function roomWsUrl(code: string): string {
  return `${WS_BASE}/ws/${code}`
}

export type SongSearchResult = {
  track_id: string
  title: string
  artist: string
  preview_url: string
}

export async function searchSongs(query: string): Promise<SongSearchResult[]> {
  const trimmed = query.trim()
  if (!trimmed) return []
  const url = `/api/search?q=${encodeURIComponent(trimmed)}`
  const res = await fetch(url)
  if (!res.ok) return []
  const data = (await res.json()) as { results: SongSearchResult[] }
  return data.results
}

export type LeaderboardRow = {
  name: string
  games: number
  wins: number
  podiums: number
  correct: number
  wrong: number
  steals_won: number
}

export type StatsResponse = {
  leaderboard: LeaderboardRow[]
  totals: { games_recorded: number; multiplayer_games: number }
}

export async function fetchStats(): Promise<StatsResponse | null> {
  try {
    const res = await fetch('/api/stats')
    if (!res.ok) return null
    return (await res.json()) as StatsResponse
  } catch {
    return null
  }
}

const PLAYER_ID_KEY = 'hitster:player_id'
const NAME_KEY = 'hitster:name'
const VOLUME_KEY = 'hitster:volume'
const DEFAULT_VOLUME = 0.15

export function getStoredVolume(): number {
  const stored = localStorage.getItem(VOLUME_KEY)
  if (stored === null) return DEFAULT_VOLUME
  const v = parseFloat(stored)
  return Number.isFinite(v) && v >= 0 && v <= 1 ? v : DEFAULT_VOLUME
}

export function setStoredVolume(volume: number): void {
  localStorage.setItem(VOLUME_KEY, volume.toString())
}

export function getStoredPlayerId(): string | null {
  return localStorage.getItem(PLAYER_ID_KEY)
}

export function setStoredPlayerId(id: string): void {
  localStorage.setItem(PLAYER_ID_KEY, id)
}

export function getStoredName(): string {
  return localStorage.getItem(NAME_KEY) ?? ''
}

export function setStoredName(name: string): void {
  localStorage.setItem(NAME_KEY, name)
}

const AVATAR_KEY = 'hitster:avatar'

export function getStoredAvatar(): string {
  return localStorage.getItem(AVATAR_KEY) ?? ''
}

export function setStoredAvatar(avatar: string): void {
  localStorage.setItem(AVATAR_KEY, avatar)
}
