"""
Protect the King - 2D
Extracts Aegis (tank / defender guard) into finished Paper2D frames.

    source : <Downloads>/gamethon pics/design 2d pics/aegis pics/*.png  (READ ONLY)
    output : ArtSource/Characters/Guards/Aegis/Frames/<Anim>/<Dir>/...
             ArtSource/Characters/Guards/Aegis/Sheets/Aegis_<Anim>_8F.png

Run:  python Tools/ExtractAegisAnimations.py --measure
      python Tools/ExtractAegisAnimations.py

Uses the shared machinery in Tools/ptk_sheet.py, so the corrections proven on
Ravager, Swarm Node and the King apply here unchanged.


WHICH SHEET IS WHICH
--------------------
Five sheets arrived as opaque GUIDs. Each was identified by looking at it and
then confirmed by measurement - never by filename:

  86f284fd  2x8  walk, row0 face and glowing shield emblem toward camera,
                 row1 the caped back        -> WALK  Down / Up
  1fb633fd  2x8  walk in profile            -> WALK  Left / Right
  dfbf3b5b  2x8  mace raised, blue arc, burst at frame 5, front and back
                                            -> ATTACK Down / Up
  00200303  2x8  the same swing in profile  -> ATTACK Left / Right
  94c7f0cd  1x8  he sags, drops, and ends face-down under his shield
                                            -> DEATH (non-directional)

aegis.png is a 1448x1086 RGB turnaround (front / back / two profiles) with no
alpha. It carries no animation, but it IS the source of the four real idle
frames - see Tools/ExtractGuardIdle.py.


HOW DIRECTION WAS PROVEN, NOT ASSUMED
-------------------------------------
Down vs Up: the front view shows the shield's glowing emblem, the back view
shows only the cape. Measured as bright-blue coverage, row0 carries 4.98% and
row1 0.55% on the walk sheet (7.10% vs 2.33% on the attack sheet) - a 9x and 3x
separation in the same direction on both sheets.

Left vs Right: calibrated against Ravager's already-verified frames, using how
far the outermost blue mass (the mace head) reaches past the body centre.
Ravager Left reads +0.451 left / -0.071 right and Right the mirror of that.
Aegis walk row0 reads +0.288 / +0.121 with all 8 frames voting left, and row1
+0.089 / +0.299 with all 8 voting right. The attack sheet agrees on the mean.

The extractor re-runs both checks and REFUSES to write if the art contradicts
the mapping below.

THE IDLE FRAMES COME FROM THE TURNAROUND, NOT FROM WALK
------------------------------------------------------
No idle sheet shipped with the animation sheets, so Idle_<Dir>.png used to be a
copy of Walk_<Dir>_01. That is still a walking frame, and standing still read as
a man frozen mid-stride.

The real standing poses were in the turnaround sheet all along - the same source
Ravager's idle has always used. They are extracted by Tools/ExtractGuardIdle.py;
this script only checks they are present, so re-running it can never put the
walk frame back.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\aegis pics"
AEGIS = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Aegis")
FRAMES_DIR = os.path.join(AEGIS, "Frames")
SHEETS_DIR = os.path.join(AEGIS, "Sheets")

COLUMNS = 8
DIRECTIONS = ("Down", "Up", "Left", "Right")

SHEETS = [
    dict(anim="Walk",   rows=("Down", "Up"),
         file="86f284fd-b1ba-4d82-9095-21a138db1041.png"),
    dict(anim="Walk",   rows=("Left", "Right"),
         file="1fb633fd-3ad6-4aaf-b4e9-f28ab146200e.png"),
    dict(anim="Attack", rows=("Down", "Up"),
         file="dfbf3b5b-fcd8-49bc-b08d-fd0900dc7956.png"),
    dict(anim="Attack", rows=("Left", "Right"),
         file="00200303-9b67-45aa-8211-3f895f69fa5f.png"),
]
DEATH_FILE = "94c7f0cd-3d13-4b57-aeee-b53c6e97abba.png"

# The shield-defence skill. Four sheets, ONE DIRECTION EACH, laid out 4 columns
# by 2 rows - so the eight frames read row-major, top row then bottom, not as
# two directions. Every sheet peaks in glow at frames 5-6 and settles back to
# its opening brightness by 7-8, which is what a raise / flare / settle reads
# like and confirms the ordering.
#
# Identified by content, never by filename, using the same two tests his walk
# and attack sheets pass:
#   799d40b6  5.5% baseline blue, bias ~0     -> DOWN  (emblem faces the camera)
#   727902b1  0.6% baseline blue              -> UP    (cape only, 9x less blue)
#   8e7cc00c  bias +0.29                      -> LEFT
#   9bd841db  bias -0.35                      -> RIGHT
DEFEND_COLUMNS = 4
DEFEND_ROWS = 2
DEFEND_FRAME_COUNT = DEFEND_COLUMNS * DEFEND_ROWS
DEFEND_SHEETS = [
    ("Down",  "799d40b6-98bc-4e11-8009-9b5bfe657954.png"),
    ("Up",    "727902b1-8bce-4981-8bc7-c9f2e1ae5a1a.png"),
    ("Left",  "8e7cc00c-d2c7-488a-92d2-c0551a824b15.png"),
    ("Right", "9bd841db-5a16-4201-9356-81c67df28459.png"),
]

# 192x192, pivot (96, 179) - the project's standard canvas, shared with
# Ravager, Swarm Node and Wraith.
#
# This is not an assumption: measured worst case from the feet anchor across
# all five animation sheets is left 70, right 64, up 147, down 7, against the
# 96 / 95 / 179 / 12 this canvas provides. The raised mace is the tallest thing
# he does and it clears by 32 px, so Aegis needs no more room than Ravager
# despite being the bulkier man - his weight is in width, not height. main()
# re-checks this every run and refuses to write if it ever stops being true,
# and extract_defend() fails outright if a braced shield touches the edge.
CANVAS = (192, 192)
PIVOT = (96, 179)

# Helmet-to-feet in the finished frames. Ravager stands 116; Aegis is given 122
# because he is the heavy tank and should read as the bigger man on the field.
# He is far bulkier than Ravager at the same height, which is where the weight
# actually comes from - height alone would just look stretched.
TARGET_BODY_HEIGHT = 122.0

SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128


# Bright blue: shield emblem, mace head, swing arcs, visor. Excluded from the
# body mask so that geometry is measured off armour and a wide glow can never
# drag the ground anchor. His armour is dark steel, so nothing of his body
# qualifies.
def is_energy(r, g, b):
    return b > 150 and b - r > 80


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

    The mace head is the one strongly asymmetric feature and always sits on the
    side he faces. The shield is blue too but lies across his body, so the
    outermost fifth of the blue mass is used rather than its centroid.
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
                 "view must carry MORE (the shield emblem faces the camera), so the "
                 "Down/Up mapping is wrong".format(spec["file"][:8], front, back))
        return "front {0:.2f}% vs back {1:.2f}% bright blue".format(front, back)

    left = [facing_reach(cells[0][c]) for c in range(COLUMNS)]
    right = [facing_reach(cells[1][c]) for c in range(COLUMNS)]
    lm = sum(v[0] - v[1] for v in left if v) / COLUMNS
    rm = sum(v[0] - v[1] for v in right if v) / COLUMNS
    if not (lm > 0.0 > rm):
        fail("{0}: row0 bias {1:+.3f} and row1 {2:+.3f} - row0 must lean LEFT "
             "(positive) and row1 RIGHT (negative), so the Left/Right mapping is "
             "wrong".format(spec["file"][:8], lm, rm))
    return "left bias {0:+.3f} vs right bias {1:+.3f}".format(lm, rm)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def body_metrics(cell, reference_height):
    """
    Ground contact, silhouette top and hip centre, measured off armour only.

    The hips band is located from `reference_height`, not from this frame's own
    height: with the mace raised overhead the frame's own top IS the mace, which
    would slide the band down onto the legs and make the centre incomparable
    between frames of the same swing.
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
    top = heads[0]

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
        # Every walk frame is a standing pose, so the median IS the height.
        heights = sorted(m["body"] for row in raw for m in row)
    else:
        # Frames 1 and 8 are ready / return-to-ready: the only poses in a swing
        # whose height is not inflated by the mace being over the helmet.
        heights = sorted(raw[r][c]["body"]
                         for r in range(rows_count) for c in (0, COLUMNS - 1))
    reference = heights[len(heights) // 2]

    metrics = measure(reference)
    scale = TARGET_BODY_HEIGHT / float(reference)

    anchors = []
    for r in range(rows_count):
        # Walk plays in place, so every frame is pinned and the drift goes. Attack
        # and death deliberately travel, so the row gets ONE anchor and the
        # motion survives.
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
# Pipeline
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
            frame = ptk_sheet.render_frame(
                sheet, ox, oy, grid.cell_w, grid.cell_h,
                ax, ay, scale, CANVAS, PIVOT)
            ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
            # Seeded on the chest: high enough to be armour in every pose,
            # low enough that the last death frame still has body there.
            dropped = ptk_sheet.keep_connected(frame, (PIVOT[0], PIVOT[1] - 40))
            clipped = ptk_sheet.border_contact(frame)
            name = ("{0}_{1}_{2:02d}.png".format(anim, direction, c + 1) if direction
                    else "{0}_{1:02d}.png".format(anim, c + 1))
            ptk_png.write_png(os.path.join(out_dir, name), frame)
            results.append(dict(name=name, dropped=dropped, clipped=clipped))
            note = ""
            if dropped:
                note += "  spill removed {0}px".format(dropped)
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
    name = "Aegis_{0}{1}_8F.png".format(anim, ("_" + tag) if tag else "")
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
             .format(", ".join(missing), "Aegis"))
    log("  idle   4 real standing frames present "
        "(from the turnaround - see Tools/ExtractGuardIdle.py)")


def verify_defend(direction, cells, reference_blue):
    """Refuses to write a defence sheet whose content contradicts its direction."""
    blue = sum(bright_blue_fraction(c) for c in cells) / len(cells)
    bias = []
    for cell in cells:
        v = facing_reach(cell)
        if v:
            bias.append(v[0] - v[1])
    mean_bias = sum(bias) / len(bias) if bias else 0.0

    if direction == "Up" and blue >= reference_blue:
        fail("defend Up reads {0:.2f}% bright blue against Down's {1:.2f}% - the "
             "back must carry LESS".format(blue, reference_blue))
    if direction == "Left" and mean_bias <= 0.0:
        fail("defend Left has bias {0:+.3f} - positive means LEFT".format(mean_bias))
    if direction == "Right" and mean_bias >= 0.0:
        fail("defend Right has bias {0:+.3f} - negative means RIGHT".format(mean_bias))
    return "{0:.2f}% bright blue, bias {1:+.3f}".format(blue, mean_bias), blue


def extract_defend():
    """
    Aegis's shield brace: 4 directions x 8 frames.

    Each sheet is one direction, so the eight cells are a SEQUENCE rather than
    two rows of different views - which is why this does not go through
    plan_sheet(), whose rows are directions.

    Anchoring follows the attack rule rather than the walk rule: a brace is a
    deliberate one-shot action that plants and returns, so the row gets ONE
    anchor taken from its rest frames and any lean survives.
    """
    log("")
    log("=" * 76)
    log("Defend  4 directions x {0} frames".format(DEFEND_FRAME_COUNT))

    out_root = os.path.join(FRAMES_DIR, "Defend")
    results = []
    reference_blue = None

    for direction, filename in DEFEND_SHEETS:
        path = os.path.join(SOURCE_DIR, filename)
        if not os.path.isfile(path):
            fail("defend sheet missing: " + path)
        sheet = ptk_png.read_png(path)
        grid = ptk_sheet.Grid(sheet, DEFEND_COLUMNS, DEFEND_ROWS)
        # Row-major: the eight frames run left to right, top row then bottom.
        order = [(c, r) for r in range(DEFEND_ROWS) for c in range(DEFEND_COLUMNS)]
        cells = [grid.cell(c, r) for c, r in order]

        how, blue = verify_defend(direction, cells, reference_blue)
        if direction == "Down":
            reference_blue = blue

        raw = [body_metrics(cell, grid.cell_w * 1.05) for cell in cells]
        if any(m is None for m in raw):
            fail("defend {0}: a frame is empty".format(direction))
        # Frames 1 and 8 are the stance before the shield comes up and after it
        # settles - the only two whose height is not inflated by the raised shield.
        rest = sorted((raw[0]["body"], raw[-1]["body"]))
        reference = rest[len(rest) // 2]
        metrics = [body_metrics(cell, reference) for cell in cells]
        scale = TARGET_BODY_HEIGHT / float(reference)
        anchors = ptk_sheet.anchors_for_row(metrics, hold_still=False)

        out_dir = os.path.join(out_root, direction)
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)

        log("")
        log("  {0:<5s} <- {1}   identity: {2}".format(direction, filename[:8], how))
        log("        body {0} px -> scale x{1:.4f}".format(reference, scale))

        for index, (c, r) in enumerate(order):
            ox, oy = grid.origin(c, r)
            ax, ay = anchors[index]
            bounds = (ox, int(round((c + 1) * grid.cell_w)))
            frame = ptk_sheet.render_frame(
                sheet, ox, oy, grid.cell_w, grid.cell_h,
                ax, ay, scale, CANVAS, PIVOT, x_bounds=bounds)
            ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
            # Detached DARK art is his own mace or shield rim and stays; only a
            # neighbouring frame that bled in is far enough away to be dropped.
            dropped = ptk_sheet.clean_islands(
                frame, (PIVOT[0], PIVOT[1] - 40), is_energy,
                max_gap=8, drop_effect=False)
            clipped = ptk_sheet.border_contact(frame)
            if clipped:
                fail("Defend_{0}_{1:02d} is clipped by the canvas ({2} px on the "
                     "edge)".format(direction, index + 1, clipped))
            name = "Defend_{0}_{1:02d}.png".format(direction, index + 1)
            ptk_png.write_png(os.path.join(out_dir, name), frame)
            results.append(name)
            log("    {0}{1}".format(name, "  strays removed {0}px".format(dropped)
                                    if dropped else ""))

    # Contact sheet: one row per direction, eight frames across.
    if not os.path.isdir(SHEETS_DIR):
        os.makedirs(SHEETS_DIR)
    cw, ch = CANVAS
    out = ptk_png.Image(cw * DEFEND_FRAME_COUNT, ch * len(DEFEND_SHEETS))
    for row, (direction, _f) in enumerate(DEFEND_SHEETS):
        for index in range(DEFEND_FRAME_COUNT):
            p = os.path.join(out_root, direction,
                             "Defend_{0}_{1:02d}.png".format(direction, index + 1))
            out.paste(ptk_png.read_png(p), index * cw, row * ch)
    ptk_png.write_png(os.path.join(SHEETS_DIR, "Aegis_Defend_8F.png"), out)
    log("")
    log("  sheet  Aegis_Defend_8F.png  ({0}x{1})  rows: Down Up Left Right"
        .format(out.width, out.height))
    return results


def choose_canvas(measure_only):
    """Measure every sheet first, then size one canvas that holds them all."""
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
    parser = argparse.ArgumentParser(description="Extract Aegis's animations.")
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    log("Aegis animation extraction")
    log("target body height {0:.0f} px (Ravager is 116)".format(TARGET_BODY_HEIGHT))
    log("")

    worst, report = choose_canvas(args.measure)
    log("")
    log("WORST CASE from the feet anchor:  left {0:.0f}  right {1:.0f}  up {2:.0f}  down {3:.0f}"
        .format(*worst))

    have = (PIVOT[0], CANVAS[0] - PIVOT[0] - 1, PIVOT[1], CANVAS[1] - PIVOT[1] - 1)
    log("canvas {0}x{1} pivot {2} provides:   left {3} right {4} up {5} down {6}"
        .format(CANVAS[0], CANVAS[1], PIVOT, *have))
    if any(w > h for w, h in zip(worst, have)):
        fail("Aegis does not fit {0}x{1} at pivot {2} - needs left {3:.0f} right {4:.0f} "
             "up {5:.0f} down {6:.0f}".format(CANVAS[0], CANVAS[1], PIVOT, *worst))
    log("fits with margin: {0:.0f} / {1:.0f} / {2:.0f} / {3:.0f} px to spare"
        .format(*[h - w for w, h in zip(worst, have)]))

    if args.measure:
        for (spec, rows_count, _s, _g, _c, _m, _a, scale, reference, need, how) in report:
            tag = "/".join(spec["rows"]) if spec["rows"] else "non-directional"
            log("")
            log("{0:<6s} {1:<16s} <- {2}".format(spec["anim"], tag, spec["file"][:8]))
            log("  identity: {0}".format(how))
            log("  body {0} px -> scale x{1:.4f}".format(reference, scale))
            log("  needs left {0:.0f} right {1:.0f} up {2:.0f} down {3:.0f}".format(*need))
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
    defend = extract_defend()

    log("")
    check_idle()

    log("")
    log("=" * 76)
    log("{0} frames written  ({1} walk/attack/death + {2} defend + 4 idle)".format(
        len(every) + len(defend) + 4, len(every), len(defend)))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED: " + ", ".join("{0} ({1}px)".format(r["name"], r["clipped"])
                                    for r in clipped))
    else:
        log("no frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
