"""
Protect the King - 2D
Extracts the King's four supplied animations into finished Paper2D frames.

    source : <Downloads>/gamethon pics/design 2d pics/king pics/*.png  (READ ONLY)
    output : ArtSource/Characters/King/Frames/<Anim>/<Anim>_01..08.png
             ArtSource/Characters/King/Sheets/King_<Anim>_8F.png

Run:  python Tools/ExtractKingAnimations.py --measure
      python Tools/ExtractKingAnimations.py

Uses the shared machinery in Tools/ptk_sheet.py.


WHICH SHEET IS WHICH
--------------------
The four source files carry UUID names that say nothing, so every sheet was
identified by looking at it, never by its filename:

  07099154  a blue aura swells from nothing at frame 1 to a full envelope at
            frame 5 and returns to nothing by frame 8, while the body pose does
            not change at all           -> IDLE (it is a loop, and it is the
            "glowing core pulse" the brief describes)
  e5cf2b3c  comic emphasis strokes flick out beside his head, his face turns
            from calm to a scowl and he braces                 -> ALERT
  8bb300d4  staff raised overhead, a gold starburst peaks at frame 5, then
            settles back to the opening pose                   -> POWERCAST
  70e80680  he sags, drops to his knees, the staff falls out of his hand and
            he ends as a heap on the floor                     -> DEATH

King.png in the same folder is a 1448x1086 RGB turnaround (front / back / two
profiles) with no alpha. It is a design reference, not an animation, so nothing
is extracted from it.

No HIT sheet was supplied. One is NOT invented here - see the report.


THE THREE CORRECTIONS THIS CHARACTER NEEDED
-------------------------------------------
1. SCALE. The four sheets are drawn at four different sizes. Neither of the
   usual rigid landmarks works on him: the cape billows, so silhouette width is
   not rigid, and the staff is a held prop drawn at a different height per
   sheet, so overall height is not rigid either. What IS true is that frame 1
   of all four sheets is the same neutral standing pose - so the scale is
   solved for directly, by finding the factor that maximises silhouette overlap
   against the Idle sheet. That needs no landmark at all. Measured this way the
   sheets are drawn at +0.0 / +4.2 / -9.9 / +3.1 percent, and the Idle sheet is
   the reference. Left uncorrected the King would visibly change size the
   instant he reacted to anything.

2. ANCHORING. Every animation uses ONE fixed anchor taken from frame 1, not a
   per-frame anchor. Two independent reasons:
     - The King is stationary by design, and the source art is already
       registered to the pixel: the ground contact moves by at most 1 px across
       a whole sheet. There is no placement jitter to correct, so a per-frame
       anchor could only add error.
     - His centroid swings by up to 39 px as the cape billows and the aura
       flares. Re-centring on that every frame would drag him sideways - it
       would invent movement in the one character who must never move.
   The horizontal anchor of each sheet is likewise solved by correlation, so
   all four line up and he does not jump when the state changes.

3. NEIGHBOUR SPILL. Frames touch: on some cells 192 rows of art run right up to
   the cell boundary, so sampling across it would drag in the next frame's
   glow. The usual fix is to sample wide and then drop whatever is not joined
   to the body - but that cannot be used here. In the last death frame the
   staff has fallen OUT OF HIS HAND and is a separate 5548 px island, and the
   power cast throws off around thirty detached sparkles. Connectivity cleanup
   would delete all of it. So each cell is sliced out and rendered in
   isolation instead: there is physically no neighbour to bleed in, and every
   detached sparkle and the dropped staff survive untouched.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\king pics"
KING = os.path.join(PROJECT, "ArtSource", "Characters", "King")
FRAMES_DIR = os.path.join(KING, "Frames")
SHEETS_DIR = os.path.join(KING, "Sheets")

COLUMNS = 8

SHEETS = [
    dict(anim="Idle",      file="07099154-9c5d-4199-a3a7-35f00ecf9914.png"),
    dict(anim="Alert",     file="e5cf2b3c-1d51-4f2f-829c-2b2f045f7617.png"),
    dict(anim="PowerCast", file="8bb300d4-d49f-47f5-8946-6af954aca876.png"),
    dict(anim="Death",     file="70e80680-5251-4ac0-a085-2de7829990fe.png"),
]
REFERENCE = "Idle"

# 192x232, pivot (96, 208).
#
# Width is the project's existing 192 - shared with Ravager and Swarm Node so
# every character keeps one horizontal convention. The King needs only 47 px
# either side of the pivot; the rest is margin, and it costs nothing.
#
# Height is where he differs, and the power cast decides it: the gold starburst
# breaks 195 px above his feet, against the 179 a 192-tall canvas allows. The
# death collapse then needs 15 px BELOW the standing feet row, because he ends
# lying on the floor. 208 above and 23 below clears both with real margin
# rather than the 5 px a 224-tall canvas would have left - the King is not
# shrunk to fit a rounder number.
#
# ONE canvas is used for all five states, so the sprite never changes size and
# nothing can pop when the state changes.
CANVAS = (192, 232)
PIVOT = (96, 208)

# Crown to feet in the finished frames. Ravager stands 116 px; the King is
# given 120 - the protected objective should read as slightly the larger figure
# without towering over the guard who defends him.
TARGET_CROWN_TO_FEET = 120.0

SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128

# Only the blue glow is treated as an effect. His robes are blue and his armour
# is gold, so a "bright warm pixel is an effect" rule would eat his own crown.
# The gold burst lives up at the staff and can never reach the ground contact,
# which is the only thing the body mask is used for here.
EFFECT_BLUE_MIN = 150
EFFECT_BLUE_BIAS = 60

# Correlation search. Coarse pass then a fine pass around the winner.
CORR_DOWNSAMPLE = 3


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


def is_effect(r, g, b):
    return b > EFFECT_BLUE_MIN and b - r > EFFECT_BLUE_BIAS


# ---------------------------------------------------------------------------
# Correlation: solve scale and horizontal anchor without needing a landmark
# ---------------------------------------------------------------------------
def body_mask(cell):
    body, _full, w, h = ptk_sheet.build_masks(cell, SRC_ALPHA_THRESHOLD, is_effect)
    return body, w, h


def shrink(mask, w, h, k):
    """Box-decimate a 0/1 mask by k, so the correlation is affordable."""
    sw, sh = w // k, h // k
    out = bytearray(sw * sh)
    for y in range(sh):
        for x in range(sw):
            hit = 0
            for dy in range(k):
                base = (y * k + dy) * w + x * k
                for dx in range(k):
                    if mask[base + dx]:
                        hit = 1
                        break
                if hit:
                    break
            out[y * sw + x] = hit
    return out, sw, sh


def place(mask, w, h, scale, ax, ay, cw, ch, px_c, py_c):
    """Nearest-neighbour placement of a mask with (ax, ay) landing on the pivot."""
    out = bytearray(cw * ch)
    inv = 1.0 / scale
    for oy in range(ch):
        sy = int(ay + (oy - py_c) * inv)
        if sy < 0 or sy >= h:
            continue
        rb = sy * w
        ob = oy * cw
        for ox in range(cw):
            sx = int(ax + (ox - px_c) * inv)
            if 0 <= sx < w and mask[rb + sx]:
                out[ob + ox] = 1
    return out


def overlap(a, b, n):
    inter = union = 0
    for i in range(n):
        p = a[i]
        q = b[i]
        if p or q:
            union += 1
            if p and q:
                inter += 1
    return inter / float(union) if union else 0.0


def solve_alignment(ref_small, ref_w, ref_h, ref_ax, ref_ay,
                    mask_small, w, h, ax_guess, ay):
    """
    Best (scale, anchor_x) mapping this sheet's frame 1 onto the reference's.

    Frame 1 is the same neutral pose in every sheet, so overlap is a direct
    measure of "same size, same place" and needs no landmark to be identified.
    """
    cw, ch = 140, 210
    px_c, py_c = cw // 2, ch - 24
    ref_plane = place(ref_small, ref_w, ref_h, 1.0, ref_ax, ref_ay, cw, ch, px_c, py_c)
    n = cw * ch

    best = (-1.0, 1.0, ax_guess)
    for coarse in range(0, 21):
        s = 0.85 + coarse * 0.02
        for step in range(-5, 6):
            ax = ax_guess + step * 3.0
            cand = place(mask_small, w, h, s, ax, ay, cw, ch, px_c, py_c)
            v = overlap(ref_plane, cand, n)
            if v > best[0]:
                best = (v, s, ax)

    _v, s0, ax0 = best
    for fine in range(-5, 6):
        s = s0 + fine * 0.005
        for step in range(-4, 5):
            ax = ax0 + step * 1.0
            cand = place(mask_small, w, h, s, ax, ay, cw, ch, px_c, py_c)
            v = overlap(ref_plane, cand, n)
            if v > best[0]:
                best = (v, s, ax)
    return best


def crown_to_feet(cell):
    """
    Height of the King himself, ignoring the staff.

    Scanning down from the top, the staff shows up as a thin pole and its ring
    as a narrow arc; the first row whose LONGEST CONTIGUOUS RUN is wide enough
    to be shoulders-and-crown is the King. Total row coverage would not do -
    the staff would be counted the moment it sat beside his head.
    """
    body, w, h = body_mask(cell)
    anchor = ptk_sheet.ground_anchor(body, w, h)
    feet = anchor["bottom"]
    for y in range(h):
        base = y * w
        best = cur = 0
        for x in range(w):
            if body[base + x]:
                cur += 1
                if cur > best:
                    best = cur
            else:
                cur = 0
        if best >= 30:
            return feet - y + 1, anchor
    fail("could not find the King's crown")


def plan():
    """Scale and anchor for every sheet, all solved against the Idle sheet."""
    loaded = {}
    for spec in SHEETS:
        path = os.path.join(SOURCE_DIR, spec["file"])
        if not os.path.isfile(path):
            fail("source sheet missing: " + path)
        sheet = ptk_png.read_png(path)
        grid = ptk_sheet.Grid(sheet, COLUMNS, 1)
        loaded[spec["anim"]] = (sheet, grid)

    ref_sheet, ref_grid = loaded[REFERENCE]
    ref_cell = ref_grid.cell(0, 0)
    ref_body, rw, rh = body_mask(ref_cell)
    ref_anchor = ptk_sheet.ground_anchor(ref_body, rw, rh)
    ref_xs = [x for x in range(rw) if any(ref_body[y * rw + x] for y in range(rh))]
    ref_ax = (ref_xs[0] + ref_xs[-1]) / 2.0
    ref_ay = ref_anchor["bottom"]

    height, _a = crown_to_feet(ref_cell)
    master = TARGET_CROWN_TO_FEET / float(height)

    k = CORR_DOWNSAMPLE
    ref_small, rsw, rsh = shrink(ref_body, rw, rh, k)

    log("reference sheet {0}: crown-to-feet {1}px, anchor ({2:.1f}, {3})".format(
        REFERENCE, height, ref_ax, ref_ay))
    log("master scale x{0:.5f}  ->  {1:.0f}px crown-to-feet in the finished frames".format(
        master, TARGET_CROWN_TO_FEET))
    log("")

    out = {}
    for spec in SHEETS:
        anim = spec["anim"]
        sheet, grid = loaded[anim]
        cell = grid.cell(0, 0)
        body, w, h = body_mask(cell)
        anchor = ptk_sheet.ground_anchor(body, w, h)
        xs = [x for x in range(w) if any(body[y * w + x] for y in range(h))]
        guess = (xs[0] + xs[-1]) / 2.0
        if anim == REFERENCE:
            fit, norm, ax = 1.0, 1.0, ref_ax
        else:
            small, sw, sh = shrink(body, w, h, k)
            fit, norm, ax = solve_alignment(
                ref_small, rsw, rsh, ref_ax / k, ref_ay / k,
                small, sw, sh, guess / k, anchor["bottom"] / float(k))
            ax *= k
        out[anim] = dict(sheet=sheet, grid=grid, scale=master * norm,
                         norm=norm, ax=ax, ay=anchor["bottom"], fit=fit)
        log("  {0:<10s} drawn {1:+5.1f}%  ->  normalise x{2:.4f}  "
            "anchor ({3:6.1f}, {4})  overlap {5:.3f}".format(
                anim, 100.0 * (1.0 / norm - 1.0), norm, ax, anchor["bottom"], fit))
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def process(anim, info, measure_only):
    grid = info["grid"]
    scale = info["scale"]
    ax, ay = info["ax"], info["ay"]

    cells = [grid.cell(c, 0) for c in range(COLUMNS)]
    masks = [ptk_sheet.build_masks(c, SRC_ALPHA_THRESHOLD, is_effect) for c in cells]
    bounds = [ptk_sheet.mask_bounds(m[1], m[2], m[3]) for m in masks]

    need_l = need_r = need_u = need_d = 0.0
    for x0, x1, y0, y1 in bounds:
        need_l = max(need_l, (ax - x0) * scale)
        need_r = max(need_r, (x1 - ax) * scale)
        need_u = max(need_u, (ay - y0) * scale)
        need_d = max(need_d, (y1 - ay) * scale)

    log("")
    log("=" * 76)
    log("{0}  <-  {1}".format(anim, os.path.basename(
        [s["file"] for s in SHEETS if s["anim"] == anim][0])))
    log("  needs left {0:.0f} right {1:.0f} up {2:.0f} down {3:.0f}"
        "   (canvas gives {4} / {5} / {6} / {7})".format(
            need_l, need_r, need_u, need_d,
            PIVOT[0], CANVAS[0] - PIVOT[0] - 1, PIVOT[1], CANVAS[1] - PIVOT[1] - 1))
    if (need_l > PIVOT[0] or need_r > CANVAS[0] - PIVOT[0] - 1
            or need_u > PIVOT[1] or need_d > CANVAS[1] - PIVOT[1] - 1):
        fail("{0} does not fit {1}x{2} at pivot {3}".format(anim, CANVAS[0], CANVAS[1], PIVOT))

    if measure_only:
        return []

    out_dir = os.path.join(FRAMES_DIR, anim)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    results = []
    for c in range(COLUMNS):
        # Rendered from the isolated cell, so sampling cannot reach the
        # neighbouring frame and no connectivity cleanup is needed - which is
        # what keeps the dropped staff and the loose sparkles.
        cell = cells[c]
        frame = ptk_sheet.render_frame(
            cell, 0, 0, cell.width, cell.height,
            ax, ay, scale, CANVAS, PIVOT, fence_fraction=1.0)
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        clipped = ptk_sheet.border_contact(frame)
        name = "{0}_{1:02d}.png".format(anim, c + 1)
        ptk_png.write_png(os.path.join(out_dir, name), frame)
        results.append(dict(name=name, clipped=clipped))
        log("    {0}{1}".format(name, "  CLIPPED {0}px".format(clipped) if clipped else ""))

    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    cw, ch = CANVAS
    contact = ptk_png.Image(cw * COLUMNS, ch)
    for c in range(COLUMNS):
        contact.paste(ptk_png.read_png(
            os.path.join(out_dir, "{0}_{1:02d}.png".format(anim, c + 1))), c * cw, 0)
    ptk_png.write_png(os.path.join(SHEETS_DIR, "King_{0}_8F.png".format(anim)), contact)
    log("  sheet  King_{0}_8F.png  ({1}x{2})".format(anim, contact.width, contact.height))
    return results


def main():
    parser = argparse.ArgumentParser(description="Extract the King's animations.")
    parser.add_argument("--measure", action="store_true",
                        help="report scale, anchors and required extents, write nothing")
    args = parser.parse_args()

    log("King animation extraction")
    log("canvas {0}x{1}, pivot {2}".format(CANVAS[0], CANVAS[1], PIVOT))
    log("")
    layout = plan()

    every = []
    for spec in SHEETS:
        every.extend(process(spec["anim"], layout[spec["anim"]], args.measure))

    if args.measure:
        return

    log("")
    log("=" * 76)
    log("{0} frames written".format(len(every)))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED: " + ", ".join(
            "{0} ({1}px)".format(r["name"], r["clipped"]) for r in clipped))
    else:
        log("no frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
