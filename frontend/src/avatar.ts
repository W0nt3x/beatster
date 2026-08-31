// Avatar rendering: DiceBear styles bundled locally (no external calls).
// Humans all share ONE style — fun-emoji — so the dance floor stays coherent
// (user call 2026-07-24: multiple styles looked chaotic); only the face varies
// (seeded, rerollable). Bots always render as bottts robots. Custom meme
// images can be dropped into src/avatars/ as `avatar-*.png` (auto-collected,
// no code change — same pattern as the ads easter egg); referenced as
// "img:<basename>".
import { createAvatar, type Style } from '@dicebear/core'
import { bottts, funEmoji } from '@dicebear/collection'

export const AVATAR_STYLES = ['fun-emoji'] as const

// the concrete option generics differ per style and don't matter here — we
// only ever pass a seed
type AnyStyle = Style<Record<string, unknown>>
const STYLE_MAP: Record<string, AnyStyle> = {
  'fun-emoji': funEmoji as unknown as AnyStyle,
  bottts: bottts as unknown as AnyStyle,
}

// custom meme catalog: drop avatar-*.png (or .jpg/.webp) into src/avatars/
const customImages = import.meta.glob('./avatars/avatar-*.{png,jpg,jpeg,webp}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

/** basename (without extension) -> bundled url */
export const CUSTOM_AVATARS: Record<string, string> = Object.fromEntries(
  Object.entries(customImages).map(([path, url]) => {
    const base = path.split('/').pop()!.replace(/\.(png|jpe?g|webp)$/i, '')
    return [base, url]
  }),
)

const cache = new Map<string, string>()

function dicebearUri(styleKey: string, seed: string): string {
  const key = `${styleKey}:${seed}`
  const hit = cache.get(key)
  if (hit) return hit
  const style = STYLE_MAP[styleKey] ?? STYLE_MAP['fun-emoji']
  const uri = createAvatar(style, { seed }).toDataUri()
  cache.set(key, uri)
  return uri
}

/** Resolve a player's avatar identifier to an image URL.
 *  Empty identifier = deterministic default: bots get bottts, humans get the
 *  default style seeded by their NAME (same name -> same face on every device). */
export function avatarUrl(
  avatar: string,
  name: string,
  isBot: boolean,
): string {
  if (isBot) return dicebearUri('bottts', name)
  if (avatar.startsWith('img:')) {
    const url = CUSTOM_AVATARS[avatar.slice(4)]
    if (url) return url
  } else if (avatar.includes(':')) {
    const [styleKey, seed] = avatar.split(':', 2)
    if (seed && (AVATAR_STYLES as readonly string[]).includes(styleKey)) {
      return dicebearUri(styleKey, seed)
    }
  }
  return dicebearUri(AVATAR_STYLES[0], name)
}

/** Random seed for the picker's dice roll. */
export function randomSeed(): string {
  return Math.random().toString(36).slice(2, 10)
}
