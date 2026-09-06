# Protect the King — 2D · Sprite Specification

**This document is the contract between art and code for all 11 characters.**

Ravager is the reference implementation. Every character listed below is prepared
exactly the same way — only the pixels change.

| Tier | Characters |
|---|---|
| Guards | Ravager, Aegis, Wraith, Reaver, Sentinel |
| King | King |
| Enemies | Swarm Node, Infiltrator, Hijacker, Encrypter, Exfiltrator |

---

## 1. Canvas

| Property | Value |
|---|---|
| Frame size | **192 × 192 px** |
| Format | **PNG, RGBA (32-bit)** |
| Background | **Fully transparent** (alpha 0) |
| Colour space | sRGB |

Every frame of every character — idle, walk and attack alike — uses the same canvas
size. The character does **not** need to fill the frame; consistent *alignment*
matters far more than coverage.

### Per-character canvas exceptions

Width is 192 for everyone. Height grows only where a measured animation does not
fit, and when it does the extra pixels are added so the pivot **stays put** — a
character whose feet moved between animations would visibly hop.

| Character | Animations | Canvas | Pivot | Why |
|---|---|---|---|---|
| Ravager, Swarm Node | idle, walk, attack | 192 × 192 | (96, 179) | baseline |
| Ravager, Swarm Node | death | 192 × 208 | (96, 179) | a corpse settles **below** the line its feet stood on — Ravager's axe drops flat and reaches 17 px under the standing feet row, against the 12 px a 192-tall canvas leaves. The 16 px is added to the BOTTOM only. |
| **King** | all five states | **192 × 232** | **(96, 208)** | his power cast throws a starburst **195 px above** his feet, and his death collapse reaches 15 px below. One canvas is used for every King state so the sprite never changes size mid-fight. |
| Aegis, Wraith | idle, walk, attack, death | 192 × 192 | (96, 179) | baseline. Aegis's raised mace and Wraith's drawn bow both clear it — measured worst case is 118 px above the feet against the 179 available. Their weight is in width, not height. |
| **Wraith's arrow** | flight, impact | **129 × 129** | **(64, 64)** | a projectile is the one thing in this project that does **not** pivot on its feet — it has none. See below. |

The King's frames are the tallest in the project and use the most headroom of
anyone; he still only needs 47 px either side of the pivot, so the shared 192
width is mostly margin for him.

### Projectiles pivot on their centre, on an odd-sized square

A character pivots on its feet because that is what makes it stand on a point.
A projectile pivots on its **centre**, so that the actor location *is* the
arrow — which is what keeps the flight sweep, the impact position and the drawn
sprite agreeing with one another.

The canvas is **square and odd-sized** (129, not 128) on purpose. An odd size
has a true centre pixel, and that is what lets the four directions be **exact
90-degree rotations** of a single drawing: a lossless index permutation, baked
at extraction time by `Tools/ExtractWraithAnimations.py`. Rotating the sprite
component at runtime instead would resample pixel art, and mirroring it would
be wrong for any projectile that is not symmetric about its own axis.

The impact burst is **non-directional** — it is radial, so one set of frames
serves every direction, centred on its own bright core rather than on the cell.

### Why 192 × 192

> **Changed from 128 × 128 on 2026-09-05, when the walk and attack art arrived.**

128 × 128 was sized from the idle pose alone, and it fitted: Ravager's body is
117 px from helmet to boots and his idle silhouette spans 87 px. Animation broke it.
Measured worst cases across all 68 finished frames, in pixels from the feet anchor:

| Animation | left | right | above feet | below feet |
|---|---|---|---|---|
| Idle | 42 | 44 | 117 | 8 |
| Walk | 70 | 71 | 120 | 1 |
| **Attack** | **78** | **72** | **152** | 8 |

A 128 px canvas with the pivot at (64, 119) offers 64 left, 63 right, 119 above and
8 below. The walk axe overruns it by 7 px and the **raised attack axe by 33 px**.

The overflow is not the glow — masking every energy pixel out still needs 173 px of
width, because it is the axe head itself, held out horizontally during the walk and
lifted over the helmet during the attack.

That leaves exactly two ways to reach 128, and both are forbidden by this document:
shrink Ravager during the animation (§6: scale must be identical across all frames),
or crop the axe. So the canvas grew instead.

**Nothing about the character changed.** Ravager is drawn at the same size, on the
same feet anchor, in every frame; there is simply more transparent padding around
him. Paper2D stores a pivot per sprite, so the extra padding costs nothing at
runtime beyond texture memory.

> **Open dependency — tile scale.** The canvas is sized from the character
> silhouette, because no map reference has been supplied yet. Once the real map
> exists, check that a character reads correctly against its tiles. Authoring tiles
> at **32 px or 64 px** keeps Ravager about 2–3 tiles tall, the normal proportion
> for this genre. If the map uses a very different tile size, the value to revisit
> is the character's **body height** (§3), not the canvas — and it must be changed
> **here**, once, not per-asset.

---

## 2. The feet anchor (pivot)

**This is the single most important rule in this document.**

| Property | Value |
|---|---|
| Pivot mode | `Custom` |
| Pivot point | **(96, 179)** in texture pixels, measured from the top-left |

That is: horizontally centred, and **12 px above the bottom edge** of the canvas.

> **History.** (64, 120) → (64, 119) on 2026-09-04 when the real idle art was
> measured; → **(96, 179)** on 2026-09-05 when the canvas grew to 192 × 192.
> The last change moved the pivot by exactly +(32, 60) — the same offset the canvas
> grew by — so the feet did not move relative to the artwork at all. The existing
> idle frames were re-framed by pasting them at that offset: not one pixel was
> resampled, recoloured or shifted.

```
   0                96              191
 0 ┌────────────────┬────────────────┐
   │                                 │
   │   (raised axe reaches row 27)   │
   │                                 │
   │            (character)          │
   │                                 │
179 ├────────────────●────────────────┤   ← feet contact row, pivot
   │  (12 px: shadows, or weapon     │
191└────overhang such as the axe)────┘
```

### Rules for the artist

1. The character's **feet contact point** — where they touch the ground — must sit
   on **row 179** in *every single frame*, of every animation.
2. Row 179 is the lowest row the character's **body** occupies. The 12 px below it
   are for ground shadows and dust — and for weapon overhang, which takes
   priority: Ravager's axe blade legitimately hangs below his boots in the Down
   view, and must never be cropped to make room for a shadow.
3. The character must be horizontally centred on **column 96**.
4. This holds across directions *and* across animation frames. A walk cycle may bob
   the head and torso, but the planted foot stays on row 179.
5. An attack may lunge — the body genuinely travels during a swing, and that motion
   is kept. What must not happen is the *rest* pose sitting somewhere else: attack
   frame 01 has to line up with idle, or the character will jump the moment the
   player presses the attack key.

### Why it matters

The sprite pivot is the point Unreal aligns to the character's world position. If two
frames disagree about where the feet are, the character **jumps vertically** the
instant the flipbook switches — going Idle → Walk, Left → Up, or Walk → Attack.
Because the pivot is identical in all 68 frames, that cannot happen.

`Tools/VerifyRavagerFrames.py` enforces this: it re-measures every finished frame and
fails if the feet drift off the pivot row, if body height varies between idle, walk
and attack, or if a walk cycle slides sideways. Run it on every future character.

---

## 3. Scale and Pixels Per Unreal Unit

| Property | Value |
|---|---|
| **Pixels Per Unreal Unit** | **1.0** (1 source pixel = 1 Unreal unit) |
| Set globally in | `Config/DefaultEditor.ini` → `[/Script/Paper2DEditor.PaperImporterSettings]` |

Consequences of this convention, all of which are intentional:

- A 128 px frame is 128 uu tall.
- Camera `OrthoWidth` is a **direct pixel count** — 960 means 960 source pixels visible.
- Movement speeds read as **pixels per second** (Ravager's 240 = 240 px/sec).
- Collision sizes read as pixels (Ravager's capsule is a 28 × 28 px footprint).

**Never rescale an individual sprite or actor to compensate for anything.** If the
scale is wrong, it is wrong for the whole project and belongs in the config file.
Per-asset scale fixes are how a project ends up with 11 characters at 11 sizes.

---

## 4. Naming

### Source PNG files

Delivered into `ArtSource/Characters/<Tier>/<Character>/Frames/`, filed by animation
and direction. 68 frames in one flat folder is unreadable; this shape scales to all
eleven characters.

```
Frames/
  Idle/            Idle_Down.png  Idle_Up.png  Idle_Left.png  Idle_Right.png
  Walk/
    Down/          Walk_Down_01.png  ...  Walk_Down_08.png
    Up/            Walk_Up_01.png    ...  Walk_Up_08.png
    Left/          Walk_Left_01.png  ...  Walk_Left_08.png
    Right/         Walk_Right_01.png ...  Walk_Right_08.png
  Attack/
    Down/          Attack_Down_01.png  ...  Attack_Down_08.png
    Up/            Attack_Up_01.png    ...  Attack_Up_08.png
    Left/          Attack_Left_01.png  ...  Attack_Left_08.png
    Right/         Attack_Right_01.png ...  Attack_Right_08.png
```

Frame numbers are **two digits, 1-based** (`01`…`08`). Exact spelling and
capitalisation — the import script matches these names literally.

Normalised contact sheets are also written to `.../<Character>/Sheets/`:

```
Ravager_Walk_LeftRight_8F.png     1536 × 384   8 columns × 2 rows of 192 × 192
Ravager_Walk_DownUp_8F.png        1536 × 384
Ravager_Attack_LeftRight_8F.png   1536 × 384
Ravager_Attack_DownUp_8F.png      1536 × 384
```

Sheet row order is **row 1 = Left / Down, row 2 = Right / Up**. The sheets are a
review aid only; the engine imports the individual frames.

### Generated Unreal assets

| Asset | Pattern | Example |
|---|---|---|
| Texture | `T_<Character>_<FrameName>` | `T_Ravager_Attack_Left_05` |
| Sprite | `SPR_<Character>_<FrameName>` | `SPR_Ravager_Attack_Left_05` |
| Flipbook | `FB_<Character>_<State>_<Direction>` | `FB_Ravager_Attack_Left` |

---

## 5. Required frames

| State | Directions | Frames each | Total |
|---|---|---|---|
| Idle | Down, Up, Left, Right | 1 | **4** |
| Walk | Down, Up, Left, Right | 8 | **32** |
| Attack | Down, Up, Left, Right | 8 | **32** |
| | | | **68** |

### The King is the exception: no directions at all

The King is a **fixed objective**. He never walks, never turns to face anything
and is never possessed, so none of his animations are directional — each is a
single sequence, stored flat in `Frames/<State>/<State>_NN.png` with no
direction subfolder.

| State | Directions | Frames | FPS | Loops |
|---|---|---|---|---|
| Idle | — | 8 | 8 | yes |
| Alert | — | 8 | 10 | yes |
| PowerCast | — | 8 | 12 | no, one shot |
| Death | — | 8 | 9 | no, holds last frame |
| | | **32** | | |

There is **no Walk state for the King, and there never will be.** There is also
no Hit sheet: none was supplied, so `HitFlipbook` is left empty and
`APTKKingCharacter` falls back to the Alert reaction rather than inventing art.

> **The 4-frame walk plan is obsolete.** It was superseded on 2026-09-05. Any tooling
> or document still referring to 4 walk frames per direction is stale.

Do not author hit, death or special animations yet — the state machine that would
drive them does not exist.

### Direction meanings

| Direction | The character is facing… |
|---|---|
| `Down` | toward the camera (front view) |
| `Up` | away from the camera (back view) |
| `Left` | screen-left (side view) |
| `Right` | screen-right (side view) |

`Left` and `Right` are **separate hand-drawn frames**, not mirrored copies. Mirroring
flips asymmetric details — Ravager's axe would jump from one hand to the other. If a
character is genuinely symmetrical, mirroring is acceptable, but it is a per-character
decision made by the artist, never an automatic engine step.

> **Never trust a delivered sheet's row labels for Left vs Right.** The Ravager
> turnaround arrived with them the other way round. Verify from the artwork — helmet
> orientation, axe side, cape direction. `Tools/ExtractRavagerAnimations.py` does this
> automatically and refuses to run if a sheet contradicts its mapping: it measures
> where the axe-energy mass sits relative to the silhouette centre (negative = Left,
> matching the known-good `Idle_Left`), and for Down/Up it measures visor glow in the
> head band, which is bright from the front and dark from behind.

### Walk cycle structure — 8 frames

| Frame | Pose |
|---|---|
| `01` | contact |
| `02` | transition |
| `03` | passing |
| `04` | opposite contact |
| `05` | transition |
| `06` | passing |
| `07` | recovery |
| `08` | loop preparation |

Frame 08 must lead cleanly back into frame 01 — check that transition specifically,
it is the one join a linear contact sheet hides.

### Attack sequence structure — 8 frames

| Frame | Pose |
|---|---|
| `01` | ready |
| `02` | anticipation |
| `03` | strong wind-up |
| `04` | swing begins |
| `05` | **main impact** |
| `06` | follow-through |
| `07` | recovery |
| `08` | return toward ready |

Frame `05` must read unmistakably as the strongest pose. Blue energy and slash
effects are valid around frames `04`–`06`, but they must stay controlled and
readable.

> **Slash effects are art, never collision.** When damage is implemented, the logical
> hit frame is `Attack_*_05`. Nothing is implemented yet — this phase is animation
> only: no damage, health, hitboxes, knockback, cooldowns or combos.

---

## 6. Consistency requirements

Across all 68 frames of a character, these must be identical:

- canvas size (192 × 192)
- **character scale and proportions** — see the warning below
- the top-down / three-quarter viewing angle
- armour, weapon, silhouette and palette
- feet position (row 179, column 96)

> **Scale is the one that bites.** Ravager's four delivered sheets were *not* drawn
> at the same scale: he is ~296 px tall on the walk sheets but only ~240 px on the
> attack sheets — a ratio of 0.82. Sliced naively he would have shrunk by a fifth the
> instant he attacked. Each sheet therefore gets its own scale factor, computed so
> every finished frame lands on the same body height.
>
> Always measure helmet-to-feet height per sheet before slicing. Do not assume that
> art delivered together shares a scale.

And every frame must have:

- a fully transparent background — **no** background colour, gradient or checkerboard
- **no** text, watermarks, labels, frame numbers or borders
- hard alpha edges — see below

### Transparency

Use **hard (binary) alpha**: a pixel is either fully opaque or fully transparent.

Soft anti-aliased alpha edges fight with nearest-neighbour filtering and produce
halos when the camera moves. Pixel art gets its edge quality from deliberate pixel
placement, not from alpha blending. Hard alpha also lets Unreal pick the *masked*
sprite material, which writes depth and therefore sorts correctly against other
sprites — translucent materials do not.

---

## 7. Unreal import settings

Applied automatically by `Tools/PTK_GenerateAssets.py`. Listed here so they can be
verified by hand, and so nobody "fixes" them into something blurry.

### Texture

| Setting | Value | Why |
|---|---|---|
| Filter | **Nearest** | Bilinear filtering turns pixel art into mush |
| Mip Gen Settings | **NoMipmaps** | Mips blur the sprite as the camera moves |
| Compression Settings | **UserInterface2D** (`TC_EditorIcon`) | Uncompressed RGBA; DXT causes colour bleed and dirty alpha |
| Texture Group | **Pixels2D** | Point sampling, no LOD bias |
| sRGB | **On** | Colours must round-trip as authored |
| Never Stream | **On** | No pop-in on first appearance |

### Sprite

| Setting | Value |
|---|---|
| Pixels per unit | **1.0** |
| Pivot Mode | **Custom** |
| Custom Pivot Point | **(96, 179)** |
| Snap pivot to pixel grid | **On** |
| Collision domain | **None** (the capsule is the gameplay footprint) |

### Flipbook

| Animation | Frames | FPS | Duration |
|---|---|---|---|
| Idle | 1 | 8 | — |
| Walk | 8 | **10** | 0.80 s per stride |
| Attack | 8 | **12** | 0.67 s per swing |

`Frame Run` is **1** on every key frame.

10 FPS is the starting point for readable pixel-art walking — fast enough to feel
alive, slow enough that individual frames register. Try **8 / 10 / 12** and keep what
reads best. The attack is deliberately faster so the swing lands with more force;
do not push it much past 12 or the wind-up stops registering.

Tune via the flipbook asset, or at runtime via `IdlePlayRate` / `WalkPlayRate` /
`AttackPlayRate` on the character.

> **Playback rate and movement speed are independent, and must stay that way.**
> Never change `MaxMoveSpeed` to make the walk cycle look right, or vice versa. The
> attack's state duration is derived from the flipbook length divided by
> `AttackPlayRate`, so raising the rate shortens the state to match what is on
> screen automatically.

---

## 8. Rendering conventions the art must respect

### World orientation

Protect the King is a **genuine 2D game**. The three-quarter look lives entirely in
the artwork — it is not produced by tilting a 3D camera. The play plane is world **XZ**:
screen-up is `+Z`, the depth axis is `Y`, and the orthographic camera sits at `-Y`
looking toward `+Y`.

Screen-right is therefore `-X`, and the sprite is mirrored back with a negative X
scale on the flipbook component. Both facts are load-bearing and were established by
measurement, not deduction: Paper2D sprites in this project render **only** from the
`-Y` side, so moving the camera to `+Y` makes every character vanish. Do not "correct"
either one — see the comment block in `PTKTopDownCharacter.cpp`.

None of this affects the artist: art is always authored as it should appear on
screen.

**Sprites are never rotated to express direction.** Direction is *only* ever a
flipbook swap. This means the art must actually contain the four viewing angles —
the engine will not and cannot derive them.

### Depth sorting

Characters lower on screen draw in front of characters higher on screen. The engine
handles this by nudging the sprite along the depth axis (`bEnableDepthSorting` on the
character). Because the camera is orthographic, that nudge causes **no** parallax and
**no** size change.

Art implication: draw characters as if standing on the ground at the feet anchor. The
anchor row is what the sorting maths uses as "how far down the screen this character
is standing".

### Collision

Collision is a capsule around the **body and feet only** — Ravager's is 14 uu radius,
14 uu half-height, a 28 × 28 px footprint centred on the feet anchor.

It deliberately excludes the axe, cape, glow and armour spikes. A weapon that
extends 35 px from the body must not make the character collide with walls from
across the room. Art can extend as far outside the capsule as the design wants.

---

## 9. Preparing a new character

Once Ravager is signed off, every remaining character follows this exact path. Note
that **no new C++ is written** — that is the entire point of the architecture.

1. **Author the 68 frames** to this spec.
   → `ArtSource/Characters/<Tier>/<Character>/Frames/`
2. **Point the generator at the character.** Copy the direction/name tables in
   `Tools/PTK_GenerateAssets.py` and change the character name; the import, pivot,
   filtering and flipbook steps are already generic.
3. **Create the Blueprint.** Right-click → Blueprint Class → parent:
   - `PTKGuardCharacter` for a playable guard
   - `PTKTopDownCharacter` for the King or an enemy
4. **Assign the 12 flipbooks** in the Blueprint's `PTK|Animation` section
   (`IdleFlipbooks`, `WalkFlipbooks` and `AttackFlipbooks`, four directions each).
   Leave `AttackFlipbooks` empty for a character that cannot attack — `StartAttack()`
   then refuses cleanly instead of freezing them in a state with nothing to play.
5. **Set the character's tuning values:**
   - `PTK|Movement` → `MaxMoveSpeed`
   - `PTK|Collision` → `CollisionRadius`, `CollisionHalfHeight`
   - `PTK|Guard` → `GuardId`, `GuardDisplayName` (guards only)
6. **Assign input** (player-controlled characters only):
   `PTK|Input` → `MoveAction` = `IA_Move`, `AttackAction` = `IA_Attack`,
   `DefaultMappingContext` = `IMC_PTK_Default`
7. **Drop it in the test level and check** the acceptance list below.

### Per-character acceptance checklist

- [ ] All four directions show the correct animation
- [ ] Diagonals are not faster than cardinals
- [ ] Releasing all keys keeps the last facing direction
- [ ] No vertical jump when switching Idle ↔ Walk ↔ Attack, or between directions
- [ ] Attack plays all 8 frames, is not interrupted, and returns to the right state
- [ ] Sprite is sharp — no blur, no halo
- [ ] Collision matches the body, not the weapon

---

## 10. Delivery checklist for a character

- [ ] 68 PNG files, exact names and folders from §4
- [ ] Every file 192 × 192
- [ ] Every file RGBA with a transparent background
- [ ] Feet contact point on row 179, centred on column 96, in every frame
- [ ] **Identical body height across idle, walk and attack** — measure, do not assume
- [ ] Hard alpha edges, no anti-aliased fringing
- [ ] No text, no watermark, no background
- [ ] Consistent armour, weapon, palette and proportions across all 68
- [ ] `Left` and `Right` drawn separately if the character is asymmetric
- [ ] `Left`/`Right` verified from the artwork, not from the sheet's row labels
- [ ] `Tools/VerifyRavagerFrames.py` (adapted) reports 0 failures

---

## 11. Preparing frames from a high-resolution turnaround sheet

The concept sheets in `gamethon pics/design 2d pics/` are **pixel-art-styled
renders, not native-resolution pixel art**. Measured on `ravager.png`:

| Measurement | Value | What it means |
|---|---|---|
| Sheet size | 1448 × 1086, 8-bit RGB | no alpha channel at all |
| Horizontal run lengths (row 400) | 968 runs of length 1 | there is **no** pixel grid |
| Unique colours (sampled) | ~50,000 | a detailed render, not a limited palette |
| One character view | ~466–470 px tall | ~4× larger than the 128 px target |

This distinction matters, because it changes the correct resampling rule.

### Background removal — flood fill, never a colour key

The backdrop measures **(12, 16, 21)** with a range of only ±3 per channel, but
Ravager's armour contains **15,000+ pixels that are themselves within tolerance of
that colour**. A plain colour key would punch thousands of holes straight through him.

Use a **flood fill inward from the image border** instead. Connectivity, not colour
alone, is what separates backdrop from dark armour. Measured tolerance behaviour:

| Tolerance | Background captured | Verdict |
|---|---|---|
| 6 | 75.80% | safe |
| 10 | 76.31% | safe |
| **14** | **77.12%** | **used — middle of the stable plateau** |
| 24 | 83.38% | starts eating the character |
| 32 | 88.29% | destroys the character |

The plateau between 6 and 14 moves by only 1.3%, which is what makes 14 a safe
choice rather than a guess. Edges are hard: a scanline across the silhouette goes
from distance 2.4 (background) to 18.7 (character) within **two pixels**.

Alpha is written as **strictly 0 or 255**. No feathering is performed anywhere, so
semi-transparent halos are impossible by construction — verified as
`semi-alpha = 0` on all four extracted frames.

### Downscaling — area average, not nearest neighbour

> **This is the one place the "nearest-neighbour only" rule does not apply, and it
> is deliberate.**

That rule is correct when the source is *already* pixel art at its native
resolution — resampling it any other way destroys the artist's chosen pixels. This
source is a 1448 px render being reduced **4×**, where nearest neighbour keeps 1
pixel in every 16 and throws the other 15 away. The result is not "crisp", it is
*aliased*: helmet horns fragment, gold trim becomes dotted, and pauldrons speckle.

Compare for yourself: `Docs/ravager_zoom_box_vs_nearest.png` (6× zoom, box on top).

What is used instead:

- RGB is **area-averaged over a 4 × 4 block**, counting **opaque pixels only**, so
  the transparent backdrop can never bleed into edge colours.
- Alpha is **thresholded to 0 or 255** — a block is opaque when at least 6 of its
  16 source pixels are. Edges stay hard and no halo can form.

So the parts of the rule that protect sprite quality — hard edges, no halos, no
background bleed — are all still enforced. Only the RGB resampling differs.

Nearest neighbour remains one flag away for comparison:

```
python Tools/ExtractRavagerIdle.py --mode nearest
```

### Anchoring a view

The **helmet centre** is used as the horizontal anchor, not the boots, because the
axe occludes or merges with the boots in three of Ravager's four views. In the one
view where the boots *are* cleanly measurable (Up), the two agree to within 4 source
pixels — 1 pixel after the 4× reduction.

Feet rows must be **measured per view and confirmed visually**. They cannot be taken
from the bounding box: Ravager's Down view has a bounding box 32 px taller than his
body because the axe blade hangs below his boots.

### Tools

| Script | Purpose |
|---|---|
| `Tools/ptk_png.py` | dependency-free PNG read/write (no Pillow or numpy on this machine) |
| `Tools/ExtractRavagerIdle.py` | idle extraction from the turnaround sheet + verification |
| `Tools/ExtractRavagerAnimations.py` | walk + attack extraction from the animation sheets |
| `Tools/VerifyRavagerFrames.py` | validates all 68 finished frames before import |
| `Tools/BuildRavagerComparison.py` | renders the alignment/quality comparison sheet |

Source images in `Downloads` are treated as **read-only**. A byte-identical copy of
each sheet is archived into the character's `Concept/` folder.

---

## 12. Preparing frames from an animation sheet

The walk and attack art arrives as four sheets, each **2172 × 724 RGBA**, laid out
**8 columns × 2 rows** on a cell pitch of 271.5 × 362.

| Sheet | Row 1 | Row 2 |
|---|---|---|
| Walk, left/right | Left | Right |
| Walk, down/up | Down | Up |
| Attack, left/right | Left | Right |
| Attack, down/up | Down | Up |

The delivered filenames are opaque GUIDs and carry no meaning. Identify each sheet
from its **content** — `ExtractRavagerAnimations.py` does this and refuses to run on
a sheet that contradicts its mapping.

### These sheets already have alpha

Unlike the turnaround sheet, alpha here is bimodal: 0 for background, 249–253 for
Ravager, with a thin anti-aliased rim. There is no presentation backdrop to flood
fill, **and no colour key is used anywhere** — so the "dark armour shares colours
with the dark background" failure mode of §11 cannot occur.

Alpha is resolved to hard 0/255 after downscaling. The runtime material is
`MaskedUnlitSpriteMaterial`, which thresholds anyway; making the cut in the pipeline
means what ships is exactly what renders.

### The four things that must be corrected

Each was measured, and each would be a visible defect if ignored.

**1. Sheets are not all at the same scale.** Ravager is ~296 px tall on the walk
sheets and ~240 px on the attack sheets. Every sheet gets its own scale factor,
targeting one common body height (116 px — the existing idle art).

**2. The walk sheets drift; the attack sheets do not.** On the left/right walk sheet
the body centre slides monotonically ~38 px across the eight frames — played back,
the sprite slides sideways and snaps home at the loop point. That is generator drift
and must go. On the attack sheets the centre wanders just as far but **returns to its
starting value on frame 8** — that is the lunge into the strike, and it must stay.

The test is whether the motion returns to where it began:

| | Anchoring | Result |
|---|---|---|
| Walk | **per frame** — planted foot to the pivot | drift removed, foot-plant and bob kept |
| Attack | **once per row** — from the frames 1 / 8 rest pose | lunge kept, rest pose still on the pivot |

**3. Frames do not fit the source cell.** At matched scale the attack needs 174 px of
width and 154 px above the feet, against a 271 px cell that is only ~135 px wide once
scaled. Sampling must be allowed to read *outside* the cell, fenced to 0.66 of a cell
either side of the anchor — past everything of ours, clear of the neighbour's body
at ~221 px.

**4. The slash FX crosses into the neighbouring cell.** On both attack sheets the blue
arc of frames 4–6 spills sideways. After sampling, keep only the pixels connected to
this frame's own silhouette; the neighbour's spill is disconnected and drops out.

### Sampling

Work **backwards from the output**: for each destination pixel, compute the source
box it came from and area-average it. The anchor then lands on the pivot to sub-pixel
accuracy with no intermediate resample, so no rounding error can re-introduce the
jitter the pipeline exists to remove.

Colour is averaged **premultiplied**, so the transparent background cannot bleed a
dark fringe into the silhouette edge.

### Verification is not optional

`Tools/VerifyRavagerFrames.py` re-measures every finished frame and reports:

| Check | Ravager's result |
|---|---|
| 192 × 192, hard 0/255 alpha | 68/68 |
| No opaque pixel on the canvas edge | 68/68 — nothing clipped |
| Feet on the pivot row | 68/68 |
| Body height across idle / walk / attack | drift ≤ 3 px on Up, Left, Right |
| Walk feet spread | **0.0 px** |
| Walk centre spread | ≤ 2.3 px |
| Silhouette area consistency | within band — no lost horns or extra limbs |

Two measurement artefacts are expected and benign: `Idle_Down` reports its "feet"
8 px low because the axe blade hangs below the boots (the same 8 px it always had),
and `Attack_Down_07` sits 8 px high because Ravager genuinely rears back on the
recovery frame.
