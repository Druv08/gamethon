# Phase 1 — Status

_Last updated: 2026-09-05 (movement direction + placeholder-art bugs fixed)_

## Toolchain — resolved

| Item | Value |
|---|---|
| Visual Studio | Community **2026**, 18.9.12120.119 |
| MSVC selected by UBT | **14.50.35717** (compiler 14.50.35737) — UE 5.8.1's *preferred* toolset |
| Windows SDK | 10.0.26100.0 |
| Unreal Engine | 5.8.1 (`++UE5+Release-5.8`, CL 56057345) |

14.51 is also installed but UBT ranks it `FamilyRank 2` (not in
`PreferredVisualCppVersions`), so 14.50 wins automatically. No compiler warning.

## Build

`ProtectTheKing2DEditor · Win64 · Development` — **compiles and links clean.**

Three genuine defects were found and fixed, none of them architectural:

| # | Error | Category | Fix |
|---|---|---|---|
| 1 | `C1083: Cannot open include file: 'ProtectTheKing2D.h'` | module/include layout | Module header/impl moved into `Public/` and `Private/`. UBT only puts `Public/`, `Internal/` and `Private/` on the include path — the module root is not included when a Public/Private split exists. |
| 2 | `C2668: AddOnScreenDebugMessage ambiguous` | C++ overload resolution | `GetUniqueID()` returns `uint32`, which converts equally to the `int32` and `uint64` overloads. Added `static_cast<uint64>`. |
| 3 | All WASD moved left (runtime) | see below | two compounding causes, both fixed |

## The all-directions-move-left bug

Two independent faults that happened to combine into one symptom.

**Cause A — Enhanced Input modifiers were not persisted.**
The generator created modifiers with `unreal.InputModifierSwizzleAxis()`, which
produces a **transient** object with no Outer. It assigns and reads back fine in
the same session, but cannot serialise into the asset. On reload every modifier
slot was `null`:

```
[0] key=W  modifiers=['<NULL MODIFIER>']
[1] key=S  modifiers=['<NULL MODIFIER>', '<NULL MODIFIER>']
[2] key=A  modifiers=['<NULL MODIFIER>']
→ W, S, A and D all produced the raw digital value (+1, 0)
```

Fixed by creating each modifier with the mapping context as its Outer:
`unreal.new_object(unreal.InputModifierSwizzleAxis, context)`.

**Cause B — the movement basis assumed screen-right was +X.**
Paper2D sprite normals point down −Y (`PaperAxisZ = (0,-1,0)`), so the camera
*must* look along +Y or every character renders from behind. That forces a boom
yaw of 90°, and a yaw of 90° makes the camera's right vector **world −X**:

```
CameraBoom yaw=90 → right = (-1.00, 0.00, 0.00)
```

So travelling along +X appears to move **left**. The hardcoded
`ScreenRight = (1,0,0)` was therefore backwards.

Fixed by deriving the basis from the camera in `UpdateMovementBasis()`, so the
movement code and the view can no longer disagree even if the rig is re-oriented.

Together: every key produced `(+1, 0)` → pushed along world +X → appeared to
move left. Both are now covered by automated regression checks.

## Ravager art state

| Animation | Source | Status |
|---|---|---|
| `Idle_Down/Up/Left/Right` | `ravager.png` turnaround | ✅ **REAL ARTWORK** |
| `Walk_*` flipbooks | **temporarily reuse the real idle sprite** | ⚠️ placeholder-free |
| `Walk_*_01..04` PNG placeholders | on disk, imported, **unreferenced** | 🚫 cannot reach the screen |

`WALK_USES_IDLE_SPRITE = True` in `Tools/PTK_GenerateAssets.py` makes each
`FB_Ravager_Walk_<Dir>` hold a single frame — the real idle sprite for that
direction. Ravager therefore **slides instead of walking**, which is intentional
and sufficient to validate movement, direction, camera, collision and last-facing.

The 16 placeholder PNGs and their sprites are deliberately **kept, not deleted**,
so the walk cycle can be restored for testing at any time by flipping that flag.

**Next art milestone:** real `Walk_{Down,Up,Left,Right}_{01..04}` — 16 frames to
[SPRITE_SPEC](SPRITE_SPEC.md), dropped into
`ArtSource/Characters/Guards/Ravager/Frames/`. Then set `WALK_USES_IDLE_SPRITE`
to `False` and re-run. Source resolution is per-frame, so frames can land a few
at a time.

## Automated verification

`Tools/PTK_VerifyRuntime.py` — **109 checks, 0 failures.** Covers:

- C++ / Paper2D / Enhanced Input types reflected
- `BP_Ravager` parent class, all 8 flipbooks, `IA_Move`, `IMC_PTK_Default`
- direction detection across the full WASD + diagonal matrix
- last-facing held on zero and dead-zone input
- diagonal normalisation **measured** on a spawned actor (1.0000, not 1.4142)
- key → IA_Move → world vector → **screen direction**, end to end
- every flipbook keyframe confirmed to reference real Ravager art

`Tools/PTK_DiagnoseInput.py` dumps the saved IMC modifiers and camera basis —
run it first whenever input behaves strangely.

## Still requiring a human at the keyboard

The automated chain proves the *mapping*. These need eyes on a running frame:

- [ ] sprite blur / filtering under motion
- [ ] pivot jump between Idle ↔ Walk (now the same sprite, so it should be exact)
- [ ] animation flicker on rapid direction changes
- [ ] collision jitter along walls; the axe must not collide from a distance
- [ ] camera framing at `CameraOrthoWidth` 480 / 720 / 960

Tick `PTK|Debug → Show Debug State` on `BP_Ravager` for a live readout of facing,
state, input vector and velocity projected onto the screen axes.

## Camera note

`CameraOrthoWidth = 960` (temporary). At 1 uu = 1 px and 16:9, screen height is
`OrthoWidth × 9/16`, and Ravager is 117 px tall:

| OrthoWidth | Ravager height | Zoom on a 1920-wide viewport |
|---|---|---|
| 480 | 43% of screen | 4.0× (integer ✅) |
| 720 | 29% of screen | 2.67× (**non-integer ⚠️** — uneven pixels) |
| 960 | 22% of screen | 2.0× (integer ✅) |

**720 is not an integer divisor of 1920**, so it breaks pixel-perfect scaling —
some source pixels become 3 screen pixels and others 2, which shimmers on pixel
art. Prefer **640** (3×) as the middle option instead of 720. Final choice waits
on the real map.

## Known issues

1. Walk is a static pose (intentional, see above) until real walk frames exist.
2. Camera lag is on (`CameraLagSpeed = 12`) — can shimmer pixel art; set
   `PTK|Camera → Use Camera Lag` to false for a locked, perfectly crisp camera.
3. Depth sorting is implemented but untested against real scenery.
4. Enemy turnaround sheets need a different extractor: 2×2 grid with titles,
   captions and decorative borders at 1122×1402, and a different view order.
