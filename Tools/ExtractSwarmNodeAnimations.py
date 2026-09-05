"""
Protect the King - 2D
Extracts the 8-frame Swarm Node WALK and ATTACK cycles from the four generated
sprite sheets.

    source : <Downloads>/gamethon pics/design 2d pics/swarmnode pics/*.png  (READ ONLY)
    output : ArtSource/Characters/Enemies/SwarmNode/Frames/{Walk,Attack}/<Dir>/*.png
             ArtSource/Characters/Enemies/SwarmNode/Sheets/*.png

The originals are never renamed, moved, modified or deleted.

Run:  python Tools/ExtractSwarmNodeAnimations.py --measure   (report only)
      python Tools/ExtractSwarmNodeAnimations.py             (write frames)

The generic slicing machinery lives in Tools/ptk_sheet.py. Only the parts that
are actually specific to this creature are here.


WHAT IS DIFFERENT ABOUT SWARM NODE
----------------------------------
Ravager is a humanoid: helmet-to-feet height is a rigid scale reference and the
boots are an obvious ground anchor. A crawling tentacled blob has neither.

* SCALE comes from the CENTRAL EYE, not from body height. The eye is a rigid
  disc that appears at the same size in every pose, whereas the body flattens
  when crawling and rears up when attacking - measuring its height would read a
  pose change as a scale change. The eye is measured only on the four REST
  frames (1, 2, 7, 8); during the strike the beam merges with the eye and the
  blob is no longer the eye.

  Measured rest-frame eye height, in source pixels:

      Walk left/right     36.6      Attack left/right   33.0   <- 11% small
      Walk down/up        37.8      Attack down/up      35.8   <-  5% small

  Three independent metrics agree the left/right attack sheet was drawn small
  (eye 0.89, body height 0.85, sqrt-area 0.91). Left uncorrected, Swarm Node
  would visibly shrink whenever it attacked sideways.

* The UP rows show the creature from behind, where the big eye is hidden and
  only a small node shows. Those rows take the scale measured from their own
  sheet's other row - rows within a sheet always share the generator's scale.

* ANCHOR is the bottom of the dark body mass: where the tentacles meet the
  ground. There are no feet, but the lowest body row is the contact point and
  it is what depth sorting needs.


BACKGROUND
----------
Alpha is already present and bimodal (0 background, ~250 creature), as with the
Ravager animation sheets. No flood fill and no colour key: the creature is
almost black and a colour key would eat it.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet


SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\swarmnode pics"

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARACTER = os.path.join(PROJECT, "ArtSource", "Characters", "Enemies", "SwarmNode")
FRAMES_DIR = os.path.join(CHARACTER, "Frames")
SHEETS_DIR = os.path.join(CHARACTER, "Sheets")

COLUMNS = 8
SHEET_ROWS = 2

# Identified by content, not by filename - the delivered names are GUIDs.
SHEETS = [
    dict(key="Walk_LeftRight",   anim="Walk",   rows=("Left", "Right"),
         file="9ac5a582-d524-49b0-b17f-bc6d1402394f.png"),
    dict(key="Walk_DownUp",      anim="Walk",   rows=("Down", "Up"),
         file="bd7be678-3a49-4afc-8856-3bba964775f9.png"),
    dict(key="Attack_LeftRight", anim="Attack", rows=("Left", "Right"),
         file="0e0e39d2-9992-443c-a778-84f62ef393fc.png"),
    dict(key="Attack_DownUp",    anim="Attack", rows=("Down", "Up"),
         file="dccdf5c5-e4a7-4e69-a0ec-b80bd214c67e.png"),
]

DIRECTIONS = ("Down", "Up", "Left", "Right")

# ---------------------------------------------------------------------------
# Output contract - see Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
# 192x192 with the pivot at (96,179) - identical to Ravager, so the whole
# project has one canvas and one pivot.
#
# 128 was tried first and measured, because Swarm Node's body is small: ~97 px
# wide and ~95 px tall, which fits 128 with room to spare. The body is not what
# decides the canvas. The ATTACK BEAM is: it fires clear of the creature and
# overruns the source cell, reaching 62 px sideways and 115 px above the ground
# anchor. Against the 64/63/118 that 128x128 offers that leaves under 2 px of
# margin, and generating at 128 clipped Attack_Left_03 (12 px) and
# Attack_Left_04 (28 px) at the canvas edge.
#
# 160x160 would also have fitted, with ~18 px to spare. 192 was chosen over it
# because it is one of the project's standard sizes, it matches Ravager exactly,
# and a single canvas + pivot for every character means one spec section, one
# verifier and no per-character pivot to get wrong. The cost is transparent
# padding in a prototype, which is not a real cost.
CANVAS = (192, 192)
PIVOT = (96, 179)

# Finished-frame height of the central eye. Sets Swarm Node's on-screen size:
# 15 px here puts his body at ~95 px, against Ravager's 116 px - a low, wide
# crawler that reads as smaller than the knight without becoming a speck.
TARGET_EYE_HEIGHT = 15.0

SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128

# Frames whose eye is not swallowed by the beam. The attack fires on 3-6.
REST_FRAMES = (0, 1, 6, 7)


def is_effect(r, g, b):
    """The hot red beam and its flare. Deliberately NOT the dark red nodes:
    those are part of the creature and must count as body."""
    return r > 190 and g > 70


def is_core(r, g, b):
    """Glowing red - the central eye and the limb nodes."""
    return r > 170 and r - g > 85 and r - b > 85


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


# ---------------------------------------------------------------------------
# Scale reference: the central eye
# ---------------------------------------------------------------------------
def eye_height(img):
    """Height of the largest connected glowing-red blob - the central eye."""
    from collections import deque
    w, h, px = img.width, img.height, img.px
    mask = bytearray(w * h)
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            if is_core(px[i], px[i + 1], px[i + 2]):
                mask[y * w + x] = 1

    seen = bytearray(w * h)
    best = 0
    best_h = 0
    for start in range(w * h):
        if not mask[start] or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        count = 0
        y0 = h
        y1 = -1
        while queue:
            k = queue.popleft()
            count += 1
            kx, ky = k % w, k // w
            y0 = min(y0, ky)
            y1 = max(y1, ky)
            for nk in ((k - 1) if kx > 0 else -1, (k + 1) if kx < w - 1 else -1,
                       (k - w) if ky > 0 else -1, (k + w) if ky < h - 1 else -1):
                if nk >= 0 and mask[nk] and not seen[nk]:
                    seen[nk] = 1
                    queue.append(nk)
        if count > best:
            best = count
            best_h = y1 - y0 + 1
    return best_h if best else 0


# ---------------------------------------------------------------------------
# Identity - prove each sheet holds what its row order claims
# ---------------------------------------------------------------------------
def core_bias(img):
    """Signed offset of the glowing-core mass from the silhouette centre.
    Negative means the eye leads to the left, i.e. the creature faces LEFT -
    the same sign convention Ravager's axe-energy test uses."""
    w, h, px = img.width, img.height, img.px
    ex = en = sx = sn = 0.0
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            sx += x
            sn += 1
            if is_core(px[i], px[i + 1], px[i + 2]):
                ex += x
                en += 1
    if not sn or not en:
        return 0.0
    return (ex / en - sx / sn) / w


def core_fraction(img):
    """Share of the silhouette that glows. The front view shows the big central
    eye; the back view hides it, so Down always outscores Up."""
    w, h, px = img.width, img.height, img.px
    lit = seen = 0
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            seen += 1
            if is_core(px[i], px[i + 1], px[i + 2]):
                lit += 1
    return lit / float(seen) if seen else 0.0


def verify_identity(spec, cells):
    if spec["rows"] == ("Left", "Right"):
        left = sum(core_bias(cells[0][c]) for c in REST_FRAMES) / len(REST_FRAMES)
        right = sum(core_bias(cells[1][c]) for c in REST_FRAMES) / len(REST_FRAMES)
        if not (left < 0.0 < right):
            fail("{0}: row 0 should face LEFT and row 1 RIGHT, but the core bias "
                 "reads {1:+.3f} / {2:+.3f}".format(spec["key"], left, right))
        return "core bias row0={0:+.3f} (Left) row1={1:+.3f} (Right)".format(left, right)

    down = sum(core_fraction(cells[0][c]) for c in REST_FRAMES) / len(REST_FRAMES)
    up = sum(core_fraction(cells[1][c]) for c in REST_FRAMES) / len(REST_FRAMES)
    if not down > up:
        fail("{0}: row 0 should face DOWN (eye visible) and row 1 UP, but the core "
             "fraction reads {1:.4f} / {2:.4f}".format(spec["key"], down, up))
    return "core fraction row0={0:.4f} (Down) row1={1:.4f} (Up)".format(down, up)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def plan_sheet(spec, grid, cells):
    """Per-sheet scale, per-frame metrics and the anchor scheme."""
    masks = [[ptk_sheet.build_masks(cells[r][c], SRC_ALPHA_THRESHOLD, is_effect)
              for c in range(COLUMNS)] for r in range(SHEET_ROWS)]

    metrics = []
    bounds = []
    for r in range(SHEET_ROWS):
        mrow = []
        brow = []
        for c in range(COLUMNS):
            body, full, w, h = masks[r][c]
            mrow.append(ptk_sheet.ground_anchor(body, w, h))
            brow.append(ptk_sheet.mask_bounds(full, w, h))
        metrics.append(mrow)
        bounds.append(brow)

    # Scale from the eye, measured only on rest frames, and only on rows where
    # the eye actually faces the camera. A row viewed from behind borrows its
    # sheet-mate's value: rows within one sheet share the generator's scale.
    per_row = []
    for r in range(SHEET_ROWS):
        vals = [eye_height(cells[r][c]) for c in REST_FRAMES]
        vals = [v for v in vals if v > 0]
        per_row.append(sorted(vals)[len(vals) // 2] if vals else 0)

    # Take the LARGEST row reading rather than averaging. A row that faces away
    # hides the eye behind the body and can only ever under-measure it - the
    # down/up sheets read 15 and 25 px from behind against 38 and 36 from the
    # front. Averaging those in would shrink the eye and silently inflate the
    # scale; the maximum is the only reading that saw the whole disc.
    eye = max(per_row)
    if eye < 20:
        fail(spec["key"] + ": could not measure the central eye on either row")
    scale = TARGET_EYE_HEIGHT / eye

    anchors = [ptk_sheet.anchors_for_row(metrics[r], hold_still=(spec["anim"] == "Walk"))
               for r in range(SHEET_ROWS)]
    return metrics, bounds, anchors, scale, eye, per_row


def process(spec, measure_only):
    path = os.path.join(SOURCE_DIR, spec["file"])
    if not os.path.isfile(path):
        fail("source sheet missing: " + path)
    sheet = ptk_png.read_png(path)
    grid = ptk_sheet.Grid(sheet, COLUMNS, SHEET_ROWS)
    cells = [[grid.cell(c, r) for c in range(COLUMNS)] for r in range(SHEET_ROWS)]

    identity = verify_identity(spec, cells)
    metrics, bounds, anchors, scale, eye, per_row = plan_sheet(spec, grid, cells)

    log("")
    log("=" * 76)
    log("{0}  <-  {1}".format(spec["key"], spec["file"]))
    log("  {0}x{1}, cell {2:.1f}x{3}, identity: {4}".format(
        sheet.width, sheet.height, grid.cell_w, grid.cell_h, identity))
    log("  eye {0:.1f}px (rows {1})  ->  scale x{2:.4f}  ->  target eye {3:.0f}px".format(
        eye, per_row, scale, TARGET_EYE_HEIGHT))

    results = []
    for r in range(SHEET_ROWS):
        direction = spec["rows"][r]
        bottoms = [m["bottom"] for m in metrics[r]]
        centres = [m["centre"] for m in metrics[r]]
        heights = [m["height"] for m in metrics[r]]
        log("  row{0} {1:<5s} bottom spread {2:2d}px  centre spread {3:5.1f}px  "
            "bodyH {4}..{5} -> {6:.0f}px".format(
                r, direction, max(bottoms) - min(bottoms),
                max(centres) - min(centres), min(heights), max(heights),
                (sum(heights) / 8.0) * scale))

        if measure_only:
            l, rt, u, d = ptk_sheet.required_extent(
                metrics[r], anchors[r], bounds[r], scale)
            log("        needs left={0:.1f} right={1:.1f} up={2:.1f} down={3:.1f}"
                "   (canvas gives {4} / {5} / {6} / {7})".format(
                    l, rt, u, d, PIVOT[0], CANVAS[0] - PIVOT[0] - 1,
                    PIVOT[1], CANVAS[1] - PIVOT[1] - 1))
            continue

        out_dir = os.path.join(FRAMES_DIR, spec["anim"], direction)
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)

        for c in range(COLUMNS):
            ax, ay = anchors[r][c]
            ox, oy = grid.origin(c, r)
            frame = ptk_sheet.render_frame(
                sheet, ox, oy, grid.cell_w, grid.cell_h,
                ax, ay, scale, CANVAS, PIVOT)
            ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
            dropped = ptk_sheet.keep_connected(frame, (PIVOT[0], PIVOT[1] - 30))
            clipped = ptk_sheet.border_contact(frame)
            name = "{0}_{1}_{2:02d}.png".format(spec["anim"], direction, c + 1)
            ptk_png.write_png(os.path.join(out_dir, name), frame)
            results.append(dict(name=name, dropped=dropped, clipped=clipped))
            note = ""
            if dropped:
                note += "  spill removed {0}px".format(dropped)
            if clipped:
                note += "  CLIPPED {0}px".format(clipped)
            log("    {0}{1}".format(name, note))

    return results


def build_contact_sheet(spec):
    cw, ch = CANVAS
    out = ptk_png.Image(cw * COLUMNS, ch * SHEET_ROWS)
    for r, direction in enumerate(spec["rows"]):
        for c in range(COLUMNS):
            path = os.path.join(FRAMES_DIR, spec["anim"], direction,
                                "{0}_{1}_{2:02d}.png".format(spec["anim"], direction, c + 1))
            out.paste(ptk_png.read_png(path), c * cw, r * ch)
    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    name = "SwarmNode_{0}_8F.png".format(spec["key"])
    ptk_png.write_png(os.path.join(SHEETS_DIR, name), out)
    log("  sheet  {0}  ({1}x{2})".format(name, out.width, out.height))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", action="store_true",
                        help="report geometry and required canvas, write nothing")
    args = parser.parse_args()

    log("Swarm Node animation extraction")
    log("source: " + SOURCE_DIR + "  (read only)")

    every = []
    for spec in SHEETS:
        every.extend(process(spec, args.measure) or [])
        if not args.measure:
            build_contact_sheet(spec)

    if args.measure:
        return

    log("")
    log("=" * 76)
    log("{0} frames written".format(len(every)))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED at canvas edge: " + ", ".join(
            "{0} ({1}px)".format(r["name"], r["clipped"]) for r in clipped))
    else:
        log("no frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
