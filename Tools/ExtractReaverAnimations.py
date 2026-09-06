"""
Protect the King - 2D
Extracts Reaver (fast melee / assassin guard) into finished Paper2D frames.

    source : <Downloads>/gamethon pics/design 2d pics/reaver pics/*.png  (READ ONLY)
    output : ArtSource/Characters/Guards/Reaver/Frames/<Anim>/<Dir>/...
             ArtSource/Characters/Guards/Reaver/Sheets/Reaver_<Anim>_8F.png

Run:  python Tools/ExtractReaverAnimations.py --measure
      python Tools/ExtractReaverAnimations.py

Uses the shared machinery in Tools/ptk_sheet.py, so every correction proven on
Ravager, Swarm Node, the King, Aegis and Wraith applies here unchanged.


WHICH SHEET IS WHICH
--------------------
Five sheets arrived as opaque GUIDs. Each was identified by looking at it and
then confirmed by measurement - never by filename:

  fae814bf  2x8  row0 the glowing V-mask and chest gems toward camera,
                 row1 the smooth hood and cape   -> WALK   Down / Up
  8037beb5  2x8  the same stride in profile      -> WALK   Left / Right
  8e6bfae8  2x8  twin-blade slash, front and back, with crescent arcs
                                                 -> ATTACK Down / Up
  6ef79b36  2x8  the same slash in profile       -> ATTACK Left / Right
  c97b8234  1x8  he staggers, sinks, falls and dissolves into blue
                                                 -> DEATH (non-directional)

reaver.png is a 1448x1086 RGB turnaround (front / back / two profiles) with no
alpha. It carries no animation, but it IS the source of the four real idle
frames - see Tools/ExtractGuardIdle.py.

NOTE the attack front/back sheet is 1672x941, NOT the 2172x724 the others use.
Nothing here assumes a sheet size: the grid is derived per sheet and the scale
is normalised per sheet, which is exactly why a differently sized delivery drops
in without special handling.


HOW DIRECTION WAS PROVEN, NOT ASSUMED
-------------------------------------
Down vs Up needed a NEW test for Reaver. The whole-frame bright-blue rule that
separates Aegis 9x and Wraith 7x barely moves for him - 6.28% front against
5.71% back - because he carries a glowing blade in each hand in every view, and
the blades swamp the measurement.

What actually differs is his HEAD: the front view has a lit V-mask inside the
hood and gems across the chest, the back view a plain hood and cape. Measuring
bright blue only inside the head/upper-torso box separates them 12.7x on the
walk sheet, and every one of the 8 frames agrees.

The attack sheet needs one more guard. Its crescent arcs sweep straight through
that box on two frames of each row, spiking the reading to 25-30%, so the MEDIAN
frame is used rather than the mean - it ignores the two arc frames and reads the
pose underneath, 1.8% front against 0.3% back.

Left vs Right uses the outermost-blue-mass bias already calibrated on the other
guards, where positive means LEFT. His blades sweep forward on the side he
faces, so the same metric applies unchanged: the walk profile sheet reads +0.112
with 8/8 frames voting left and -0.110 with 0/8, and the attack profile sheet
agrees on the mean (+0.103 / -0.087, less unanimous per frame only because the
arcs swing across his body).

verify_identity() re-runs every one of these and REFUSES to write if the art
contradicts the mapping below.


HIS SLASH ARCS ARE KEPT
-----------------------
Unlike Wraith - whose released arrow is deleted because the game spawns a real
projectile in its place - Reaver's crescents are the attack itself. There is no
actor to hand them to, so detached bright art is KEPT here and only distance
decides what is spill. clean_islands is therefore called with drop_effect off.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\reaver pics"
REAVER = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Reaver")
FRAMES_DIR = os.path.join(REAVER, "Frames")
SHEETS_DIR = os.path.join(REAVER, "Sheets")

COLUMNS = 8
DIRECTIONS = ("Down", "Up", "Left", "Right")

SHEETS = [
    dict(anim="Walk",   rows=("Down", "Up"),
         file="fae814bf-b8fa-4d65-a6ed-51ca955e9c1d.png"),
    dict(anim="Walk",   rows=("Left", "Right"),
         file="8037beb5-aaff-4ada-be80-1cf3d4595220.png"),
    dict(anim="Attack", rows=("Down", "Up"),
         file="8e6bfae8-9b66-4446-bc18-f01520680f95.png"),
    dict(anim="Attack", rows=("Left", "Right"),
         file="6ef79b36-b969-49ba-a030-59369b87c441.png"),
]
DEATH_FILE = "c97b8234-c664-4e63-960a-86c4c2cb82bf.png"

# 192x192, pivot (96, 179) - the project's standard canvas, shared with Ravager,
# Swarm Node, Aegis and Wraith. main() re-measures this every run and refuses to
# write if Reaver ever stops fitting it.
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

# Hood-to-feet of the WALK pose in the finished frames, and the one number that
# sets this character's size on screen. Every guard now uses the same 116 so
# that switching between them cannot change how big the player looks; build
# differences (Aegis is broader, Reaver leaner) live in the art, not the scale.
#
# Only the Walk sheets are scaled by this. Every other sheet is matched to Walk
# by HEAD WIDTH instead - see plan_sheet.
TARGET_BODY_HEIGHT = 116.0

SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128

# Anything more than this from Reaver is the neighbouring frame, not his own
# gear. The same 8 px that worked for Wraith's bow.
MAX_GAP = 8


def is_energy(r, g, b):
    """
    Bright blue: the twin blades, their crescent arcs, the mask and chest gems.

    His cloak and armour are dark navy and top out well under the b>150 gate, so
    none of his body qualifies and geometry stays measured off the man rather
    than off a blade held out at arm's length.
    """
    return b > 150 and b - r > 80


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


# ---------------------------------------------------------------------------
# Identity - prove each sheet is what the table above claims
# ---------------------------------------------------------------------------
def head_blue_fraction(img):
    """
    Bright blue inside the head / upper-torso box only.

    Reaver's whole-frame blue is dominated by the two blades he carries in every
    view, which is why the usual front/back test fails for him. His lit mask and
    chest gems sit in the middle of the upper body, where the blades - held out
    to the sides and low - are not.
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
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    cx0, cx1 = x0 + int(bw * 0.28), x0 + int(bw * 0.72)
    cy0, cy1 = y0, y0 + int(bh * 0.45)

    total = hot = 0
    for y in range(cy0, cy1 + 1):
        base = y * w * 4
        for x in range(cx0, cx1 + 1):
            i = base + x * 4
            if px[i + 3] < SRC_ALPHA_THRESHOLD:
                continue
            total += 1
            if px[i + 2] > 190 and px[i + 2] - px[i] > 90:
                hot += 1
    return (100.0 * hot / total) if total else 0.0


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def facing_reach(img):
    """
    (left, right) - how far the outermost blue mass reaches past the body centre,
    as a fraction of silhouette width. His blades lead on the side he faces.
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
        # Median, not mean: the attack's crescent arcs cross the head box on two
        # frames of each row and would otherwise decide the answer.
        front = median([head_blue_fraction(cells[0][c]) for c in range(COLUMNS)])
        back = median([head_blue_fraction(cells[1][c]) for c in range(COLUMNS)])
        if front <= back:
            fail("{0}: row0 reads {1:.2f}% head blue and row1 {2:.2f}% - the front "
                 "view must carry MORE (the lit mask and chest gems face the "
                 "camera), so the Down/Up mapping is wrong"
                 .format(spec["file"][:8], front, back))
        return "median head blue: front {0:.2f}% vs back {1:.2f}%".format(front, back)

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

    The hips band is located from `reference_height` rather than from this
    frame's own height, so a blade raised overhead cannot slide the band onto
    the legs and make the centre incomparable between frames of one swing.
    """
    body, full, w, h = ptk_sheet.build_masks(cell, SRC_ALPHA_THRESHOLD, is_energy)
    foot_threshold = max(2, int(round(0.030 * w)))
    head_threshold = max(2, int(round(0.022 * w)))

    def bands(mask):
        rows = [sum(mask[y * w:(y + 1) * w]) for y in range(h)]
        return ([y for y in range(h) if rows[y] >= foot_threshold],
                [y for y in range(h) if rows[y] >= head_threshold])

    solid, heads = bands(body)
    if not solid or not heads:
        # His last death frame is pure blue dissolve - there is no body left to
        # measure, only effect. Fall back to the full silhouette rather than
        # failing: a frame made entirely of effect still has a position, and
        # refusing to place it would stop the whole death sequence.
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
        # A collapsed corpse is far shorter than the reference height, so the
        # hip band can land entirely above it - his death sheet holds a 724 px
        # cell around a body that ends up barely 50 px tall. Fall back to the
        # whole silhouette's centroid, which is the right answer for a heap.
        xs = [x for y in range(h) for x in range(w) if body[y * w + x]]
    if not xs:
        return None
    return dict(feet=feet, top=top, body=feet - top + 1,
                centre=sum(xs) / float(len(xs)), bottom=feet)


# Finished-frame head width per facing pair, set by the Walk sheets and read by
# every other sheet. See plan_sheet.
_TARGET_HEAD = {}


def facing_pair(rows):
    """'DU' for the front/back sheet, 'LR' for the profile one."""
    if not rows:
        return None
    return "DU" if "Down" in rows else "LR"


def plan_sheet(anim, rows, cells, rows_count, cell_w):
    """
    Per-sheet scale, per-frame metrics and the anchor scheme.

    WALK SETS THE SIZE; EVERY OTHER SHEET IS MATCHED TO IT BY HEAD WIDTH.
    --------------------------------------------------------------------
    Each of Reaver's sheets is drawn at its own scale, so every one has to be
    normalised. Doing that on hood-to-feet HEIGHT is what produced the bug this
    replaces: his attack ready-pose stands straighter than his walk pose, so
    equalising heights made the whole attack render 8.6% smaller than the stride
    it interrupts - he shrank the moment he swung and sprang back when he
    finished, which is exactly what was reported.

    A head is the same size whatever the body is doing. Matching heads matches
    size and leaves the pose alone, so he can still crouch, lean and lunge
    through a swing without changing scale.

    The two facing pairs are kept apart because a hood seen in profile is not
    the same width as one seen head-on: front/back sheets are matched to the
    front/back walk, profile sheets to the profile walk.
    """
    def measure(reference):
        return [[body_metrics(cells[r][c], reference) for c in range(COLUMNS)]
                for r in range(rows_count)]

    raw = measure(cell_w * 1.05)
    if any(m is None for row in raw for m in row):
        fail(anim + ": a frame is empty")

    if anim == "Walk":
        heights = sorted(m["body"] for row in raw for m in row)
    else:
        # Frames 1 and 8 are ready / return-to-ready: the only poses in the
        # swing whose height is not inflated by a raised blade.
        heights = sorted(raw[r][c]["body"]
                         for r in range(rows_count) for c in (0, COLUMNS - 1))
    reference = heights[len(heights) // 2]

    metrics = measure(reference)

    pair = facing_pair(rows)
    source_head = ptk_sheet.sheet_head_width(cells, SRC_ALPHA_THRESHOLD, is_energy)

    if anim == "Walk" or pair is None or pair not in _TARGET_HEAD or not source_head:
        # Walk defines the character's size, and so does anything with no head
        # left to measure - the death sheet ends as a heap.
        scale = TARGET_BODY_HEIGHT / float(reference)
        basis = "body {0} px".format(reference)
    else:
        scale = _TARGET_HEAD[pair] / float(source_head)
        basis = "head {0:.0f} px -> {1:.1f}".format(source_head, _TARGET_HEAD[pair])

    if anim == "Walk" and pair and source_head:
        _TARGET_HEAD[pair] = source_head * scale

    # PER-FRAME correction, for the attack sheets only.
    #
    # One scale for the whole sheet is only right if the artist drew every cell
    # at one size, and in his attack sheets they did not: the front/back sheet
    # runs from 226 to 257 px of body between cells, so frames 2, 5, 6 and 7
    # came out visibly smaller than the ready pose either side of them. He
    # shrank mid-swing and sprang back.
    #
    # Each frame is therefore scaled by ITS OWN head width. A head does not
    # crouch, so this normalises size without touching the pose - he still
    # hunches, leans and lunges exactly as drawn.
    #
    # Clamped to +/-12% of the sheet scale because a head measurement can be
    # wrong: in a couple of frames a lit blade sweeps across the hood and merges
    # with it, which reads as a far wider head. The clamp means the worst a bad
    # reading can do is leave that frame where it already was.
    scales = [[scale for _c in range(COLUMNS)] for _r in range(rows_count)]
    if anim == "Attack" and pair and pair in _TARGET_HEAD:
        lo, hi = scale * 0.88, scale * 1.12
        for r in range(rows_count):
            for c in range(COLUMNS):
                own = ptk_sheet.head_width(cells[r][c], SRC_ALPHA_THRESHOLD, is_energy)
                if not own:
                    continue
                scales[r][c] = min(hi, max(lo, _TARGET_HEAD[pair] / float(own)))

    anchors = []
    for r in range(rows_count):
        # Walk plays in place, so every frame is pinned and the drift goes.
        # An attack lunges and returns and a death collapses forward, so those
        # rows get ONE anchor and the motion survives.
        anchors.append(ptk_sheet.anchors_for_row(metrics[r], hold_still=(anim == "Walk")))
    return metrics, anchors, scales, basis


def required(metrics, anchors, cells, rows_count, scales):
    """Worst-case reach from the anchor, in finished-frame pixels."""
    need = [0.0, 0.0, 0.0, 0.0]
    for r in range(rows_count):
        for c in range(COLUMNS):
            _body, full, w, h = ptk_sheet.build_masks(
                cells[r][c], SRC_ALPHA_THRESHOLD, is_energy)
            x0, x1, y0, y1 = ptk_sheet.mask_bounds(full, w, h)
            ax, ay = anchors[r][c]
            s = scales[r][c]
            need[0] = max(need[0], (ax - x0) * s)
            need[1] = max(need[1], (x1 - ax) * s)
            need[2] = max(need[2], (ay - y0) * s)
            need[3] = max(need[3], (y1 - ay) * s)
    return need


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def load(spec_file, rows_count):
    path = os.path.join(SOURCE_DIR, spec_file)
    if not os.path.isfile(path):
        fail("source sheet missing: " + path)
    sheet = ptk_png.read_png(path)
    # Rows are taken from where the content actually is, not from
    # sheet.height / rows. His front/back attack sheet is 1672x941 with figures
    # at 154-470 and 519-845: an even split at 470 leaves the last pixel row of
    # the first figure inside the second cell, and that one row made the second
    # cell measure 376 px of "body" instead of 250 - scaling the whole sheet,
    # and only that sheet, to two thirds of his proper size.
    bounds = ptk_sheet.find_row_bands(sheet, rows_count, SRC_ALPHA_THRESHOLD)
    grid = ptk_sheet.Grid(sheet, COLUMNS, rows_count, row_bounds=bounds)
    cells = [[grid.cell(c, r) for c in range(COLUMNS)] for r in range(rows_count)]
    return sheet, grid, cells


def write_frames(sheet, grid, cells, anim, rows, metrics, anchors, scales, rows_count):
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
            # Clamp sampling to the cell so a neighbour's blade can never be
            # sampled in, then let distance alone decide what is spill.
            bounds = (ox, int(round((c + 1) * grid.cell_w)))
            frame = ptk_sheet.render_frame(
                sheet, ox, oy, grid.cell_w, grid.height_of(r),
                ax, ay, scales[r][c], CANVAS, PIVOT, x_bounds=bounds)
            ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
            # drop_effect OFF: his crescents ARE the attack and must survive.
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
    name = "Reaver_{0}{1}_8F.png".format(anim, ("_" + tag) if tag else "")
    ptk_png.write_png(os.path.join(SHEETS_DIR, name), out)
    log("  sheet  {0}  ({1}x{2})".format(name, out.width, out.height))


def check_idle():
    """
    Idle is NOT produced here.

    The real standing poses come from the character turnaround sheet, extracted
    by Tools/ExtractGuardIdle.py. This only checks they are present, so that
    re-running this script can never quietly leave him without one.
    """
    out_dir = os.path.join(FRAMES_DIR, "Idle")
    missing = [d for d in DIRECTIONS
               if not os.path.isfile(os.path.join(out_dir, "Idle_{0}.png".format(d)))]
    if missing:
        fail("real idle frames missing: {0}. Run: python Tools/ExtractGuardIdle.py Reaver"
             .format(", ".join(missing)))
    log("  idle   4 real standing frames present "
        "(from the turnaround - see Tools/ExtractGuardIdle.py)")


def choose_canvas():
    """Measure every sheet first, then check one canvas holds them all."""
    worst = [0.0, 0.0, 0.0, 0.0]
    report = []
    for spec in SHEETS + [dict(anim="Death", rows=None, file=DEATH_FILE)]:
        rows_count = 1 if spec["rows"] is None else 2
        sheet, grid, cells = load(spec["file"], rows_count)
        anim = spec["anim"]
        how = verify_identity(spec, cells) if spec["rows"] else "single row, non-directional"
        metrics, anchors, scales, basis = plan_sheet(
            anim, spec["rows"], cells, rows_count, grid.cell_w)
        need = required(metrics, anchors, cells, rows_count, scales)
        worst = [max(a, b) for a, b in zip(worst, need)]
        report.append((spec, rows_count, sheet, grid, cells, metrics, anchors, scales,
                       basis, need, how))
    return worst, report


def main():
    parser = argparse.ArgumentParser(description="Extract Reaver's animations.")
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    log("Reaver animation extraction")
    log("walk body height {0:.0f} px; every other sheet matched to it by head width"
        .format(TARGET_BODY_HEIGHT))
    log("")

    worst, report = choose_canvas()
    log("")
    log("WORST CASE from the feet anchor:  left {0:.0f}  right {1:.0f}  up {2:.0f}  down {3:.0f}"
        .format(*worst))

    have = (PIVOT[0], CANVAS[0] - PIVOT[0] - 1, PIVOT[1], CANVAS[1] - PIVOT[1] - 1)
    log("canvas {0}x{1} pivot {2} provides:   left {3} right {4} up {5} down {6}"
        .format(CANVAS[0], CANVAS[1], PIVOT, *have))
    if any(w > h for w, h in zip(worst, have)):
        fail("Reaver does not fit {0}x{1} at pivot {2} - needs left {3:.0f} right {4:.0f} "
             "up {5:.0f} down {6:.0f}".format(CANVAS[0], CANVAS[1], PIVOT, *worst))
    log("fits with margin: {0:.0f} / {1:.0f} / {2:.0f} / {3:.0f} px to spare"
        .format(*[h - w for w, h in zip(worst, have)]))

    if args.measure:
        for (spec, rows_count, _s, grid, _c, _m, _a, scales, basis, need, how) in report:
            tag = "/".join(spec["rows"]) if spec["rows"] else "non-directional"
            log("")
            log("{0:<6s} {1:<16s} <- {2}  (cell {3:.0f}x{4}, rows {5})".format(
                spec["anim"], tag, spec["file"][:8], grid.cell_w,
                grid.height_of(0), grid.row_bounds or "even split"))
            log("  identity: {0}".format(how))
            flat = [v for row in scales for v in row]
            log("  scale from {0} -> x{1:.4f}..{2:.4f}".format(basis, min(flat), max(flat)))
            log("  needs left {0:.0f} right {1:.0f} up {2:.0f} down {3:.0f}".format(*need))
        return

    every = []
    for (spec, rows_count, sheet, grid, cells, metrics, anchors, scales, basis,
         need, how) in report:
        tag = "/".join(spec["rows"]) if spec["rows"] else "non-directional"
        log("")
        log("=" * 76)
        log("{0}  {1}  <-  {2}".format(spec["anim"], tag, spec["file"][:8]))
        log("  identity: {0}".format(how))
        flat = [v for row in scales for v in row]
        log("  scale from {0} -> x{1:.4f}..{2:.4f}".format(basis, min(flat), max(flat)))
        every.extend(write_frames(sheet, grid, cells, spec["anim"], spec["rows"],
                                  metrics, anchors, scales, rows_count))
        contact_sheet(spec["anim"], spec["rows"], rows_count)

    log("")
    check_idle()

    log("")
    log("=" * 76)
    log("{0} frames written ({1} walk/attack/death + 4 idle)".format(
        len(every) + 4, len(every)))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED: " + ", ".join("{0} ({1}px)".format(r["name"], r["clipped"])
                                    for r in clipped))
    else:
        log("no frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
