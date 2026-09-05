"""
Protect the King - 2D
Extracts the four REAL Ravager directional idle frames from the source
turnaround sheet.

    source : <Downloads>/gamethon pics/design 2d pics/ravager.png   (READ ONLY)
    output : ArtSource/Characters/Guards/Ravager/Frames/Idle_{Down,Up,Left,Right}.png

The source is never modified. A byte-identical copy is archived into
ArtSource/Characters/Guards/Ravager/Concept/ for reference.

Run:  python Tools/ExtractRavagerIdle.py
      python Tools/ExtractRavagerIdle.py --mode nearest


HOW THIS WORKS
--------------
1. Background removal is a flood fill inwards from the image border, keeping
   pixels within `BG_TOLERANCE` of the measured background colour.

   A flood fill is used rather than a plain colour key because Ravager's armour
   contains thousands of pixels that are themselves within tolerance of the
   background. A colour key would punch holes straight through him. Connectivity
   is what distinguishes "background" from "very dark armour".

   Alpha is written as strictly 0 or 255. There is no feathering anywhere in
   this script, so no semi-transparent halo can be produced.

2. Each view is cropped, then downscaled by an exact integer factor of 4.

3. Frames are composed onto a 128x128 canvas so that the helmet centre lands on
   column 64 and the feet contact row lands on row 119.


MEASURED SOURCE GEOMETRY
------------------------
Bounding boxes and helmet centres are re-derived from the image every run.
The feet rows below were measured by row-profiling each view and confirmed
visually; they cannot be auto-detected reliably because the axe overlaps or
extends below the boots in three of the four views.
"""

import argparse
import os
import shutil
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png


# --------------------------------------------------------------------------
# Source
# --------------------------------------------------------------------------
SOURCE = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\ravager.png"

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES_DIR = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Ravager", "Frames")
CONCEPT_DIR = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Ravager", "Concept")

# Measured background colour of the presentation backdrop.
BG_COLOUR = (12, 16, 21)

# Flood-fill tolerance. Measured plateau: the background pixel count changes by
# only ~1.3% between tolerance 6 and 14, then starts eating the character at 24.
# 14 sits safely in the middle of that plateau.
BG_TOLERANCE = 14

# --------------------------------------------------------------------------
# Output contract
# --------------------------------------------------------------------------
FRAME_W = 128
FRAME_H = 128
PIVOT_X = 64
PIVOT_Y = 119          # feet contact row - see docs/SPRITE_SPEC.md
SCALE_DIVISOR = 4      # exact integer downscale

# A 4x4 source block becomes one output pixel. It is opaque when at least this
# many of its 16 source pixels are opaque. 6/16 keeps 2-pixel-wide details such
# as the axe glow rim, while still discarding stray single pixels.
ALPHA_BLOCK_THRESHOLD = 6

# Feet contact row per view, in absolute source coordinates.
# Measured from row profiles; see module docstring.
FEET_ROW = {"Down": 729, "Up": 730, "Right": 730, "Left": 730}

# Which column group is which direction, left to right in the sheet.
# Confirmed from the helmet eye-slit: group 2 looks right, group 3 looks left.
GROUP_ORDER = ["Down", "Up", "Right", "Left"]


def log(message):
    print(message)


# --------------------------------------------------------------------------
def remove_background(img):
    """Binary alpha via border flood fill. Returns count of background pixels."""
    w, h, px = img.width, img.height, img.px
    tol2 = BG_TOLERANCE * BG_TOLERANCE
    br, bg_, bb = BG_COLOUR

    is_bg = bytearray(w * h)
    queue = deque()

    def push(x, y):
        p = y * w + x
        if is_bg[p]:
            return
        i = p * 4
        dr = px[i] - br
        dg = px[i + 1] - bg_
        db = px[i + 2] - bb
        if dr * dr + dg * dg + db * db <= tol2:
            is_bg[p] = 1
            queue.append(p)

    for x in range(w):
        push(x, 0)
        push(x, h - 1)
    for y in range(h):
        push(0, y)
        push(w - 1, y)

    while queue:
        p = queue.popleft()
        y, x = divmod(p, w)
        if x > 0:
            push(x - 1, y)
        if x < w - 1:
            push(x + 1, y)
        if y > 0:
            push(x, y - 1)
        if y < h - 1:
            push(x, y + 1)

    for p in range(w * h):
        px[p * 4 + 3] = 0 if is_bg[p] else 255

    return sum(is_bg)


def find_view_groups(img, min_gap=12):
    """Contiguous runs of columns containing foreground = one view each."""
    w, h, px = img.width, img.height, img.px
    groups = []
    start = None
    gap = 0
    for x in range(w):
        occupied = False
        for y in range(h):
            if px[(y * w + x) * 4 + 3]:
                occupied = True
                break
        if occupied:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                groups.append((start, x - gap + 1))
                start = None
                gap = 0
    if start is not None:
        groups.append((start, w))
    return groups


def vertical_bounds(img, x0, x1):
    w, px = img.width, img.px
    ys = [y for y in range(img.height)
          if any(px[(y * w + x) * 4 + 3] for x in range(x0, x1))]
    return (min(ys), max(ys) + 1) if ys else None


def helmet_centre(img, x0, x1, y0, rows=50):
    """
    Horizontal anchor = centre of the helmet mass in the top `rows` rows.

    The helmet is used rather than the boots because the axe occludes or merges
    with the boots in three of the four views. Where the boots ARE cleanly
    measurable (the Up view) the two agree to within 4 source pixels, which is
    1 pixel after the 4x downscale.
    """
    w, px = img.width, img.px
    xs = [x for y in range(y0, y0 + rows) for x in range(x0, x1)
          if px[(y * w + x) * 4 + 3]]
    return (min(xs) + max(xs)) / 2.0 if xs else (x0 + x1) / 2.0


# --------------------------------------------------------------------------
def sample_block_box(src, sx0, sy0, size, clip):
    """
    Area-average a `size` x `size` source block.

    RGB is averaged over OPAQUE source pixels only, so the transparent
    background can never bleed into the character's edge colours. Alpha is
    then forced to 0 or 255, so the result has hard edges and no halo.

    `clip` restricts sampling to this view's bounding box. One output frame
    spans 512 source pixels, which is far wider than the gaps between views
    in the turnaround, so without clipping the neighbouring characters leak
    into the frame.
    """
    w, px = src.width, src.px
    cx0, cy0, cx1, cy1 = clip
    r = g = b = 0
    n = 0
    for y in range(max(sy0, cy0), min(sy0 + size, cy1)):
        row = y * w
        for x in range(max(sx0, cx0), min(sx0 + size, cx1)):
            i = (row + x) * 4
            if px[i + 3]:
                r += px[i]
                g += px[i + 1]
                b += px[i + 2]
                n += 1
    if n < ALPHA_BLOCK_THRESHOLD:
        return (0, 0, 0, 0)
    return (r // n, g // n, b // n, 255)


def sample_block_nearest(src, sx0, sy0, size, clip):
    """Single source pixel from the block centre - true nearest neighbour."""
    w, px = src.width, src.px
    cx0, cy0, cx1, cy1 = clip
    x = sx0 + size // 2
    y = sy0 + size // 2
    if not (cx0 <= x < cx1 and cy0 <= y < cy1):
        return (0, 0, 0, 0)
    i = (y * w + x) * 4
    if not px[i + 3]:
        return (0, 0, 0, 0)
    return (px[i], px[i + 1], px[i + 2], 255)


def build_frame(src, head_cx, feet_row, mode, clip):
    """Composes one 128x128 frame anchored on (PIVOT_X, PIVOT_Y)."""
    out = ptk_png.Image(FRAME_W, FRAME_H)
    size = SCALE_DIVISOR
    sample = sample_block_box if mode == "box" else sample_block_nearest

    # Output row PIVOT_Y covers the `size` source rows ending on the feet row,
    # so the feet contact row lands exactly on the pivot.
    base_y = feet_row - (size - 1)
    base_x = int(round(head_cx)) - size // 2

    for oy in range(FRAME_H):
        sy0 = base_y + (oy - PIVOT_Y) * size
        for ox in range(FRAME_W):
            sx0 = base_x + (ox - PIVOT_X) * size
            rgba = sample(src, sx0, sy0, size, clip)
            if rgba[3]:
                out.set(ox, oy, rgba)
    return out


# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("box", "nearest"), default="box",
                        help="downscale method (default: box area-average)")
    parser.add_argument("--suffix", default="",
                        help="filename suffix, for producing comparison sets")
    args = parser.parse_args()

    if not os.path.isfile(SOURCE):
        log("ERROR: source not found: " + SOURCE)
        return 1

    os.makedirs(FRAMES_DIR, exist_ok=True)
    os.makedirs(CONCEPT_DIR, exist_ok=True)

    # Archive the untouched original for reference.
    archive = os.path.join(CONCEPT_DIR, "ravager_turnaround_source.png")
    if not os.path.exists(archive):
        shutil.copy2(SOURCE, archive)
        log("archived original -> " + os.path.relpath(archive, PROJECT))

    log("reading " + SOURCE)
    img = ptk_png.read_png(SOURCE)
    log("source: %dx%d" % (img.width, img.height))

    n_bg = remove_background(img)
    log("background removed: %d px (%.2f%%), binary alpha"
        % (n_bg, 100.0 * n_bg / (img.width * img.height)))

    groups = find_view_groups(img)
    log("view groups found: %d" % len(groups))
    if len(groups) != 4:
        log("ERROR: expected 4 views, got %d - aborting" % len(groups))
        return 1

    results = []
    for name, (x0, x1) in zip(GROUP_ORDER, groups):
        y0, y1 = vertical_bounds(img, x0, x1)
        head_cx = helmet_centre(img, x0, x1, y0)
        feet = FEET_ROW[name]
        results.append((name, x0, y0, x1, y1, head_cx, feet))
        log("  %-5s bbox x=%d..%d y=%d..%d (%dx%d)  helmet_cx=%.1f  feet_y=%d "
            "height=%d" % (name, x0, x1, y0, y1, x1 - x0, y1 - y0,
                           head_cx, feet, feet - y0))

    log("\ncomposing 128x128 frames (mode=%s, scale=1/%d, pivot=(%d,%d))"
        % (args.mode, SCALE_DIVISOR, PIVOT_X, PIVOT_Y))

    written = []
    for name, x0, y0, x1, y1, head_cx, feet in results:
        frame = build_frame(img, head_cx, feet, args.mode, (x0, y0, x1, y1))
        filename = "Idle_%s%s.png" % (name, args.suffix)
        path = os.path.join(FRAMES_DIR, filename)
        ptk_png.write_png(path, frame)
        written.append((name, filename, frame))

    # ---------------- verification ----------------
    log("\n--- verification ---")
    ok = True
    bottoms = {}
    for name, filename, frame in written:
        bounds = frame.opaque_bounds()
        if bounds is None:
            log("  FAIL %s is completely empty" % filename)
            ok = False
            continue
        bx0, by0, bx1, by1 = bounds

        semi = sum(1 for i in range(3, len(frame.px), 4)
                   if frame.px[i] not in (0, 255))
        touching = (bx0 <= 0 or by0 <= 0 or bx1 >= FRAME_W or by1 >= FRAME_H)

        bottoms[name] = by1 - 1
        log("  %-5s %dx%d  content x=%d..%d y=%d..%d  height=%d  "
            "semi-alpha=%d  clipped=%s"
            % (name, frame.width, frame.height, bx0, bx1 - 1, by0, by1 - 1,
               by1 - by0, semi, "YES" if touching else "no"))

        if frame.width != FRAME_W or frame.height != FRAME_H:
            log("       FAIL wrong canvas size")
            ok = False
        if semi:
            log("       FAIL semi-transparent pixels present")
            ok = False

    # Feet consistency: every view must bottom out at the pivot row, except
    # Down whose axe legitimately hangs below it.
    log("\n  feet/pivot check (pivot row = %d):" % PIVOT_Y)
    for name in GROUP_ORDER:
        if name not in bottoms:
            continue
        b = bottoms[name]
        note = "axe overhang below pivot (expected for Down)" if name == "Down" else ""
        flag = "ok" if (b == PIVOT_Y or name == "Down") else "CHECK"
        log("    %-5s lowest opaque row = %3d   %s %s" % (name, b, flag, note))
        if flag == "CHECK":
            ok = False

    log("\n%s" % ("VERIFICATION PASSED" if ok else "VERIFICATION FAILED"))
    log("wrote %d frames to %s" % (len(written), os.path.relpath(FRAMES_DIR, PROJECT)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
