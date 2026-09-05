"""
Protect the King - 2D
Extracts the 8-frame Ravager WALK and ATTACK cycles from the four new
generated sprite sheets.

    source : <Downloads>/gamethon pics/design 2d pics/ravager pics/*.png  (READ ONLY)
    output : ArtSource/Characters/Guards/Ravager/Frames/{Walk,Attack}/<Dir>/*.png
             ArtSource/Characters/Guards/Ravager/Sheets/*.png

The originals are never renamed, moved, modified or deleted.

Run:  python Tools/ExtractRavagerAnimations.py --measure     (report only)
      python Tools/ExtractRavagerAnimations.py               (write frames)


WHY THIS SCRIPT LOOKS THE WAY IT DOES
-------------------------------------
Four things about the source sheets forced the design. All four were measured,
not assumed; `--measure` re-prints the evidence.

1. THE SHEETS ARE NOT ALL AT THE SAME SCALE.
   Ravager is drawn ~296 px tall (helmet to feet) on the walk sheets but only
   ~240 px tall on the attack sheets - a ratio of 0.82. Slicing all four at a
   single scale would make him shrink by a fifth the instant he attacks.
   Each sheet therefore gets its OWN scale factor, chosen so that every
   finished frame lands on the same target body height as the existing idle
   art. See REFERENCE_BODY_HEIGHT / TARGET_BODY_HEIGHT.

2. THE WALK SHEETS DRIFT ACROSS THE CELL, THE ATTACK SHEETS DO NOT.
   On the left/right walk sheet the body centre slides monotonically by ~38 px
   over the eight frames. That is generator drift: played back it reads as the
   sprite sliding sideways and then snapping home at the loop point.
   On the attack sheets the body centre wanders by a similar amount but
   RETURNS to its starting value on frame 8 - that is the lunge into the
   strike, and it is intentional.
   So walk frames are anchored per-frame (drift removed, foot-plant preserved)
   and attack frames are anchored once per row (lunge preserved). This is the
   whole of STEP 6: kill placement jitter, keep animation.

3. THE ATTACK FRAMES DO NOT FIT IN 128x128.
   At matched body scale the attack cycle needs 174 px of width and 154 px
   above the feet, because the axe is raised overhead and swung out wide. The
   overflow is the AXE ITSELF, not the glow - measuring the armour-only mask
   still needs 173 px. 128x128 is geometrically impossible without either
   shrinking Ravager (forbidden) or amputating the axe.
   Attack frames therefore use ATTACK_CANVAS with the pivot at the same
   body-relative position, so the feet still land on the same world point.
   Paper2D pivots are per-sprite, so mixing frame sizes inside a character is
   free. Walk and idle stay at 128x128 exactly as specified.

4. THE SLASH FX CROSSES CELL BOUNDARIES.
   On both attack sheets the blue arc of frames 4-6 spills into the
   neighbouring cell. Sampling is therefore allowed to read outside the cell
   (so a frame keeps its own arc), and the neighbour's spill is then removed
   by keeping only the pixels connected to this frame's own silhouette.


BACKGROUND REMOVAL
------------------
Unlike the turnaround sheet, these four already carry a real alpha channel:
alpha is bimodal at 0 (background) and 249-253 (Ravager), with a thin
anti-aliased rim between. There is no presentation backdrop to flood-fill and
no colour key is used anywhere, so the "dark armour shares colours with the
dark background" failure mode cannot occur here.

Alpha is resolved to hard 0/255 because the runtime material is
MaskedUnlitSpriteMaterial, which thresholds anyway. Making the cut here rather
than in the shader means what this script writes is exactly what renders.
"""

import argparse
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------
SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\ravager pics"

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAVAGER = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Ravager")
FRAMES_DIR = os.path.join(RAVAGER, "Frames")
SHEETS_DIR = os.path.join(RAVAGER, "Sheets")

COLUMNS = 8
SHEET_ROWS = 2

# The four sheets, identified by content (see verify_identity) rather than by
# filename - the delivered names are opaque GUIDs and carry no meaning.
SHEETS = [
    dict(key="Walk_LeftRight",   anim="Walk",   rows=("Left", "Right"),
         file="97e81ac1-9168-451f-89ba-a03152847cbf.png"),
    dict(key="Walk_DownUp",      anim="Walk",   rows=("Down", "Up"),
         file="4898a97a-72ca-4253-ba2b-e8eea5e94049.png"),
    dict(key="Attack_LeftRight", anim="Attack", rows=("Left", "Right"),
         file="91297213-8cf4-4553-9b79-de1acdb4e4f6.png"),
    dict(key="Attack_DownUp",    anim="Attack", rows=("Down", "Up"),
         file="9f2aa37d-2b41-430f-8cae-c3e630d359e5.png"),
]


# ---------------------------------------------------------------------------
# Output contract - keep in sync with Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
# ONE canvas and ONE pivot for every Ravager frame - idle, walk and attack.
#
# 128x128 was the original cell and it still holds the idle art, but it cannot
# hold the animations at the same body scale. Measured worst cases, in pixels
# from the feet anchor:
#
#     idle     left 42  right 44  up 117  down  8
#     walk     left 70  right 71  up 120  down  1
#     attack   left 78  right 72  up 152  down  8
#
# 128x128 with the pivot at (64,119) gives left 64, right 63, up 119, down 8 -
# so the walk axe overruns by 7 px and the raised attack axe by 33 px. The
# overflow is armour and axe, not glow: masking the energy out still needs
# 173 px of width. The only ways to reach 128 are to shrink Ravager (banned:
# he must not change size between states) or to cut the axe off.
#
# 192x192 with the pivot at (96,179) clears every case with margin. Nothing is
# rescaled and nothing moves: Ravager is drawn at exactly the same size, on the
# same feet anchor, with more transparent padding around him. Paper2D stores a
# pivot per sprite, so the extra padding costs nothing at runtime beyond
# texture memory.
CANVAS = (192, 192)
PIVOT = (96, 179)

# Ravager's helmet-to-feet height in the finished frames. Measured off the four
# existing idle sprites, which are the scale reference for the whole character.
TARGET_BODY_HEIGHT = 116.0

# A source pixel counts as Ravager when its alpha clears this. The source is
# bimodal at 0 / ~251 so anything in the middle of the range works.
SRC_ALPHA_THRESHOLD = 128

# Alpha cut applied to the finished frame, after area-averaging.
OUT_ALPHA_THRESHOLD = 128

# Blue energy - axe blades, slash arcs, visor, chest core. Excluded from the
# "core" mask so that body geometry is measured off armour alone and a wide
# glow can never move the anchor.
def is_energy(r, g, b):
    return b > 140 and b - r > 70


DIRECTIONS = ("Down", "Up", "Left", "Right")


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


# ---------------------------------------------------------------------------
# Masks and body metrics
# ---------------------------------------------------------------------------
def build_masks(img):
    """(core, full, w, h). core = armour only; full = armour + energy."""
    w, h, px = img.width, img.height, img.px
    core = bytearray(w * h)
    full = bytearray(w * h)
    for y in range(h):
        base = y * w * 4
        row = y * w
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            full[row + x] = 1
            if not is_energy(px[i], px[i + 1], px[i + 2]):
                core[row + x] = 1
    return core, full, w, h


def body_metrics(core, w, h, reference_height):
    """
    feet  : lowest armour row carrying real width (not a stray glow pixel)
    top   : highest armour row carrying real width
    cx    : horizontal centre of the hips

    The hips band is located using `reference_height` rather than this frame's
    own height. When the axe is raised overhead the frame's own top is the axe,
    which would slide the band down the legs and make cx incomparable between
    frames of the same animation.
    """
    foot_threshold = max(2, int(round(0.030 * w)))
    head_threshold = max(2, int(round(0.022 * w)))
    rows = [sum(core[y * w:(y + 1) * w]) for y in range(h)]

    solid = [y for y in range(h) if rows[y] >= foot_threshold]
    if not solid:
        return None
    feet = solid[-1]
    heads = [y for y in range(h) if rows[y] >= head_threshold]
    top = heads[0]

    span = reference_height if reference_height else (feet - top)
    y0 = max(0, int(feet - span * 0.55))
    y1 = min(h - 1, int(feet - span * 0.35))
    xs = [x for y in range(y0, y1 + 1) for x in range(w) if core[y * w + x]]
    if not xs:
        return None
    return dict(feet=feet, top=top, body=feet - top + 1, cx=sum(xs) / float(len(xs)))


# ---------------------------------------------------------------------------
# Identity checks - the sheets arrive as GUIDs, so prove what each one is
# ---------------------------------------------------------------------------
def energy_bias(img):
    """Signed offset of the axe-energy mass from the silhouette centre.

    Negative means the axe sits left of Ravager, which is how the known-good
    Idle_Left sprite reads (-0.09 against Idle_Right's +0.09).
    """
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
            if is_energy(px[i], px[i + 1], px[i + 2]):
                ex += x
                en += 1
    if not sn or not en:
        return 0.0
    return (ex / en - sx / sn) / w


def visor_glow(img):
    """Fraction of the head band that glows - high facing the camera, low from
    behind, because the visor is only visible from the front."""
    core, full, w, h = build_masks(img)
    rows = [sum(core[y * w:(y + 1) * w]) for y in range(h)]
    solid = [y for y in range(h) if rows[y] >= max(2, int(round(0.030 * w)))]
    if not solid:
        return 0.0
    top, feet = solid[0], solid[-1]
    band = top + int((feet - top) * 0.30)
    px = img.px
    lit = seen = 0
    for y in range(top, band + 1):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            seen += 1
            if is_energy(px[i], px[i + 1], px[i + 2]):
                lit += 1
    return lit / float(seen) if seen else 0.0


def verify_identity(spec, cells):
    """Refuses to run on a sheet whose content contradicts its row mapping."""
    if spec["rows"] == ("Left", "Right"):
        left = sum(energy_bias(c) for c in cells[0]) / COLUMNS
        right = sum(energy_bias(c) for c in cells[1]) / COLUMNS
        if not (left < 0.0 < right):
            fail("{0}: row 0 should face LEFT and row 1 RIGHT, but the axe-energy "
                 "bias reads {1:+.3f} / {2:+.3f}".format(spec["key"], left, right))
        return "axe bias row0={0:+.3f} (Left) row1={1:+.3f} (Right)".format(left, right)

    # Down/Up. Frames whose raised axe intrudes on the head band are skipped;
    # they say nothing about which way the helmet is pointing.
    def clean_mean(row):
        vals = [visor_glow(c) for c in row]
        keep = [v for v in vals if v < 0.10]
        return sum(keep) / len(keep) if keep else sum(vals) / len(vals)

    down = clean_mean(cells[0])
    up = clean_mean(cells[1])
    if not down > up:
        fail("{0}: row 0 should face DOWN (visor lit) and row 1 UP, but the visor "
             "glow reads {1:.4f} / {2:.4f}".format(spec["key"], down, up))
    return "visor glow row0={0:.4f} (Down) row1={1:.4f} (Up)".format(down, up)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
def render_frame(sheet, origin_x, origin_y, cell_w, cell_h,
                 anchor_cx, anchor_feet, scale, canvas, pivot):
    """
    Maps the finished frame back into the sheet and area-averages.

    Working backwards from the output means the anchor lands on the pivot to
    sub-pixel accuracy with no intermediate resample, so no rounding error can
    creep in and re-introduce the jitter this script exists to remove.

    Sampling deliberately crosses the cell edge, because the slash arc does,
    but only sideways and only so far. The fence is measured from the anchor,
    not from the cell edge:

        widest own content   171 px  (the walk axe, held out horizontally)
        nearest neighbour    221 px  (their body edge; the drift is common to
                                      the whole row, so this gap is stable)

    0.66 of a cell sits at 179 px - past everything of ours, clear of them.
    Vertically nothing needs to leave the cell at all: the tallest reach is the
    raised attack axe at 310 px above the feet, and the cell already offers
    333 px, so the window is clamped to the row. That removes any chance of
    pulling the row above or below into frame.
    """
    out_w, out_h = canvas
    px_per_out = 1.0 / scale
    fence = cell_w * 0.66
    anchor_abs_x = origin_x + anchor_cx
    x_lo = max(0, int(anchor_abs_x - fence))
    x_hi = min(sheet.width, int(anchor_abs_x + fence) + 1)
    y_lo = origin_y
    y_hi = min(sheet.height, origin_y + cell_h)

    out = ptk_png.Image(out_w, out_h)
    src = sheet.px
    sw = sheet.width

    abs_cx = origin_x + anchor_cx
    abs_feet = origin_y + anchor_feet

    for oy in range(out_h):
        sy0 = abs_feet + (oy - pivot[1]) * px_per_out
        sy1 = sy0 + px_per_out
        iy0 = max(y_lo, int(sy0))
        iy1 = min(y_hi, int(sy1) + 1)
        if iy0 >= iy1:
            continue
        for ox in range(out_w):
            sx0 = abs_cx + (ox - pivot[0]) * px_per_out
            sx1 = sx0 + px_per_out
            ix0 = max(x_lo, int(sx0))
            ix1 = min(x_hi, int(sx1) + 1)
            if ix0 >= ix1:
                continue
            r = g = b = a = 0
            n = 0
            for yy in range(iy0, iy1):
                base = yy * sw * 4
                for xx in range(ix0, ix1):
                    i = base + xx * 4
                    al = src[i + 3]
                    r += src[i] * al
                    g += src[i + 1] * al
                    b += src[i + 2] * al
                    a += al
                    n += 1
            if not n or not a:
                continue
            # Colour is averaged premultiplied, so transparent background pixels
            # cannot bleed a dark fringe into the silhouette edge.
            out.set(ox, oy, (r // a, g // a, b // a, a // n))
    return out


def harden_alpha(img):
    """Resolves the anti-aliased rim to a hard silhouette."""
    px = img.px
    for i in range(3, len(px), 4):
        px[i] = 255 if px[i] >= OUT_ALPHA_THRESHOLD else 0


def keep_connected(img, seed_xy):
    """
    Drops everything not joined to Ravager himself.

    This is what removes the neighbouring frame's slash arc after sampling was
    allowed across the cell boundary. Returns the number of pixels discarded.
    """
    w, h, px = img.width, img.height, img.px
    solid = [px[i * 4 + 3] > 0 for i in range(w * h)]
    total = sum(1 for v in solid if v)
    if not total:
        return 0

    sx, sy = seed_xy
    if not (0 <= sx < w and 0 <= sy < h and solid[sy * w + sx]):
        # Anchor landed on a transparent pixel (mid-stride gap). Fall back to
        # the nearest solid pixel on the anchor column.
        found = None
        for dy in range(h):
            for cand in (sy - dy, sy + dy):
                if 0 <= cand < h and solid[cand * w + sx]:
                    found = (sx, cand)
                    break
            if found:
                break
        if not found:
            return 0
        sx, sy = found

    seen = bytearray(w * h)
    queue = deque([(sx, sy)])
    seen[sy * w + sx] = 1
    kept = 0
    while queue:
        x, y = queue.popleft()
        kept += 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                k = ny * w + nx
                if solid[k] and not seen[k]:
                    seen[k] = 1
                    queue.append((nx, ny))

    for k in range(w * h):
        if solid[k] and not seen[k]:
            px[k * 4 + 3] = 0
    return total - kept


def border_contact(img):
    """Opaque pixels sitting on the canvas edge, i.e. art that got clipped."""
    w, h, px = img.width, img.height, img.px
    n = 0
    for x in range(w):
        if px[(0 * w + x) * 4 + 3]:
            n += 1
        if px[((h - 1) * w + x) * 4 + 3]:
            n += 1
    for y in range(h):
        if px[(y * w + 0) * 4 + 3]:
            n += 1
        if px[(y * w + (w - 1)) * 4 + 3]:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def load_cells(spec):
    path = os.path.join(SOURCE_DIR, spec["file"])
    if not os.path.isfile(path):
        fail("source sheet missing: " + path)
    sheet = ptk_png.read_png(path)
    cell_w = sheet.width / float(COLUMNS)
    cell_h = sheet.height // SHEET_ROWS
    cells = []
    for row in range(SHEET_ROWS):
        line = []
        for col in range(COLUMNS):
            x0 = int(round(col * cell_w))
            x1 = int(round((col + 1) * cell_w))
            line.append(sheet.crop(x0, row * cell_h, x1, row * cell_h + cell_h))
        cells.append(line)
    return sheet, cells, cell_w, cell_h


def plan_sheet(spec, cells, cell_w):
    """Scale, per-frame metrics and the anchor scheme for one sheet."""
    masks = [[build_masks(cells[r][c]) for c in range(COLUMNS)]
             for r in range(SHEET_ROWS)]

    def measure(reference):
        out = []
        for r in range(SHEET_ROWS):
            line = []
            for c in range(COLUMNS):
                core, _full, w, h = masks[r][c]
                line.append(body_metrics(core, w, h, reference))
            out.append(line)
        return out

    raw = measure(cell_w * 1.05)

    if spec["anim"] == "Walk":
        # Every walk frame is a standing pose, so the median is the height.
        heights = sorted(m["body"] for row in raw for m in row)
        reference = heights[len(heights) // 2]
    else:
        # Frames 1 and 8 are "ready" / "return to ready" - the only attack poses
        # whose height is not inflated by the axe being raised over the helmet.
        ready = [raw[r][c]["body"] for r in range(SHEET_ROWS) for c in (0, COLUMNS - 1)]
        reference = sorted(ready)[len(ready) // 2]

    # Re-measure with the settled reference so every cx is comparable.
    metrics = measure(reference)

    scale = TARGET_BODY_HEIGHT / float(reference)
    anchors = []
    for r in range(SHEET_ROWS):
        row = metrics[r]
        if spec["anim"] == "Walk":
            # Per frame: the planted foot stays planted and the drift is gone.
            anchors.append([(m["cx"], m["feet"]) for m in row])
        else:
            # Once per row: the lunge into the strike survives intact, and the
            # ready pose still lands exactly on the pivot.
            cx = (row[0]["cx"] + row[COLUMNS - 1]["cx"]) / 2.0
            feet = sorted(m["feet"] for m in row)[COLUMNS // 2]
            anchors.append([(cx, feet)] * COLUMNS)
    return metrics, anchors, scale, reference


def process(spec, measure_only):
    sheet, cells, cell_w, cell_h = load_cells(spec)
    identity = verify_identity(spec, cells)
    metrics, anchors, scale, reference = plan_sheet(spec, cells, cell_w)

    canvas, pivot = CANVAS, PIVOT

    log("")
    log("=" * 74)
    log("{0}  <-  {1}".format(spec["key"], spec["file"]))
    log("  {0}x{1}, cell {2:.1f}x{3}, identity: {4}"
        .format(sheet.width, sheet.height, cell_w, cell_h, identity))
    log("  body height {0} px  ->  scale x{1:.4f}  ->  target {2:.0f} px"
        .format(reference, scale, TARGET_BODY_HEIGHT))
    log("  canvas {0}x{1}, pivot {2}".format(canvas[0], canvas[1], pivot))

    results = []
    for r in range(SHEET_ROWS):
        direction = spec["rows"][r]
        feet = [metrics[r][c]["feet"] for c in range(COLUMNS)]
        cxs = [metrics[r][c]["cx"] for c in range(COLUMNS)]
        heights = [metrics[r][c]["body"] for c in range(COLUMNS)]
        log("  row{0} {1:<5s} feet spread {2:2d}px  cx spread {3:5.1f}px  "
            "bodyH {4}..{5}".format(r, direction, max(feet) - min(feet),
                                    max(cxs) - min(cxs), min(heights), max(heights)))

        if measure_only:
            need_l = need_r = need_u = need_d = 0.0
            for c in range(COLUMNS):
                acx, afeet = anchors[r][c]
                core, full, w, h = build_masks(cells[r][c])
                xs = [x for x in range(w) if any(full[y * w + x] for y in range(h))]
                ys = [y for y in range(h) if any(full[y * w + x] for x in range(w))]
                need_l = max(need_l, (acx - xs[0]) * scale)
                need_r = max(need_r, (xs[-1] - acx) * scale)
                need_u = max(need_u, (afeet - ys[0]) * scale)
                need_d = max(need_d, (ys[-1] - afeet) * scale)
            log("        needs left={0:.1f} right={1:.1f} up={2:.1f} down={3:.1f}"
                "  (canvas gives {4} / {5} / {6} / {7})"
                .format(need_l, need_r, need_u, need_d,
                        pivot[0], canvas[0] - pivot[0] - 1,
                        pivot[1], canvas[1] - pivot[1] - 1))
            continue

        out_dir = os.path.join(FRAMES_DIR, spec["anim"], direction)
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)

        for c in range(COLUMNS):
            acx, afeet = anchors[r][c]
            frame = render_frame(sheet, int(round(c * cell_w)), r * cell_h,
                                 cell_w, cell_h, acx, afeet, scale, canvas, pivot)
            harden_alpha(frame)
            dropped = keep_connected(frame, (pivot[0], pivot[1] - 20))
            clipped = border_contact(frame)
            name = "{0}_{1}_{2:02d}.png".format(spec["anim"], direction, c + 1)
            ptk_png.write_png(os.path.join(out_dir, name), frame)
            results.append(dict(name=name, dropped=dropped, clipped=clipped,
                                direction=direction, anim=spec["anim"]))
            note = ""
            if dropped:
                note += "  spill removed {0}px".format(dropped)
            if clipped:
                note += "  CLIPPED {0}px".format(clipped)
            log("    {0}{1}".format(name, note))

    return results, canvas, pivot, scale


def build_contact_sheet(spec, canvas):
    """The 8x2 normalised sheet: one row per direction, frame 1 leftmost."""
    cw, ch = canvas
    out = ptk_png.Image(cw * COLUMNS, ch * SHEET_ROWS)
    for r, direction in enumerate(spec["rows"]):
        for c in range(COLUMNS):
            path = os.path.join(FRAMES_DIR, spec["anim"], direction,
                                "{0}_{1}_{2:02d}.png".format(spec["anim"], direction, c + 1))
            out.paste(ptk_png.read_png(path), c * cw, r * ch)
    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    name = "Ravager_{0}_8F.png".format(spec["key"])
    ptk_png.write_png(os.path.join(SHEETS_DIR, name), out)
    log("  sheet  {0}  ({1}x{2})".format(name, out.width, out.height))
    return name


LEGACY_IDLE_CANVAS = (128, 128)
LEGACY_IDLE_PIVOT = (64, 119)


def recanvas_idle():
    """
    Re-frames the four existing idle sprites onto the shared canvas.

    This is a pure copy: not one pixel of Ravager is resampled, recoloured or
    moved relative to his feet. Only the transparent margin around him changes,
    so that idle, walk and attack all agree on one frame size and one pivot.
    The 128x128 originals stay where they are as the scale reference.
    """
    out_dir = os.path.join(FRAMES_DIR, "Idle")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    dx = PIVOT[0] - LEGACY_IDLE_PIVOT[0]
    dy = PIVOT[1] - LEGACY_IDLE_PIVOT[1]
    log("")
    log("=" * 74)
    log("Idle  <-  existing 128x128 art, re-framed onto {0}x{1} at +({2},{3})"
        .format(CANVAS[0], CANVAS[1], dx, dy))

    for direction in DIRECTIONS:
        src = os.path.join(FRAMES_DIR, "Idle_{0}.png".format(direction))
        if not os.path.isfile(src):
            fail("idle source missing: " + src)
        small = ptk_png.read_png(src)
        if (small.width, small.height) != LEGACY_IDLE_CANVAS:
            fail("{0} is {1}x{2}, expected {3}x{4}".format(
                src, small.width, small.height, *LEGACY_IDLE_CANVAS))
        frame = ptk_png.Image(CANVAS[0], CANVAS[1])
        frame.paste(small, dx, dy)
        name = "Idle_{0}.png".format(direction)
        ptk_png.write_png(os.path.join(out_dir, name), frame)
        log("    {0}".format(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", action="store_true",
                        help="report geometry and required canvas, write nothing")
    args = parser.parse_args()

    log("Ravager animation extraction")
    log("source: " + SOURCE_DIR + "  (read only)")

    every = []
    for spec in SHEETS:
        results, canvas, pivot, scale = process(spec, args.measure)
        every.extend(results)
        if not args.measure:
            build_contact_sheet(spec, canvas)

    if args.measure:
        return

    recanvas_idle()

    log("")
    log("=" * 74)
    log("{0} frames written".format(len(every)))
    clipped = [r for r in every if r["clipped"]]
    spilled = [r for r in every if r["dropped"] > 40]
    if clipped:
        log("CLIPPED at canvas edge: " + ", ".join(
            "{0} ({1}px)".format(r["name"], r["clipped"]) for r in clipped))
    else:
        log("no frame touches its canvas edge - nothing was clipped")
    if spilled:
        log("neighbour spill removed: " + ", ".join(
            "{0} ({1}px)".format(r["name"], r["dropped"]) for r in spilled))


if __name__ == "__main__":
    main()
