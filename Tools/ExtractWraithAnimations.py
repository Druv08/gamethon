"""
Protect the King - 2D
Extracts Wraith (ranged / stealth archer guard) into finished Paper2D frames,
including the arrow projectile and its impact burst.

    source : <Downloads>/gamethon pics/design 2d pics/wraith pics/*.png  (READ ONLY)
    output : ArtSource/Characters/Guards/Wraith/Frames/<Anim>/<Dir>/...
             ArtSource/Characters/Guards/Wraith/Frames/Arrow/<Dir>/...
             ArtSource/Characters/Guards/Wraith/Frames/Impact/...
             ArtSource/Characters/Guards/Wraith/Sheets/Wraith_<Anim>_8F.png

Run:  python Tools/ExtractWraithAnimations.py --measure
      python Tools/ExtractWraithAnimations.py

Uses the shared machinery in Tools/ptk_sheet.py, so every correction proven on
Ravager, Swarm Node, the King and Aegis applies here unchanged.


WHICH SHEET IS WHICH
--------------------
Six sheets arrived as opaque GUIDs. Each was identified by looking at it and
then confirmed by measurement - never by filename:

  8e30f7af  2x8  row0 hood-eye and chest gems toward camera, row1 the caped
                 back and quiver                    -> WALK   Down / Up
  9282988d  2x8  the same stride in profile         -> WALK   Left / Right
  553fc97a  2x8  bow drawn front and back, arrow gone by frame 6
                                                    -> ATTACK Down / Up
  8d933dd3  2x8  the same shot in profile, arrow visibly leaving
                                                    -> ATTACK Left / Right
  c3bd4219  1x8  he staggers, sinks, falls forward and dissolves into blue
                 wisps                              -> DEATH (non-directional)
  80f4915d  1x8  bow + nocked arrow, arrow in flight, impact on a grey test
                 dummy                              -> PROJECTILE + IMPACT

wraith.png is a 1448x1086 RGB turnaround (front / back / two profiles) with no
alpha - a design reference, not an animation. It carries no
animation, but it IS the source of the four real idle frames - see
Tools/ExtractGuardIdle.py.

HOW DIRECTION WAS PROVEN, NOT ASSUMED
-------------------------------------
Down vs Up: the front view carries the glowing hood eye and the chest gems, the
back view only the cape and quiver. Measured as bright-blue coverage, the walk
sheet reads 3.33% front against 0.47% back - a 7x separation.

Left vs Right: Wraith settles this better than any character so far, because he
fires a visible arrow. On the profile attack sheet row0's arrow travels
screen-LEFT and row1's screen-RIGHT, which is facing itself rather than a proxy
for it. The same outermost-blue-mass metric used for Aegis agrees and is
unanimous on both profile sheets: walk row0 +0.275 with 8/8 frames voting left
and row1 -0.243 with 8/8 voting right; attack row0 +0.401 and row1 -0.378,
peaking at frame 5 where the arrow is at full draw.

verify_identity() re-runs both checks and REFUSES to write if the art ever
contradicts the mapping below.


THE IDLE FRAMES COME FROM THE TURNAROUND, NOT FROM WALK
------------------------------------------------------
No idle sheet shipped with the animation sheets, so Idle_<Dir>.png used to be a
copy of Walk_<Dir>_01. That is still a walking frame, and standing still read as
a man frozen mid-stride.

The real standing poses were in the turnaround sheet all along - the same source
Ravager's idle has always used. They are extracted by Tools/ExtractGuardIdle.py;
this script only checks they are present, so re-running it can never put the
walk frame back.


THE RELEASED ARROW IS DELIBERATELY REMOVED FROM THE ATTACK FRAMES
----------------------------------------------------------------
Frames 6-8 of every attack row draw the arrow already gone from the bow and
flying away. In game that arrow is a real actor - APTKProjectile - spawned at
the release frame, so if the flipbook drew one too there would be two arrows
leaving the same bow a few pixels apart.

The nocked arrow in frames 2-5 touches the bowstring and hands and must stay;
the detached arrow in frames 6-8 must go. A plain connected-component flood
would do that, but it also erases his BOW, which parts from his arm by a pixel
on the frame after release - so the sheet came out with an archer holding
nothing. ptk_sheet.clean_islands() splits the decision instead: detached and
bright is a fired arrow and goes, detached and dark is his own gear and stays.

Two other things had to be right for that rule to be safe. Sampling is clamped
to the cell (x_bounds), because these sheets are drawn edge to edge - the
profile walk has no gutters at all - and without it a neighbour's arrow would
arrive as "detached bright art" and be judged as ours. And distance is true
pixel distance rather than bounding-box distance, because a drawn bow stretches
the box far to one side and a box test then calls the neighbour's cape close.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\wraith pics"
WRAITH = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Wraith")
FRAMES_DIR = os.path.join(WRAITH, "Frames")
SHEETS_DIR = os.path.join(WRAITH, "Sheets")

COLUMNS = 8
DIRECTIONS = ("Down", "Up", "Left", "Right")

SHEETS = [
    dict(anim="Walk",   rows=("Down", "Up"),
         file="8e30f7af-da8f-4047-abfe-828dd7a35c39.png"),
    dict(anim="Walk",   rows=("Left", "Right"),
         file="9282988d-1afe-458e-b264-529fa58a926a.png"),
    dict(anim="Attack", rows=("Down", "Up"),
         file="553fc97a-6e73-407e-9de2-06914e1c2990.png"),
    dict(anim="Attack", rows=("Left", "Right"),
         file="8d933dd3-9078-41dd-90c0-10a05c18a1d2.png"),
]
DEATH_FILE = "c3bd4219-78a6-4454-b251-8fb5f78e231a.png"

# The projectile strip, 1x8, read by content:
#   cells 1-2  bow with the arrow nocked and charging
#   cells 3-5  the arrow in flight, trail lengthening
#   cells 6-8  impact on a grey test dummy
#
# Cells 1-2 are NOT extracted. They draw the bow, and Wraith already carries a
# bow in his own attack frames - shipping them as projectile art would fire a
# second bow across the map. They are the artist's "here is where it comes
# from" panel, not a frame of the arrow.
PROJECTILE_FILE = "80f4915d-2d0d-42b6-a027-e2ebf34bd552.png"
FLIGHT_CELLS = (2, 3, 4)     # 0-based -> source cells 3, 4, 5
IMPACT_CELLS = (5, 6, 7)     # 0-based -> source cells 6, 7, 8

# 192x192, pivot (96, 179) - the project's standard canvas, shared with
# Ravager, Swarm Node and Aegis. main() re-measures this every run and refuses
# to write if Wraith ever stops fitting it.
# 224x224 with the pivot at (112, 200), shared by every guard.
#
# It used to be 192x192 at (96, 179), which left Ravager 9 px of clearance at
# his sides and 4 px under his boots, and Sentinel 6 px over his crown. Nothing
# was actually clipped, but a body that nearly fills its box has no room for a
# taller pose or a wider swing, and it reads on screen as a character whose head
# has been shaved off. The box is now big enough that the worst frame of the
# worst guard still has ~20 px of air around it.
#
# This is MARGIN, not scale: the character is drawn at exactly the same size and
# his feet still land on the pivot. Only the transparent border grows.
CANVAS = (224, 224)
PIVOT = (112, 200)

# Hood-to-feet in the finished frames. Ravager stands 116 and Aegis 122; Wraith
# is given 112 because he is the light, quick one and should read as the
# smaller figure on a field that already has a bruiser and a tank.
TARGET_BODY_HEIGHT = 116.0

# The arrow canvas is square with a true centre pixel, which is what makes the
# four directions exact 90-degree rotations of one another - a lossless index
# permutation, no resampling, no mirroring, no distortion of pixel art.
ARROW_CANVAS = 129
ARROW_PIVOT = (ARROW_CANVAS // 2, ARROW_CANVAS // 2)

# The impact burst is radial, so it needs no directions - one set of frames
# centred on its own bright core.
IMPACT_CANVAS = 129
IMPACT_PIVOT = (IMPACT_CANVAS // 2, IMPACT_CANVAS // 2)

SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128

# How far from Wraith a detached island may sit before it is judged to be the
# neighbouring frame rather than his own gear.
#
# The death sheet needs a tight one. Its frames overlap by nearly 190px - the
# collapse is drawn wide and the artist let the figures run into one another -
# so the neighbour lands close to the corpse and only a small gap separates
# them. The attack sheet needs a loose one for the opposite reason: his bow
# parts from his arm by a few pixels on the frame after release, and at 3 it
# would be thrown away with the spill.
MAX_GAP = dict(Death=3)
DEFAULT_MAX_GAP = 8


def is_energy(r, g, b):
    """
    Bright blue: the hood eye, the chest gems, the nocked arrow and its glow.

    Wraith is a blue character head to foot, so this threshold matters more for
    him than for anyone before. His cloak and armour top out around b=120, well
    under the b>150 gate, so nothing of his body qualifies and geometry is
    still measured off the man rather than off his glow.
    """
    return b > 150 and b - r > 80


def is_burst(r, g, b):
    """
    Impact-burst energy, used to strip the grey test dummy out of cells 6-8.

    The dummy is neutral - (0,0,0), (24,24,24), (48,48,48) - so it fails both
    halves of this test, while the burst is saturated blue with a white core.
    """
    return (b - r) > 40 or min(r, g, b) > 180


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


# ---------------------------------------------------------------------------
# Identity - prove each sheet is what the table above claims
# ---------------------------------------------------------------------------
def bright_blue_fraction(img):
    w, h, px = img.width, img.height, img.px
    total = hot = 0
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            total += 1
            if px[i + 2] > 190 and px[i + 2] - px[i] > 90:
                hot += 1
    return (100.0 * hot / total) if total else 0.0


def facing_reach(img):
    """
    (left, right) - how far the outermost blue mass reaches past the body
    centre, as a fraction of silhouette width.

    For Wraith the outermost blue IS the arrow when he is shooting and the hood
    eye when he is walking, and both sit on the side he faces. The outermost
    fifth is used rather than the centroid so the chest gems, which lie across
    his body in every pose, cannot wash the signal out.
    """
    w, h, px = img.width, img.height, img.px
    body = []
    blue = []
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            body.append(x)
            if px[i + 2] > 170 and px[i + 2] - px[i] > 70:
                blue.append(x)
    if not body or not blue:
        return None
    centre = sum(body) / float(len(body))
    span = (max(body) - min(body)) or 1
    blue.sort()
    k = max(1, len(blue) // 5)
    return ((centre - sum(blue[:k]) / float(k)) / span,
            (sum(blue[-k:]) / float(k) - centre) / span)


def verify_identity(spec, cells):
    """Refuses to continue if the art contradicts spec['rows']."""
    rows = spec["rows"]
    if rows == ("Down", "Up"):
        front = sum(bright_blue_fraction(cells[0][c]) for c in range(COLUMNS)) / COLUMNS
        back = sum(bright_blue_fraction(cells[1][c]) for c in range(COLUMNS)) / COLUMNS
        if front <= back:
            fail("{0}: row0 reads {1:.2f}% bright blue and row1 {2:.2f}% - the front "
                 "view must carry MORE (the hood eye and chest gems face the camera), "
                 "so the Down/Up mapping is wrong".format(spec["file"][:8], front, back))
        return "front {0:.2f}% vs back {1:.2f}% bright blue".format(front, back)

    left = [facing_reach(cells[0][c]) for c in range(COLUMNS)]
    right = [facing_reach(cells[1][c]) for c in range(COLUMNS)]
    lm = sum(v[0] - v[1] for v in left if v) / COLUMNS
    rm = sum(v[0] - v[1] for v in right if v) / COLUMNS
    votes_l = sum(1 for v in left if v and (v[0] - v[1]) > 0)
    votes_r = sum(1 for v in right if v and (v[0] - v[1]) < 0)
    if not (lm > 0.0 > rm):
        fail("{0}: row0 bias {1:+.3f} and row1 {2:+.3f} - row0 must lean LEFT "
             "(positive) and row1 RIGHT (negative), so the Left/Right mapping is "
             "wrong".format(spec["file"][:8], lm, rm))
    return ("left bias {0:+.3f} ({1}/8 frames) vs right bias {2:+.3f} ({3}/8)"
            .format(lm, votes_l, rm, votes_r))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def body_metrics(cell, reference_height):
    """
    Ground contact, silhouette top and hip centre, measured off the body only.

    The hips band is located from `reference_height`, not from this frame's own
    height, so that a raised bow arm cannot slide the band down onto the legs
    and make the centre incomparable between frames of the same shot.
    """
    body, _full, w, h = ptk_sheet.build_masks(cell, SRC_ALPHA_THRESHOLD, is_energy)
    rows = [sum(body[y * w:(y + 1) * w]) for y in range(h)]
    foot_threshold = max(2, int(round(0.030 * w)))
    head_threshold = max(2, int(round(0.022 * w)))

    solid = [y for y in range(h) if rows[y] >= foot_threshold]
    heads = [y for y in range(h) if rows[y] >= head_threshold]
    if not solid or not heads:
        return None
    feet = solid[-1]
    # The hood/helm cap, not the topmost opaque row: a weapon raised over the
    # head is not part of how tall the character is, and counting it made the
    # frame measure taller than the body and scale down to compensate.
    cap = ptk_sheet.head_cap(cell, SRC_ALPHA_THRESHOLD, is_energy)
    top = cap[0] if cap else heads[0]

    span = reference_height if reference_height else (feet - top)
    y0 = max(0, int(feet - span * 0.55))
    y1 = min(h - 1, int(feet - span * 0.35))
    xs = [x for y in range(y0, y1 + 1) for x in range(w) if body[y * w + x]]
    if not xs:
        return None
    return dict(feet=feet, top=top, body=feet - top + 1,
                centre=sum(xs) / float(len(xs)), bottom=feet)


def plan_sheet(anim, cells, rows_count, cell_w):
    """Per-sheet scale, per-frame metrics and the anchor scheme."""
    def measure(reference):
        return [[body_metrics(cells[r][c], reference) for c in range(COLUMNS)]
                for r in range(rows_count)]

    raw = measure(cell_w * 1.05)
    if any(m is None for row in raw for m in row):
        fail(anim + ": a frame is empty")

    if anim == "Walk":
        heights = sorted(m["body"] for row in raw for m in row)
    else:
        # Frames 1 and 8 are ready / return-to-ready: the only poses in the shot
        # whose height is not inflated by the bow arm being raised.
        heights = sorted(raw[r][c]["body"]
                         for r in range(rows_count) for c in (0, COLUMNS - 1))
    reference = heights[len(heights) // 2]

    metrics = measure(reference)
    scale = TARGET_BODY_HEIGHT / float(reference)

    anchors = []
    for r in range(rows_count):
        # Walk plays in place, so every frame is pinned and the drift goes.
        # Attack braces and recovers and death collapses forward, so those rows
        # get ONE anchor and the motion survives.
        anchors.append(ptk_sheet.anchors_for_row(metrics[r], hold_still=(anim == "Walk")))
    return metrics, anchors, scale, reference


def required(metrics, anchors, cells, rows_count, scale):
    """Worst-case reach from the anchor, in finished-frame pixels."""
    need = [0.0, 0.0, 0.0, 0.0]
    for r in range(rows_count):
        for c in range(COLUMNS):
            _body, full, w, h = ptk_sheet.build_masks(
                cells[r][c], SRC_ALPHA_THRESHOLD, is_energy)
            x0, x1, y0, y1 = ptk_sheet.mask_bounds(full, w, h)
            ax, ay = anchors[r][c]
            need[0] = max(need[0], (ax - x0) * scale)
            need[1] = max(need[1], (x1 - ax) * scale)
            need[2] = max(need[2], (ay - y0) * scale)
            need[3] = max(need[3], (y1 - ay) * scale)
    return need


# ---------------------------------------------------------------------------
# Pipeline - character
# ---------------------------------------------------------------------------
def load(spec_file, rows_count):
    path = os.path.join(SOURCE_DIR, spec_file)
    if not os.path.isfile(path):
        fail("source sheet missing: " + path)
    sheet = ptk_png.read_png(path)
    grid = ptk_sheet.Grid(sheet, COLUMNS, rows_count)
    cells = [[grid.cell(c, r) for c in range(COLUMNS)] for r in range(rows_count)]
    return sheet, grid, cells


def write_frames(sheet, grid, cells, anim, rows, metrics, anchors, scale, rows_count):
    results = []
    for r in range(rows_count):
        direction = rows[r] if rows else None
        out_dir = (os.path.join(FRAMES_DIR, anim, direction) if direction
                   else os.path.join(FRAMES_DIR, anim))
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)

        for c in range(COLUMNS):
            ox, oy = grid.origin(c, r)
            ax, ay = anchors[r][c]
            # Wraith's sheets are drawn edge to edge - the profile walk has no
            # gutters at all - so the usual fence still reaches the neighbour.
            # Bounding sampling to the cell makes foreign content impossible,
            # which is what lets the cleanup below judge the leftovers purely
            # by colour.
            bounds = (ox, int(round((c + 1) * grid.cell_w)))
            frame = ptk_sheet.render_frame(
                sheet, ox, oy, grid.cell_w, grid.cell_h,
                ax, ay, scale, CANVAS, PIVOT, x_bounds=bounds)
            ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
            # Seeded on the chest: high enough to be body in every pose, low
            # enough that the last death frame still has him there.
            #
            # Anything beyond MAX_GAP is the neighbouring frame's cape, which
            # overlaps into this cell where clamping cannot reach it.
            # Within that distance, on ATTACK only, a detached BRIGHT island is
            # the released arrow and goes, because the game spawns a real one -
            # while his bow, which parts from his arm by a pixel on the frame
            # after release, is dark and stays. Death keeps its blue dissolve.
            dropped = ptk_sheet.clean_islands(
                frame, (PIVOT[0], PIVOT[1] - 40), is_energy,
                max_gap=MAX_GAP.get(anim, DEFAULT_MAX_GAP),
                drop_effect=(anim == "Attack"))
            clipped = ptk_sheet.border_contact(frame)
            name = ("{0}_{1}_{2:02d}.png".format(anim, direction, c + 1) if direction
                    else "{0}_{1:02d}.png".format(anim, c + 1))
            ptk_png.write_png(os.path.join(out_dir, name), frame)
            results.append(dict(name=name, dropped=dropped, clipped=clipped))
            note = ""
            if dropped:
                note += "  strays removed {0}px".format(dropped)
            if clipped:
                note += "  CLIPPED {0}px".format(clipped)
            log("    {0}{1}".format(name, note))
    return results


def contact_sheet(anim, rows, rows_count):
    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    cw, ch = CANVAS
    out = ptk_png.Image(cw * COLUMNS, ch * rows_count)
    for r in range(rows_count):
        for c in range(COLUMNS):
            if rows:
                p = os.path.join(FRAMES_DIR, anim, rows[r],
                                 "{0}_{1}_{2:02d}.png".format(anim, rows[r], c + 1))
            else:
                p = os.path.join(FRAMES_DIR, anim, "{0}_{1:02d}.png".format(anim, c + 1))
            out.paste(ptk_png.read_png(p), c * cw, r * ch)
    tag = "_".join(rows) if rows else ""
    name = "Wraith_{0}{1}_8F.png".format(anim, ("_" + tag) if tag else "")
    ptk_png.write_png(os.path.join(SHEETS_DIR, name), out)
    log("  sheet  {0}  ({1}x{2})".format(name, out.width, out.height))


def check_idle():
    """
    Idle is NOT produced here any more.

    These frames used to be a copy of Walk_<Dir>_01 - the walk cycle's contact
    pose - because no idle art shipped with the animation sheets. It was still a
    walking frame, so standing still read as a man frozen mid-stride.

    The real standing poses come from the character turnaround sheet, extracted
    by Tools/ExtractGuardIdle.py. This only checks they are present, so that
    re-running this script can never quietly put the walk frame back.
    """
    out_dir = os.path.join(FRAMES_DIR, "Idle")
    missing = [d for d in DIRECTIONS
               if not os.path.isfile(os.path.join(out_dir, "Idle_{0}.png".format(d)))]
    if missing:
        fail("real idle frames missing: {0}. Run: python Tools/ExtractGuardIdle.py {1}"
             .format(", ".join(missing), "Wraith"))
    log("  idle   4 real standing frames present "
        "(from the turnaround - see Tools/ExtractGuardIdle.py)")


# ---------------------------------------------------------------------------
# Pipeline - projectile
# ---------------------------------------------------------------------------
def largest_component(img):
    """
    Keeps only the biggest island of opaque pixels. Returns pixels discarded.

    The arrow's trail runs the full width of its cell, so a neighbouring
    frame's trail bleeds into this one. The arrow itself is always the largest
    thing present, which makes "keep the biggest island" the right rule here -
    unlike the character, who needs a seeded flood so that a bright effect can
    never out-mass him.
    """
    w, h, px = img.width, img.height, img.px
    from collections import deque
    solid = [px[i * 4 + 3] > 0 for i in range(w * h)]
    total = sum(1 for v in solid if v)
    if not total:
        return 0
    seen = bytearray(w * h)
    best = []
    for start in range(w * h):
        if not solid[start] or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        island = []
        while queue:
            k = queue.popleft()
            island.append(k)
            x, y = k % w, k // w
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if solid[j] and not seen[j]:
                        seen[j] = 1
                        queue.append(j)
        if len(island) > len(best):
            best = island
    keep = set(best)
    for k in range(w * h):
        if solid[k] and k not in keep:
            px[k * 4 + 3] = 0
    return total - len(best)


def effect_centroid(cell, predicate):
    """Alpha-weighted centroid and bounds of the pixels passing `predicate`."""
    w, h, px = cell.width, cell.height, cell.px
    sx = sy = n = 0
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            if not predicate(px[i], px[i + 1], px[i + 2]):
                continue
            sx += x
            sy += y
            n += 1
            x0 = min(x0, x)
            x1 = max(x1, x)
            y0 = min(y0, y)
            y1 = max(y1, y)
    if not n:
        return None
    return dict(cx=sx / float(n), cy=sy / float(n), area=n,
                x0=x0, x1=x1, y0=y0, y1=y1)


def rotate90(img, turns):
    """
    Exact 90-degree rotation, counter-clockwise, `turns` times.

    This is an index permutation: every source pixel lands on exactly one
    destination pixel, so it is lossless. It is how the four arrow directions
    are produced from one horizontal drawing without resampling, without
    mirroring, and without any distortion of the pixel art.
    """
    turns %= 4
    if turns == 0:
        return img
    w, h = img.width, img.height
    for _ in range(turns):
        out = ptk_png.Image(h, w)
        for y in range(h):
            for x in range(w):
                # CCW: (x, y) -> (y, w - 1 - x)
                out.set(y, w - 1 - x, img.get(x, y))
        img = out
        w, h = img.width, img.height
    return img


def write_projectile(scale):
    """
    Arrow flight and impact frames.

    The arrow is drawn once, pointing screen-right, and the other three
    directions are exact 90-degree rotations of it on a square canvas with a
    true centre pixel. The impact burst is radial and therefore has no
    directions at all.

    `scale` is the mean of the two attack sheets' normalisation, because the
    arrow was drawn in the same cell width by the same generator: normalising
    it the same way is what keeps the arrow that leaves the bow the same size
    as the arrow that was on it.
    """
    path = os.path.join(SOURCE_DIR, PROJECTILE_FILE)
    if not os.path.isfile(path):
        fail("projectile sheet missing: " + path)
    sheet = ptk_png.read_png(path)
    grid = ptk_sheet.Grid(sheet, COLUMNS, 1)

    report = dict(flight=[], impact=[])

    # ---- flight ---------------------------------------------------------
    # Anchored on the arrowHEAD, not on the whole silhouette: the trail grows
    # from frame to frame, so a silhouette centroid would slide backwards and
    # the arrow would appear to stutter as it flew.
    arrow_dir = os.path.join(FRAMES_DIR, "Arrow")
    for direction in DIRECTIONS:
        d = os.path.join(arrow_dir, direction)
        if not os.path.isdir(d):
            os.makedirs(d)

    # CCW turns that take a right-pointing arrow to each screen direction.
    # Screen-up is -Y in image space, so one CCW turn points it up.
    TURNS = dict(Right=0, Up=1, Left=2, Down=3)

    for n, c in enumerate(FLIGHT_CELLS):
        cell = grid.cell(c, 0)
        head = effect_centroid(cell, lambda r, g, b: not is_burst(r, g, b))
        glow = effect_centroid(cell, is_burst)
        if head is None or glow is None:
            fail("projectile cell {0}: no arrow found".format(c + 1))
        # The head's dark outline gives the tip; the glow gives the axis.
        ax = (head["x0"] + head["x1"]) / 2.0
        ay = (head["y0"] + head["y1"]) / 2.0

        frame = ptk_sheet.render_frame(
            sheet, *grid.origin(c, 0), cell_w=grid.cell_w, cell_h=grid.cell_h,
            anchor_x=ax, anchor_y=ay, scale=scale,
            canvas=(ARROW_CANVAS, ARROW_CANVAS), pivot=ARROW_PIVOT,
            fence_fraction=0.5)
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        dropped = largest_component(frame)

        for direction in DIRECTIONS:
            turned = rotate90(frame, TURNS[direction])
            name = "Arrow_{0}_{1:02d}.png".format(direction, n + 1)
            ptk_png.write_png(os.path.join(arrow_dir, direction, name), turned)
        b = ptk_sheet.mask_bounds(
            bytearray(1 if frame.px[i * 4 + 3] else 0
                      for i in range(frame.width * frame.height)),
            frame.width, frame.height)
        report["flight"].append(dict(cell=c + 1, dropped=dropped, bounds=b))
        log("    Arrow_<4 dirs>_{0:02d}.png   from source cell {1}"
            "   spill removed {2}px".format(n + 1, c + 1, dropped))

    # ---- impact ---------------------------------------------------------
    # The grey test dummy is stripped by is_burst: it is a mannequin the artist
    # drew to show the hit landing, not part of the effect.
    impact_dir = os.path.join(FRAMES_DIR, "Impact")
    if not os.path.isdir(impact_dir):
        os.makedirs(impact_dir)

    for n, c in enumerate(IMPACT_CELLS):
        cell = grid.cell(c, 0)
        burst = effect_centroid(cell, is_burst)
        if burst is None:
            fail("projectile cell {0}: no burst found".format(c + 1))

        stripped = ptk_png.Image(cell.width, cell.height)
        px, sp = cell.px, stripped.px
        for i in range(0, len(px), 4):
            if px[i + 3] >= SRC_ALPHA_THRESHOLD and is_burst(px[i], px[i + 1], px[i + 2]):
                sp[i:i + 4] = px[i:i + 4]
        removed = (sum(1 for i in range(3, len(px), 4) if px[i] >= SRC_ALPHA_THRESHOLD)
                   - burst["area"])

        frame = ptk_sheet.render_frame(
            stripped, 0, 0, cell_w=stripped.width, cell_h=stripped.height,
            anchor_x=burst["cx"], anchor_y=burst["cy"], scale=scale,
            canvas=(IMPACT_CANVAS, IMPACT_CANVAS), pivot=IMPACT_PIVOT,
            fence_fraction=0.5)
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        name = "Impact_{0:02d}.png".format(n + 1)
        ptk_png.write_png(os.path.join(impact_dir, name), frame)
        report["impact"].append(dict(cell=c + 1, dummy=removed, area=burst["area"]))
        log("    {0}   from source cell {1}   test dummy removed {2}px"
            .format(name, c + 1, removed))

    # ---- contact sheet --------------------------------------------------
    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    out = ptk_png.Image(ARROW_CANVAS * 3, ARROW_CANVAS * 5)
    for n in range(3):
        for row, direction in enumerate(DIRECTIONS):
            p = os.path.join(arrow_dir, direction,
                             "Arrow_{0}_{1:02d}.png".format(direction, n + 1))
            out.paste(ptk_png.read_png(p), n * ARROW_CANVAS, row * ARROW_CANVAS)
        p = os.path.join(impact_dir, "Impact_{0:02d}.png".format(n + 1))
        out.paste(ptk_png.read_png(p), n * ARROW_CANVAS, 4 * ARROW_CANVAS)
    ptk_png.write_png(os.path.join(SHEETS_DIR, "Wraith_Projectile.png"), out)
    log("  sheet  Wraith_Projectile.png  ({0}x{1})  rows: Down Up Left Right Impact"
        .format(out.width, out.height))
    return report


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def choose_canvas():
    """Measure every sheet first, then check one canvas holds them all."""
    worst = [0.0, 0.0, 0.0, 0.0]
    report = []
    for spec in SHEETS + [dict(anim="Death", rows=None, file=DEATH_FILE)]:
        rows_count = 1 if spec["rows"] is None else 2
        sheet, grid, cells = load(spec["file"], rows_count)
        anim = spec["anim"]
        if spec["rows"]:
            how = verify_identity(spec, cells)
        else:
            how = "single row, non-directional"
        metrics, anchors, scale, reference = plan_sheet(anim, cells, rows_count, grid.cell_w)
        need = required(metrics, anchors, cells, rows_count, scale)
        worst = [max(a, b) for a, b in zip(worst, need)]
        report.append((spec, rows_count, sheet, grid, cells, metrics, anchors, scale,
                       reference, need, how))
    return worst, report


def main():
    parser = argparse.ArgumentParser(description="Extract Wraith's animations.")
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    log("Wraith animation extraction")
    log("target body height {0:.0f} px (Ravager 116, Aegis 122)".format(TARGET_BODY_HEIGHT))
    log("")

    worst, report = choose_canvas()
    log("")
    log("WORST CASE from the feet anchor:  left {0:.0f}  right {1:.0f}  up {2:.0f}  down {3:.0f}"
        .format(*worst))

    have = (PIVOT[0], CANVAS[0] - PIVOT[0] - 1, PIVOT[1], CANVAS[1] - PIVOT[1] - 1)
    log("canvas {0}x{1} pivot {2} provides:   left {3} right {4} up {5} down {6}"
        .format(CANVAS[0], CANVAS[1], PIVOT, *have))
    if any(w > h for w, h in zip(worst, have)):
        fail("Wraith does not fit {0}x{1} at pivot {2} - needs left {3:.0f} right {4:.0f} "
             "up {5:.0f} down {6:.0f}".format(CANVAS[0], CANVAS[1], PIVOT, *worst))
    log("fits with margin: {0:.0f} / {1:.0f} / {2:.0f} / {3:.0f} px to spare"
        .format(*[h - w for w, h in zip(worst, have)]))

    attack_scales = [r[7] for r in report if r[0]["anim"] == "Attack"]
    projectile_scale = sum(attack_scales) / len(attack_scales)

    if args.measure:
        for (spec, rows_count, _s, _g, _c, _m, _a, scale, reference, need, how) in report:
            tag = "/".join(spec["rows"]) if spec["rows"] else "non-directional"
            log("")
            log("{0:<6s} {1:<16s} <- {2}".format(spec["anim"], tag, spec["file"][:8]))
            log("  identity: {0}".format(how))
            log("  body {0} px -> scale x{1:.4f}".format(reference, scale))
            log("  needs left {0:.0f} right {1:.0f} up {2:.0f} down {3:.0f}".format(*need))
        log("")
        log("projectile scale x{0:.4f} (mean of the attack sheets)".format(projectile_scale))
        return

    every = []
    for (spec, rows_count, sheet, grid, cells, metrics, anchors, scale, reference,
         need, how) in report:
        tag = "/".join(spec["rows"]) if spec["rows"] else "non-directional"
        log("")
        log("=" * 76)
        log("{0}  {1}  <-  {2}".format(spec["anim"], tag, spec["file"][:8]))
        log("  identity: {0}".format(how))
        log("  body {0} px -> scale x{1:.4f}".format(reference, scale))
        every.extend(write_frames(sheet, grid, cells, spec["anim"], spec["rows"],
                                  metrics, anchors, scale, rows_count))
        contact_sheet(spec["anim"], spec["rows"], rows_count)

    log("")
    check_idle()

    log("")
    log("=" * 76)
    log("PROJECTILE  <-  {0}   scale x{1:.4f}".format(PROJECTILE_FILE[:8], projectile_scale))
    write_projectile(projectile_scale)

    log("")
    log("=" * 76)
    log("{0} character frames + 12 arrow + 3 impact written".format(len(every) + 4))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED: " + ", ".join("{0} ({1}px)".format(r["name"], r["clipped"])
                                    for r in clipped))
    else:
        log("no character frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
