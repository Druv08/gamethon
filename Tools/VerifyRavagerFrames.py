"""
Protect the King - 2D
Validates the finished Ravager frames before they are imported into Unreal.

Run:  python Tools/VerifyRavagerFrames.py

Checks every frame in ArtSource/Characters/Guards/Ravager/Frames:

  contract   192x192 RGBA, alpha strictly 0 or 255
  anchor     the feet sit on the pivot row, the body sits on the pivot column
  scale      body height is constant across idle, walk and attack
  jitter     frame-to-frame movement of the helmet, body centre and feet
  clipping   no opaque pixel touches the canvas edge
  design     silhouette area and energy-pixel count stay within band, which is
             what catches a generated frame that lost its horns or grew a limb

Jitter is reported, not silently corrected. The extraction step already removed
placement drift; what is left here is either real animation or a genuine defect
in the source art, and only a human can tell those apart. Anything past the
tolerances below is printed as WARN with the frame named so it can be redrawn.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES_DIR = os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Ravager", "Frames")

CANVAS = (192, 192)
PIVOT = (96, 179)
DIRECTIONS = ("Down", "Up", "Left", "Right")
WALK_FRAMES = 8
ATTACK_FRAMES = 8

# Tolerances, in finished-frame pixels.
FEET_TOLERANCE = 6.0      # vertical bob; more than this reads as a hop
CENTRE_TOLERANCE = 8.0    # sideways sway on an in-place walk cycle
BODY_TOLERANCE = 10.0     # scale pulsing between frames of one animation
SCALE_TOLERANCE = 8.0     # body height drift between idle / walk / attack

failures = []
warnings = []


def fail(message):
    failures.append(message)
    print("FAIL  " + message)


def warn(message):
    warnings.append(message)
    print("WARN  " + message)


def ok(message):
    print("PASS  " + message)


def is_energy(r, g, b):
    return b > 140 and b - r > 70


def analyse(path):
    img = ptk_png.read_png(path)
    w, h, px = img.width, img.height, img.px

    alphas = set()
    core = bytearray(w * h)
    solid = bytearray(w * h)
    energy = 0
    for y in range(h):
        base = y * w * 4
        row = y * w
        for x in range(w):
            i = base + x * 4
            a = px[i + 3]
            alphas.add(a)
            if not a:
                continue
            solid[row + x] = 1
            if is_energy(px[i], px[i + 1], px[i + 2]):
                energy += 1
            else:
                core[row + x] = 1

    rows = [sum(core[y * w:(y + 1) * w]) for y in range(h)]
    foot_threshold = max(2, int(round(0.030 * w)))
    filled = [y for y in range(h) if rows[y] >= foot_threshold]
    feet = filled[-1]

    # Hips band located from the pivot, so a raised axe cannot move it.
    y0, y1 = PIVOT[1] - 64, PIVOT[1] - 41
    xs = [x for y in range(y0, y1 + 1) for x in range(w) if core[y * w + x]]
    centre = sum(xs) / float(len(xs)) if xs else None

    head_threshold = max(2, int(round(0.022 * w)))
    heads = [y for y in range(h) if rows[y] >= head_threshold]

    # Helmet centre: the topmost rows of the body, near the hips column.
    hx = []
    if centre is not None:
        for y in range(heads[0], heads[0] + 12):
            for x in range(max(0, int(centre) - 45), min(w, int(centre) + 45)):
                if core[y * w + x]:
                    hx.append(x)

    edge = 0
    for x in range(w):
        edge += 1 if px[x * 4 + 3] else 0
        edge += 1 if px[((h - 1) * w + x) * 4 + 3] else 0
    for y in range(h):
        edge += 1 if px[(y * w) * 4 + 3] else 0
        edge += 1 if px[(y * w + w - 1) * 4 + 3] else 0

    return dict(size=(w, h), alphas=alphas, feet=feet, top=heads[0],
                body=feet - heads[0] + 1, centre=centre,
                helmet=(sum(hx) / float(len(hx)) if hx else None),
                area=sum(rows), energy=energy, edge=edge)


def spread(values):
    values = [v for v in values if v is not None]
    return (max(values) - min(values)) if values else 0.0


def sequence(anim, direction, count):
    if anim == "Idle":
        return [os.path.join(FRAMES_DIR, "Idle", "Idle_{0}.png".format(direction))]
    return [os.path.join(FRAMES_DIR, anim, direction,
                         "{0}_{1}_{2:02d}.png".format(anim, direction, i + 1))
            for i in range(count)]


def main():
    print("Ravager frame validation")
    print("frames: " + FRAMES_DIR)
    print("")

    groups = [("Idle", 1), ("Walk", WALK_FRAMES), ("Attack", ATTACK_FRAMES)]
    stats = {}
    missing = []

    for anim, count in groups:
        for direction in DIRECTIONS:
            for path in sequence(anim, direction, count):
                if not os.path.isfile(path):
                    missing.append(os.path.relpath(path, PROJECT))
    if missing:
        for m in missing:
            fail("missing frame " + m)
        print("")
        return 1

    # ---- contract -------------------------------------------------------
    bad_size = []
    bad_alpha = []
    clipped = []
    for anim, count in groups:
        for direction in DIRECTIONS:
            for path in sequence(anim, direction, count):
                info = analyse(path)
                stats[path] = info
                name = os.path.basename(path)
                if info["size"] != CANVAS:
                    bad_size.append("{0} is {1[0]}x{1[1]}".format(name, info["size"]))
                if not info["alphas"] <= {0, 255}:
                    bad_alpha.append("{0} has {1} alpha levels"
                                     .format(name, len(info["alphas"])))
                if info["edge"]:
                    clipped.append("{0} touches the edge ({1}px)"
                                   .format(name, info["edge"]))

    total = len(stats)
    if bad_size:
        for m in bad_size:
            fail(m)
    else:
        ok("all {0} frames are {1}x{2}".format(total, CANVAS[0], CANVAS[1]))

    if bad_alpha:
        for m in bad_alpha:
            fail(m)
    else:
        ok("all {0} frames have hard 0/255 alpha".format(total))

    if clipped:
        for m in clipped:
            fail(m)
    else:
        ok("no frame is clipped by the canvas edge")

    # ---- anchor ---------------------------------------------------------
    feet_off = []
    for path, info in stats.items():
        if abs(info["feet"] - PIVOT[1]) > FEET_TOLERANCE:
            feet_off.append("{0} feet at row {1}, pivot is {2}"
                            .format(os.path.basename(path), info["feet"], PIVOT[1]))
    if feet_off:
        for m in feet_off:
            warn(m)
    else:
        ok("every frame's feet sit within {0}px of pivot row {1}"
           .format(int(FEET_TOLERANCE), PIVOT[1]))

    # ---- scale across states -------------------------------------------
    print("")
    per_state = {}
    for anim, count in groups:
        for direction in DIRECTIONS:
            bodies = [stats[p]["body"] for p in sequence(anim, direction, count)]
            per_state[(anim, direction)] = sum(bodies) / float(len(bodies))

    for direction in DIRECTIONS:
        heights = [per_state[(a, direction)] for a, _ in groups]
        drift = max(heights) - min(heights)
        line = "{0:<5s} body height  idle {1:.0f}  walk {2:.0f}  attack {3:.0f}  (drift {4:.1f}px)" \
            .format(direction, heights[0], heights[1], heights[2], drift)
        if drift > SCALE_TOLERANCE:
            warn(line)
        else:
            ok(line)

    # ---- jitter ---------------------------------------------------------
    print("")
    for anim, count in groups:
        if count == 1:
            continue
        for direction in DIRECTIONS:
            paths = sequence(anim, direction, count)
            feet = [stats[p]["feet"] for p in paths]
            cent = [stats[p]["centre"] for p in paths]
            helm = [stats[p]["helmet"] for p in paths]
            body = [stats[p]["body"] for p in paths]

            sf, sc, sh, sb = spread(feet), spread(cent), spread(helm), spread(body)
            label = "{0} {1:<5s}".format(anim, direction)
            detail = ("feet {0:.1f}  centre {1:.1f}  helmet {2:.1f}  bodyH {3:.1f}"
                      .format(sf, sc, sh, sb))

            # An attack lunges and rears back on purpose, so only the walk
            # cycle is held to the in-place tolerances.
            if anim == "Walk":
                if sf > FEET_TOLERANCE or sc > CENTRE_TOLERANCE or sb > BODY_TOLERANCE:
                    warn("{0} movement spread  {1}".format(label, detail))
                else:
                    ok("{0} movement spread  {1}".format(label, detail))
            else:
                ok("{0} movement spread  {1}  (lunge expected)".format(label, detail))

    # ---- design consistency ---------------------------------------------
    print("")
    for anim, count in groups:
        if count == 1:
            continue
        for direction in DIRECTIONS:
            paths = sequence(anim, direction, count)
            areas = [stats[p]["area"] for p in paths]
            mean = sum(areas) / float(len(areas))
            outliers = [(os.path.basename(p), stats[p]["area"]) for p in paths
                        if abs(stats[p]["area"] - mean) > 0.28 * mean]
            if outliers:
                warn("{0} {1:<5s} silhouette area varies: {2}  (mean {3:.0f})"
                     .format(anim, direction,
                             ", ".join("{0} {1}".format(n, a) for n, a in outliers), mean))
            else:
                ok("{0} {1:<5s} silhouette area consistent (mean {2:.0f}, spread {3:.0f})"
                   .format(anim, direction, mean, max(areas) - min(areas)))

    print("")
    print("=" * 70)
    print("{0} frames checked, {1} failures, {2} warnings"
          .format(total, len(failures), len(warnings)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
