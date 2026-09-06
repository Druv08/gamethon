"""
Protect the King - 2D
Extracts Sentinel (mage / ranged magic guard) into finished Paper2D frames,
including his magic orb projectile and its impact burst.

    source : <Downloads>/gamethon pics/design 2d pics/sentinel pics/*.png (READ ONLY)
    output : ArtSource/Characters/Guards/Sentinel/Frames/<Anim>/<Dir>/...
             ArtSource/Characters/Guards/Sentinel/Frames/Orb/<Dir>/...
             ArtSource/Characters/Guards/Sentinel/Frames/Impact/...
             ArtSource/Characters/Guards/Sentinel/Sheets/Sentinel_<Anim>_8F.png

Run:  python Tools/ExtractSentinelAnimations.py --measure
      python Tools/ExtractSentinelAnimations.py

Uses the shared machinery in Tools/ptk_sheet.py, so every correction proven on
the five characters before him applies here unchanged.


WHICH SHEET IS WHICH
--------------------
Six sheets arrived as opaque GUIDs, in THREE different sizes. Each was
identified by looking at it and then confirmed by measurement:

  df0760d7  2x8  1536x1024  row0 face and gold-faced robe toward camera,
                            row1 the plain caped back    -> WALK   Down / Up
  22b9e675  2x8  1536x1024  the same walk in profile     -> WALK   Left / Right
  029d205c  2x8  1536x1024  staff raised, starburst at frame 5, front and back
                                                         -> ATTACK Down / Up
  3ddc2d80  2x8  1536x1024  the same cast in profile, orb visibly thrown
                                                         -> ATTACK Left / Right
  cc3594eb  1x8  1774x887   he sinks, kneels, falls, orbs scatter
                                                         -> DEATH (non-directional)
  f42973b0  4x2  1774x887   the orb forming, flying, and bursting on a wooden
                            test dummy                   -> ORB + IMPACT

sentinel.png is a 1448x1086 RGB turnaround with no alpha. It carries no
animation, but it IS the source of the four real idle frames - see
Tools/ExtractGuardIdle.py.


HOW DIRECTION WAS PROVEN, NOT ASSUMED
-------------------------------------
Down vs Up needed its own test again. Bright blue is useless for him - he is a
blue mage orbited by blue orbs in every view - and whole-frame GOLD barely
separates either (13.44% front against 11.34% back), because his cape is
gold-trimmed from behind too.

What does separate is gold across the TORSO: the front carries the robe's gold
facings and chest emblem where the back has plain cloth. Measured as the median
frame, the walk sheet reads 16.37% against 10.91% and the attack sheet 15.24%
against 8.62% - 1.5x and 1.8x, with the front winning 8/8 and 7/8 frames. That
is a smaller margin than Aegis's 9x, so it is used as a direction CHECK on a
mapping that was first read by eye, not as the sole evidence.

Left vs Right uses the outermost-blue-mass bias calibrated on the other guards,
where positive means LEFT: the walk profile sheet is unanimous (+0.083 with 8/8
frames voting left, -0.057 with 0/8) and the attack profile agrees (+0.153 6/8
against -0.191 1/8, less unanimous only because the thrown orb crosses his body).

verify_identity() re-runs both and REFUSES to write if the art contradicts the
mapping below.


THE PROJECTILE SHEET IS A DEMONSTRATION, NOT A SPRITE STRIP
-----------------------------------------------------------
Unlike Wraith's - whose arrow flies alone across most of its cells - every cell
of Sentinel's projectile sheet also contains the CASTER, and the last four
contain a wooden practice dummy as well. The orb cannot simply be cropped out.

It is separated by colour and then by position. The dummy is warm brown and
fails the blue test outright. The mage is harder: he is blue, and three blue
orbs float around his head in every frame. But those orbs are small and always
sit over him - measured, they never exceed 620 px and never start further right
than x=215 - while the projectile is a single 3900-7800 px mass that starts at
x=203 or beyond. So an island is the spell if it is either large or far to the
right, and the mage's own orbs satisfy neither.

CELLS USED: the orb is in flight in r0c2, r0c3 and r1c0, and bursting in r1c1,
r1c2 and r1c3. r0c0 and r0c1 are the caster gathering the spell in his hand -
they draw the mage, not the projectile, and are not extracted.
"""

import argparse
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\sentinel pics"
SENTINEL = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Sentinel")
FRAMES_DIR = os.path.join(SENTINEL, "Frames")
SHEETS_DIR = os.path.join(SENTINEL, "Sheets")

COLUMNS = 8
DIRECTIONS = ("Down", "Up", "Left", "Right")

SHEETS = [
    dict(anim="Walk",   rows=("Down", "Up"),
         file="df0760d7-4363-4a3b-8ab3-e5b70d3c0fa5.png"),
    dict(anim="Walk",   rows=("Left", "Right"),
         file="22b9e675-b7c1-4632-bb1d-c5b24b002340.png"),
    dict(anim="Attack", rows=("Down", "Up"),
         file="029d205c-ff0f-4eef-8a78-505b1b99139e.png"),
    dict(anim="Attack", rows=("Left", "Right"),
         file="3ddc2d80-9acd-47c6-b935-bca0ba519e08.png"),
]
DEATH_FILE = "cc3594eb-1476-407c-96fe-daa4a150f7b7.png"

PROJECTILE_FILE = "f42973b0-52bd-4d02-8f5b-84cf9648be49.png"
PROJECTILE_COLUMNS = 4
PROJECTILE_ROWS = 2
FLIGHT_CELLS = ((2, 0), (3, 0), (0, 1))     # (col, row)
IMPACT_CELLS = ((1, 1), (2, 1), (3, 1))

# An island in a projectile cell is the spell if it is either big or far right.
# Measured: the mage's own floating orbs top out at 620 px and never start
# further right than x=215; the orb and its burst run 3900-7800 px from x=203.
SPELL_MIN_AREA = 800
SPELL_MIN_X = 230

# 192x208, pivot (96, 179). The pivot is the project standard - his feet land
# on the actor origin exactly like every other guard, so nothing moves - but the
# canvas is 16 px TALLER at the bottom.
#
# He does technically fit 192x192: measured worst case is up 162 against the 179
# available and down 11 against 12. One pixel is not a margin. His death collapse
# is what reaches down, and Ravager and Swarm Node already take a 192x208 canvas
# for exactly that. Taking it for all five of his animations rather than death
# alone keeps one canvas per character, which is what stops a sprite changing
# size mid-fight.
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

# Feet-to-crown in the finished frames. Ravager 116, Aegis 122, Wraith 112,
# Reaver 114. Sentinel is given 118: a robed mage reads tall and stately, second
# only to the tank.
TARGET_BODY_HEIGHT = 116.0

# Square with a true centre pixel, so the four directions are exact 90-degree
# rotations of one drawing - lossless, no resampling, no mirroring.
ORB_CANVAS = 129
ORB_PIVOT = (ORB_CANVAS // 2, ORB_CANVAS // 2)
IMPACT_CANVAS = 129
IMPACT_PIVOT = (IMPACT_CANVAS // 2, IMPACT_CANVAS // 2)

SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128
MAX_GAP = 8


def is_energy(r, g, b):
    """
    Bright blue: the floating orbs, the staff gems, the cast glow and the spell.

    His robe is deep blue but dark, and his trim is gold, so neither reads as
    energy - geometry stays measured off the mage rather than off his orbs.
    """
    return b > 150 and b - r > 80


def is_spell(r, g, b):
    """Slightly looser than is_energy - the orb's outer glow is paler."""
    return b > 150 and b - r > 60


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def torso_gold(img):
    """
    Gold fraction across the middle of the body.

    Blue tells nothing about which way this character faces. Gold does, but only
    in the torso band: his cape is gold-trimmed from behind, so a whole-frame
    reading washes out, while the robe's facings and chest emblem are on the
    front alone.
    """
    w, h, px = img.width, img.height, img.px
    xs = []
    ys = []
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            if px[base + x * 4 + 3] >= SRC_ALPHA_THRESHOLD:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0.0
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    cx0, cx1 = x0 + int(bw * 0.30), x0 + int(bw * 0.70)
    cy0, cy1 = y0 + int(bh * 0.25), y0 + int(bh * 0.65)

    total = hot = 0
    for y in range(cy0, cy1 + 1):
        base = y * w * 4
        for x in range(cx0, cx1 + 1):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            total += 1
            if px[i] > 140 and px[i] - px[i + 2] > 40:
                hot += 1
    return (100.0 * hot / total) if total else 0.0


def median(values):
    return sorted(values)[len(values) // 2]


def facing_reach(img):
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
    rows = spec["rows"]
    if rows == ("Down", "Up"):
        front = median([torso_gold(cells[0][c]) for c in range(COLUMNS)])
        back = median([torso_gold(cells[1][c]) for c in range(COLUMNS)])
        if front <= back:
            fail("{0}: row0 reads {1:.2f}% torso gold and row1 {2:.2f}% - the front "
                 "must carry MORE (the robe's facings and chest emblem), so the "
                 "Down/Up mapping is wrong".format(spec["file"][:8], front, back))
        return "median torso gold: front {0:.2f}% vs back {1:.2f}%".format(front, back)

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
    body, full, w, h = ptk_sheet.build_masks(cell, SRC_ALPHA_THRESHOLD, is_energy)
    foot_threshold = max(2, int(round(0.030 * w)))
    head_threshold = max(2, int(round(0.022 * w)))

    def bands(mask):
        rows = [sum(mask[y * w:(y + 1) * w]) for y in range(h)]
        return ([y for y in range(h) if rows[y] >= foot_threshold],
                [y for y in range(h) if rows[y] >= head_threshold])

    solid, heads = bands(body)
    if not solid or not heads:
        body = full
        solid, heads = bands(body)
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
        xs = [x for y in range(h) for x in range(w) if body[y * w + x]]
    if not xs:
        return None
    return dict(feet=feet, top=top, body=feet - top + 1,
                centre=sum(xs) / float(len(xs)), bottom=feet)


def plan_sheet(anim, cells, rows_count, cell_w):
    def measure(reference):
        return [[body_metrics(cells[r][c], reference) for c in range(COLUMNS)]
                for r in range(rows_count)]

    raw = measure(cell_w * 1.05)
    if any(m is None for row in raw for m in row):
        fail(anim + ": a frame is empty")

    if anim == "Walk":
        heights = sorted(m["body"] for row in raw for m in row)
    else:
        heights = sorted(raw[r][c]["body"]
                         for r in range(rows_count) for c in (0, COLUMNS - 1))
    reference = heights[len(heights) // 2]

    metrics = measure(reference)
    scale = TARGET_BODY_HEIGHT / float(reference)
    anchors = [ptk_sheet.anchors_for_row(metrics[r], hold_still=(anim == "Walk"))
               for r in range(rows_count)]
    return metrics, anchors, scale, reference


def required(metrics, anchors, cells, rows_count, scale):
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
def load(spec_file, rows_count, columns=COLUMNS):
    path = os.path.join(SOURCE_DIR, spec_file)
    if not os.path.isfile(path):
        fail("source sheet missing: " + path)
    sheet = ptk_png.read_png(path)
    grid = ptk_sheet.Grid(sheet, columns, rows_count)
    cells = [[grid.cell(c, r) for c in range(columns)] for r in range(rows_count)]
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
            bounds = (ox, int(round((c + 1) * grid.cell_w)))
            frame = ptk_sheet.render_frame(
                sheet, ox, oy, grid.cell_w, grid.cell_h,
                ax, ay, scale, CANVAS, PIVOT, x_bounds=bounds)
            ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
            # drop_effect OFF: his floating orbs are detached from him by design
            # and are part of the character, not a fired projectile.
            dropped = ptk_sheet.clean_islands(
                frame, (PIVOT[0], PIVOT[1] - 40), is_energy,
                max_gap=MAX_GAP, drop_effect=False)
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
    name = "Sentinel_{0}{1}_8F.png".format(anim, ("_" + tag) if tag else "")
    ptk_png.write_png(os.path.join(SHEETS_DIR, name), out)
    log("  sheet  {0}  ({1}x{2})".format(name, out.width, out.height))


def check_idle():
    out_dir = os.path.join(FRAMES_DIR, "Idle")
    missing = [d for d in DIRECTIONS
               if not os.path.isfile(os.path.join(out_dir, "Idle_{0}.png".format(d)))]
    if missing:
        fail("real idle frames missing: {0}. Run: python Tools/ExtractGuardIdle.py "
             "Sentinel".format(", ".join(missing)))
    log("  idle   4 real standing frames present "
        "(from the turnaround - see Tools/ExtractGuardIdle.py)")


# ---------------------------------------------------------------------------
# Pipeline - projectile
# ---------------------------------------------------------------------------
def isolate_spell(cell):
    """
    Returns (image, area) holding only the spell - the mage and the practice
    dummy removed.

    See the module docstring: the dummy is brown and fails the colour test, and
    the mage's own floating orbs are excluded because they are neither large nor
    far to the right.
    """
    w, h, px = cell.width, cell.height, cell.px
    mask = bytearray(w * h)
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            i = base + x * 4
            if px[i + 3] >= SRC_ALPHA_THRESHOLD and is_spell(px[i], px[i + 1], px[i + 2]):
                mask[y * w + x] = 1

    seen = bytearray(w * h)
    out = ptk_png.Image(w, h)
    kept = 0
    for start in range(w * h):
        if not mask[start] or seen[start]:
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
                    if mask[j] and not seen[j]:
                        seen[j] = 1
                        queue.append(j)
        x0 = min(k % w for k in island)
        if len(island) < SPELL_MIN_AREA and x0 < SPELL_MIN_X:
            continue
        for k in island:
            out.px[k * 4:k * 4 + 4] = px[k * 4:k * 4 + 4]
        kept += len(island)
    return out, kept


def rotate90(img, turns):
    """Exact 90-degree CCW rotation - an index permutation, so lossless."""
    turns %= 4
    for _ in range(turns):
        w, h = img.width, img.height
        out = ptk_png.Image(h, w)
        for y in range(h):
            for x in range(w):
                out.set(y, w - 1 - x, img.get(x, y))
        img = out
    return img


def centroid(img):
    w, h, px = img.width, img.height, img.px
    sx = sy = n = 0
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            if px[base + x * 4 + 3] >= SRC_ALPHA_THRESHOLD:
                sx += x
                sy += y
                n += 1
    return (sx / float(n), sy / float(n), n) if n else None


def write_projectile(scale):
    sheet_path = os.path.join(SOURCE_DIR, PROJECTILE_FILE)
    if not os.path.isfile(sheet_path):
        fail("projectile sheet missing: " + sheet_path)
    sheet = ptk_png.read_png(sheet_path)
    grid = ptk_sheet.Grid(sheet, PROJECTILE_COLUMNS, PROJECTILE_ROWS)

    # CCW turns taking a right-travelling orb to each screen direction.
    TURNS = dict(Right=0, Up=1, Left=2, Down=3)

    orb_dir = os.path.join(FRAMES_DIR, "Orb")
    for direction in DIRECTIONS:
        d = os.path.join(orb_dir, direction)
        if not os.path.isdir(d):
            os.makedirs(d)

    for n, (c, r) in enumerate(FLIGHT_CELLS):
        cell = grid.cell(c, r)
        spell, area = isolate_spell(cell)
        if area < SPELL_MIN_AREA:
            fail("projectile cell r{0}c{1}: no spell found ({2} px)".format(r, c, area))
        mid = centroid(spell)
        frame = ptk_sheet.render_frame(
            spell, 0, 0, spell.width, spell.height,
            mid[0], mid[1], scale, (ORB_CANVAS, ORB_CANVAS), ORB_PIVOT,
            fence_fraction=0.5)
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        for direction in DIRECTIONS:
            turned = rotate90(frame, TURNS[direction])
            ptk_png.write_png(
                os.path.join(orb_dir, direction, "Orb_{0}_{1:02d}.png".format(direction, n + 1)),
                turned)
        log("    Orb_<4 dirs>_{0:02d}.png   from cell r{1}c{2}   spell {3} px"
            .format(n + 1, r, c, area))

    impact_dir = os.path.join(FRAMES_DIR, "Impact")
    if not os.path.isdir(impact_dir):
        os.makedirs(impact_dir)
    for n, (c, r) in enumerate(IMPACT_CELLS):
        cell = grid.cell(c, r)
        spell, area = isolate_spell(cell)
        mid = centroid(spell)
        if mid is None:
            fail("projectile cell r{0}c{1}: no burst found".format(r, c))
        frame = ptk_sheet.render_frame(
            spell, 0, 0, spell.width, spell.height,
            mid[0], mid[1], scale, (IMPACT_CANVAS, IMPACT_CANVAS), IMPACT_PIVOT,
            fence_fraction=0.5)
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        ptk_png.write_png(
            os.path.join(impact_dir, "Impact_{0:02d}.png".format(n + 1)), frame)
        log("    Impact_{0:02d}.png   from cell r{1}c{2}   burst {3} px"
            .format(n + 1, r, c, area))

    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    out = ptk_png.Image(ORB_CANVAS * 3, ORB_CANVAS * 5)
    for n in range(3):
        for row, direction in enumerate(DIRECTIONS):
            out.paste(ptk_png.read_png(os.path.join(
                orb_dir, direction, "Orb_{0}_{1:02d}.png".format(direction, n + 1))),
                n * ORB_CANVAS, row * ORB_CANVAS)
        out.paste(ptk_png.read_png(os.path.join(
            impact_dir, "Impact_{0:02d}.png".format(n + 1))), n * ORB_CANVAS, 4 * ORB_CANVAS)
    ptk_png.write_png(os.path.join(SHEETS_DIR, "Sentinel_Projectile.png"), out)
    log("  sheet  Sentinel_Projectile.png  ({0}x{1})  rows: Down Up Left Right Impact"
        .format(out.width, out.height))


# ---------------------------------------------------------------------------
def choose_canvas():
    worst = [0.0, 0.0, 0.0, 0.0]
    report = []
    for spec in SHEETS + [dict(anim="Death", rows=None, file=DEATH_FILE)]:
        rows_count = 1 if spec["rows"] is None else 2
        sheet, grid, cells = load(spec["file"], rows_count)
        anim = spec["anim"]
        how = verify_identity(spec, cells) if spec["rows"] else "single row, non-directional"
        metrics, anchors, scale, reference = plan_sheet(anim, cells, rows_count, grid.cell_w)
        need = required(metrics, anchors, cells, rows_count, scale)
        worst = [max(a, b) for a, b in zip(worst, need)]
        report.append((spec, rows_count, sheet, grid, cells, metrics, anchors, scale,
                       reference, need, how))
    return worst, report


def main():
    parser = argparse.ArgumentParser(description="Extract Sentinel's animations.")
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    log("Sentinel animation extraction")
    log("target body height {0:.0f} px (Ravager 116, Aegis 122, Wraith 112, Reaver 114)"
        .format(TARGET_BODY_HEIGHT))

    worst, report = choose_canvas()
    log("")
    log("WORST CASE from the feet anchor:  left {0:.0f}  right {1:.0f}  up {2:.0f}  down {3:.0f}"
        .format(*worst))
    have = (PIVOT[0], CANVAS[0] - PIVOT[0] - 1, PIVOT[1], CANVAS[1] - PIVOT[1] - 1)
    log("canvas {0}x{1} pivot {2} provides:   left {3} right {4} up {5} down {6}"
        .format(CANVAS[0], CANVAS[1], PIVOT, *have))
    if any(w > h for w, h in zip(worst, have)):
        fail("Sentinel does not fit {0}x{1} at pivot {2} - needs left {3:.0f} right {4:.0f} "
             "up {5:.0f} down {6:.0f}".format(CANVAS[0], CANVAS[1], PIVOT, *worst))
    log("fits with margin: {0:.0f} / {1:.0f} / {2:.0f} / {3:.0f} px to spare"
        .format(*[h - w for w, h in zip(worst, have)]))

    attack_scales = [r[7] for r in report if r[0]["anim"] == "Attack"]
    projectile_scale = sum(attack_scales) / len(attack_scales)

    if args.measure:
        for (spec, rows_count, _s, grid, _c, _m, _a, scale, reference, need, how) in report:
            tag = "/".join(spec["rows"]) if spec["rows"] else "non-directional"
            log("")
            log("{0:<6s} {1:<16s} <- {2}  (cell {3:.0f}x{4})".format(
                spec["anim"], tag, spec["file"][:8], grid.cell_w, grid.cell_h))
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
    log("{0} character frames + 12 orb + 3 impact written".format(len(every) + 4))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED: " + ", ".join("{0} ({1}px)".format(r["name"], r["clipped"])
                                    for r in clipped))
    else:
        log("no character frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
