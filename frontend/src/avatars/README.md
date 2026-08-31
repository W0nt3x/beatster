# Custom avatar catalog (memes welcome)

Drop images named `avatar-*.png` (or `.jpg` / `.webp`) into this folder and
they appear automatically in the avatar picker for everyone — no code change
(same `import.meta.glob` pattern as the fake-ads easter egg).

Guidelines:

- square images, ~256×256 is plenty (they render at 40–72px in a circle)
- the filename (without prefix/extension) is the stable identifier that gets
  stored and synced — renaming a file "logs out" everyone who picked it
- keep it friendly; this ships to the whole friend group
