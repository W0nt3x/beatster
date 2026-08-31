# Easter-egg ad images

These PNGs are the fake ads for the room prank. They're auto-collected by
**filename prefix** — drop more in and they join the rotation, no code change.

| Prefix              | Where it shows            | Rotates        | Suggested size |
|---------------------|---------------------------|----------------|----------------|
| `skyscraper-left*`  | left edge (desktop ≥1024) | every 6 s      | 160 × 600      |
| `skyscraper-right*` | right edge (desktop ≥1024)| every 6 s      | 160 × 600      |
| `banner-*`          | bottom banner (all sizes) | every 7 s      | 728 × 90       |
| `popup-*`           | newsletter pop-up         | each time it nags back | ~360 × 300 |

So `skyscraper-left.png`, `skyscraper-left-2.png`, `skyscraper-left-cat.png`
all rotate on the left; `banner-bottom.png`, `banner-2.png` rotate at the
bottom; `popup-1.png`, `popup-2.png`, … cycle in the pop-up. Any number of
files per prefix. Vite bundles + content-hashes them, so cache-busting is
automatic when you change a file.U

To add a slot: just add a file with the right prefix and rebuild. To change
the pop-up nag interval / rotation speeds, see `useRotatingIndex` calls in
`src/Room.tsx`.

## How it's triggered

Type the secret sequence (default **`admob`**) while no text field is focused,
in a room. It toggles the ads for **everyone else** in that room — your own
screen stays clean. Type it again to turn them off. Change the word via
`PROMO_SEQUENCE` in `src/Room.tsx`.
