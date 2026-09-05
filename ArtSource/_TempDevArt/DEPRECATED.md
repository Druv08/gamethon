# Deprecated development art

Everything under this folder is **superseded and unused**. Nothing in the
project references it: no texture is imported from here, no sprite points at
it, and no flipbook contains it.

It is kept only as a record of how the project bootstrapped before the real
artwork existed. Do not wire any of it back into runtime.

## Ravager/

| File | Superseded by |
| --- | --- |
| `Idle_{Down,Up,Left,Right}.png` | `Characters/Guards/Ravager/Frames/Idle/` — real art, extracted from the turnaround sheet |
| `Walk_{Dir}_01..04.png` | `Characters/Guards/Ravager/Frames/Walk/<Dir>/Walk_<Dir>_01..08.png` |

These were flat-coloured red and green dummies used to prove that direction
selection, the flipbook swap and the pivot all worked before any Ravager
artwork existed. They were 128×128; the project now uses 192×192.

The 4-frame walk plan they were built for is obsolete. Ravager's walk is
8 frames per direction, and he also has an 8-frame attack per direction.

## Why they are still here

Deleting them would remove the only evidence of what the placeholder pipeline
looked like, and they cost a few kilobytes. If you want them gone, delete the
whole `_TempDevArt` folder — nothing will break.
