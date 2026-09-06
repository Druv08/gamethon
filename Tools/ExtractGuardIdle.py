"""
Protect the King - 2D
Extracts the four REAL directional idle frames for Aegis and Wraith from their
character turnaround sheets.

    source : <Downloads>/gamethon pics/design 2d pics/<name> pics/<name>.png
             (READ ONLY - never renamed, moved or modified)
    output : ArtSource/Characters/Guards/<Name>/Frames/Idle/Idle_<Dir>.png

Run:  python Tools/ExtractGuardIdle.py --measure
      python Tools/ExtractGuardIdle.py
      python Tools/ExtractGuardIdle.py Aegis


WHY THIS EXISTS
---------------
Aegis and Wraith shipped with Idle_<Dir>.png copied from Walk_<Dir>_01 - the
walk cycle's contact pose - because no idle sheet was delivered with their
animations. It is a walking frame, so standing still looked like a man frozen
mid-stride.

The real standing art was there the whole time, in the turnaround sheet that
sits beside the animation sheets in each character's folder. Ravager's idle has
always come from exactly that source (see Tools/ExtractRavagerIdle.py); this
does the same for the other two, and is written for both at once so the third
and fourth guards need no new script.


HOW A TURNAROUND BECOMES FOUR FRAMES
------------------------------------
1. The presentation backdrop is removed by a flood fill inwards from the border,
   keeping pixels within BG_TOLERANCE of the measured corner colour. A flood
   fill rather than a colour key, because both characters contain thousands of
   pixels as dark as the backdrop - a key would punch holes through the armour.
   Connectivity is what separates "background" from "very dark armour".

   Measured: the background count is stable from tolerance 10 to 20 for both
   sheets (Aegis 75.4% -> 77.1%), and only starts eating Wraith at 28
   (81.5% -> 88.1%). 14 sits in the middle of that plateau, which is the value
   Ravager already uses.

2. Views are found as runs of occupied columns. Both sheets give exactly four,
   at every tolerance tried.

3. Each view is scaled so its body height matches the SAME target the character's
   walk and attack frames were normalised to - 122 for Aegis, 112 for Wraith -
   and composed onto the standard 192x192 canvas at pivot (96, 179). That is
   what stops the character changing size the moment it stops walking.


DIRECTIONS ARE PROVEN, NOT ASSUMED
----------------------------------
Down vs Up uses bright-blue coverage, the same test their walk sheets pass:
the front carries the shield emblem / hood eye, the back only a cape.
  Aegis   view0 4.07%  vs view1 0.49%
  Wraith  view0 1.71%  vs view1 0.03%

Left vs Right uses the outermost-blue-mass bias already calibrated on each
character's own walk sheets, where positive means LEFT.
  Aegis   view2 +0.243   view3 -0.216   -> a genuine mirrored pair
  Wraith  view2 +0.161   view3 +0.175   -> BOTH FACE LEFT

verify() re-runs both checks and refuses to write if the art contradicts them.


WRAITH HAS NO RIGHT-FACING IDLE, SO ONE IS MIRRORED
---------------------------------------------------
His turnaround is front, back, and two slightly different LEFT-facing views -
confirmed by measurement (both biases positive) and by overlaying view3 flipped
against view2, which does not match. There is no right-facing standing pose in
the delivered art.

Rather than invent one, Idle_Right is view3 flipped horizontally. That is an
exact pixel operation, not a redraw, and it is faithful to how this character is
already drawn: his own walk and attack sheets mirror his handedness between the
two sides, putting the bow on the leading hand and the quiver on the trailing
shoulder in both. Aegis needs none of this - all four of his views are real.
"""

import argparse
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_ROOT = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics"

CANVAS = (192, 192)
PIVOT = (96, 179)
DIRECTIONS = ("Down", "Up", "Left", "Right")

BG_TOLERANCE = 14
SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128


def is_energy(r, g, b):
    """Bright blue glow - excluded from geometry so it cannot drag the anchor."""
    return b > 150 and b - r > 80


CHARACTERS = {
    "Aegis": dict(
        source=os.path.join(ART_ROOT, "aegis pics", "aegis.png"),
        frames=os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Aegis", "Frames"),
        # Matches TARGET_BODY_HEIGHT in Tools/ExtractAegisAnimations.py.
        target_height=122.0,
        # view index -> direction. Measured, not assumed; see verify().
        views={0: "Down", 1: "Up", 2: "Left", 3: "Right"},
        mirror={},
    ),
    "Wraith": dict(
        source=os.path.join(ART_ROOT, "wraith pics", "wraith.png"),
        frames=os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Wraith", "Frames"),
        # Matches TARGET_BODY_HEIGHT in Tools/ExtractWraithAnimations.py.
        target_height=112.0,
        views={0: "Down", 1: "Up", 2: "Left"},
        # Right is view3 flipped - he has no right-facing pose. See the docstring.
        mirror={"Right": 3},
    ),
}


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


# ---------------------------------------------------------------------------
# Background and views
# ---------------------------------------------------------------------------
def remove_background(img, tolerance=BG_TOLERANCE):
    """Binary alpha via a border flood fill. Returns the background pixel count."""
    w, h, px = img.width, img.height, img.px
    br, bg, bb = px[0], px[1], px[2]
    tol2 = tolerance * tolerance

    is_bg = bytearray(w * h)
    queue = deque()

    def push(x, y):
        p = y * w + x
        if is_bg[p]:
            return
        i = p * 4
        dr = px[i] - br
        dg = px[i + 1] - bg
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


def find_views(img, min_gap=12):
    """Runs of occupied columns - one per view in the turnaround."""
    w, h, px = img.width, img.height, img.px
    out = []
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
                out.append((start, x - gap + 1))
                start = None
                gap = 0
    if start is not None:
        out.append((start, w))
    return out


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def bright_blue_fraction(img, box):
    x0, x1, y0, y1 = box
    w, px = img.width, img.px
    total = hot = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * w + x) * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            total += 1
            if px[i + 2] > 190 and px[i + 2] - px[i] > 90:
                hot += 1
    return (100.0 * hot / total) if total else 0.0


def facing_bias(img, box):
    """Positive = leans LEFT. The metric each character's walk sheets calibrated."""
    x0, x1, y0, y1 = box
    w, px = img.width, img.px
    body = []
    blue = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * w + x) * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            body.append(x)
            if px[i + 2] > 170 and px[i + 2] - px[i] > 70:
                blue.append(x)
    if not body or not blue:
        return 0.0
    centre = sum(body) / float(len(body))
    span = (max(body) - min(body)) or 1
    blue.sort()
    k = max(1, len(blue) // 5)
    left = (centre - sum(blue[:k]) / float(k)) / span
    right = (sum(blue[-k:]) / float(k) - centre) / span
    return left - right


def verify(name, cfg, img, boxes):
    """Refuses to continue if the art contradicts cfg['views']."""
    plan = dict(cfg["views"])
    for direction, index in cfg["mirror"].items():
        plan[index] = direction + " (mirrored)"

    down = [i for i, d in cfg["views"].items() if d == "Down"]
    up = [i for i, d in cfg["views"].items() if d == "Up"]
    if not down or not up:
        fail(name + ": the view plan must name a Down and an Up")

    front = bright_blue_fraction(img, boxes[down[0]])
    back = bright_blue_fraction(img, boxes[up[0]])
    if front <= back:
        fail("{0}: view{1} reads {2:.2f}% bright blue and view{3} {4:.2f}% - the "
             "front must carry MORE, so the Down/Up mapping is wrong"
             .format(name, down[0], front, up[0], back))

    notes = ["Down/Up: front {0:.2f}% vs back {1:.2f}% bright blue".format(front, back)]

    for index, direction in cfg["views"].items():
        if direction not in ("Left", "Right"):
            continue
        bias = facing_bias(img, boxes[index])
        want_left = direction == "Left"
        if (bias > 0.0) != want_left:
            fail("{0}: view{1} bias {2:+.3f} but it is mapped to {3} - positive "
                 "means LEFT, so the mapping is wrong".format(name, index, bias, direction))
        notes.append("view{0} bias {1:+.3f} -> {2}".format(index, bias, direction))

    for direction, index in cfg["mirror"].items():
        bias = facing_bias(img, boxes[index])
        notes.append("view{0} bias {1:+.3f} (flipped to make {2} - no {2}-facing "
                     "pose exists)".format(index, bias, direction))
    return notes


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def measure(img, box):
    """Feet row, silhouette top and hip centre, measured off the body only."""
    x0, x1, y0, y1 = box
    view = img.crop(x0, y0, x1, y1)
    body, _full, w, h = ptk_sheet.build_masks(view, SRC_ALPHA_THRESHOLD, is_energy)
    rows = [sum(body[y * w:(y + 1) * w]) for y in range(h)]
    foot_threshold = max(2, int(round(0.030 * w)))
    head_threshold = max(2, int(round(0.022 * w)))

    solid = [y for y in range(h) if rows[y] >= foot_threshold]
    heads = [y for y in range(h) if rows[y] >= head_threshold]
    if not solid or not heads:
        return None
    feet = solid[-1]
    top = heads[0]
    span = feet - top

    lo = max(0, int(feet - span * 0.55))
    hi = min(h - 1, int(feet - span * 0.35))
    xs = [x for y in range(lo, hi + 1) for x in range(w) if body[y * w + x]]
    if not xs:
        return None
    return dict(feet=feet, top=top, height=span + 1,
                centre=sum(xs) / float(len(xs)))


def mirrored(img):
    """Exact horizontal flip - an index permutation, no resampling."""
    out = ptk_png.Image(img.width, img.height)
    for y in range(img.height):
        for x in range(img.width):
            out.set(img.width - 1 - x, y, img.get(x, y))
    return out


# ---------------------------------------------------------------------------
def build(name, cfg, measure_only):
    if not os.path.isfile(cfg["source"]):
        fail("source turnaround missing: " + cfg["source"])

    img = ptk_png.read_png(cfg["source"])
    background = remove_background(img)
    views = find_views(img)
    if len(views) != 4:
        fail("{0}: expected 4 views in the turnaround, found {1}".format(name, len(views)))

    w, h, px = img.width, img.height, img.px
    boxes = []
    for x0, x1 in views:
        ys = [y for y in range(h) if any(px[(y * w + x) * 4 + 3] for x in range(x0, x1))]
        boxes.append((x0, x1, min(ys), max(ys) + 1))

    log("")
    log("=" * 76)
    log("{0}  <-  {1}".format(name, os.path.basename(cfg["source"])))
    log("  background removed: {0} px ({1:.1f}%) at tolerance {2}".format(
        background, 100.0 * background / (w * h), BG_TOLERANCE))
    for note in verify(name, cfg, img, boxes):
        log("  identity: " + note)

    plan = []
    for index, direction in sorted(cfg["views"].items()):
        plan.append((direction, index, False))
    for direction, index in sorted(cfg["mirror"].items()):
        plan.append((direction, index, True))

    out_dir = os.path.join(cfg["frames"], "Idle")
    if not measure_only and not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    written = []
    for direction, index, flip in sorted(plan, key=lambda p: DIRECTIONS.index(p[0])):
        x0, x1, y0, y1 = boxes[index]
        m = measure(img, boxes[index])
        if m is None:
            fail("{0}: view{1} is empty".format(name, index))
        scale = cfg["target_height"] / float(m["height"])

        log("  {0:<5s} view{1}{2}  body {3} px -> x{4:.4f}  ({5} px finished)".format(
            direction, index, " flipped" if flip else "        ",
            m["height"], scale, int(round(m["height"] * scale))))
        if measure_only:
            continue

        frame = ptk_sheet.render_frame(
            img, x0, y0, x1 - x0, y1 - y0,
            m["centre"], m["feet"], scale, CANVAS, PIVOT,
            x_bounds=(x0, x1))
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        if flip:
            frame = mirrored(frame)

        clipped = ptk_sheet.border_contact(frame)
        if clipped:
            fail("{0} Idle_{1} is clipped by the canvas ({2} px on the edge)".format(
                name, direction, clipped))

        path = os.path.join(out_dir, "Idle_{0}.png".format(direction))
        ptk_png.write_png(path, frame)
        written.append(direction)

    if not measure_only:
        log("  wrote {0} real idle frames: {1}".format(len(written), ", ".join(written)))
    return True


def main():
    parser = argparse.ArgumentParser(description="Extract real guard idle frames.")
    parser.add_argument("characters", nargs="*", default=None)
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    wanted = args.characters or sorted(CHARACTERS)
    log("Guard idle extraction - real standing poses from the turnaround sheets")
    for name in wanted:
        cfg = CHARACTERS.get(name)
        if cfg is None:
            fail("unknown character: " + name)
        build(name, cfg, args.measure)
    log("")
    log("done")


if __name__ == "__main__":
    main()
