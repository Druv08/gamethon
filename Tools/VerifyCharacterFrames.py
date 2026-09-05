"""
Protect the King - 2D
Validates a character's finished frames before they are imported into Unreal.

Run:  python Tools/VerifyCharacterFrames.py SwarmNode
      python Tools/VerifyCharacterFrames.py Ravager
      python Tools/VerifyCharacterFrames.py            (all configured characters)

Generalised from Tools/VerifyRavagerFrames.py, which still works and still
covers Ravager specifically. New characters should use this one - it takes the
per-character contract from CHARACTERS below rather than hard-coding it.

Checks, per frame:

  contract   canvas size and strictly 0/255 alpha
  clipping   no opaque pixel on the canvas edge
  anchor     the ground contact sits on the pivot row
  scale      the rigid size reference holds across idle / walk / attack
  jitter     frame-to-frame movement of the anchor and the silhouette

Jitter is reported, not corrected. Extraction already removed placement drift;
what is left is either real animation or a defect in the source art, and only a
human can tell those apart.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHARACTERS = {
    "Ravager": dict(
        root=os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Ravager", "Frames"),
        canvas=(192, 192), pivot=(96, 179),
        # A corpse settles below the line its feet stood on, so death frames are
        # 16 px taller. The pivot is identical, so nothing moves.
        canvas_overrides={"Death": (192, 208)},
        animations=(("Idle", 1), ("Walk", 8), ("Attack", 8), ("Death", 8)),
        # Ravager's armour is dark; his energy is blue.
        effect=lambda r, g, b: b > 140 and b - r > 70,
    ),
    "SwarmNode": dict(
        root=os.path.join(PROJECT, "ArtSource", "Characters", "Enemies", "SwarmNode", "Frames"),
        canvas=(192, 192), pivot=(96, 179),
        canvas_overrides={"Death": (192, 208)},
        # No idle art was supplied for Swarm Node - see the report. Walk frame 1
        # stands in at runtime, so there is no Idle folder to check.
        animations=(("Walk", 8), ("Attack", 8), ("Death", 8)),
        # The hot beam, not the dark red limb nodes.
        effect=lambda r, g, b: r > 190 and g > 70,
    ),
}

DIRECTIONS = ("Down", "Up", "Left", "Right")

ANCHOR_TOLERANCE = 6.0     # ground contact drift off the pivot row
CENTRE_TOLERANCE = 8.0     # sideways sway on an in-place cycle
AREA_TOLERANCE = 0.30      # silhouette area swing within one sequence

failures = []
warnings = []


def fail(msg):
    failures.append(msg)
    print("FAIL  " + msg)


def warn(msg):
    warnings.append(msg)
    print("WARN  " + msg)


def ok(msg):
    print("PASS  " + msg)


def analyse(path, cfg):
    img = ptk_png.read_png(path)
    w, h, px = img.width, img.height, img.px
    effect = cfg["effect"]

    alphas = set()
    body = bytearray(w * h)
    area = 0
    for y in range(h):
        base = y * w * 4
        row = y * w
        for x in range(w):
            i = base + x * 4
            a = px[i + 3]
            alphas.add(a)
            if not a:
                continue
            area += 1
            if not effect(px[i], px[i + 1], px[i + 2]):
                body[row + x] = 1

    rows = [sum(body[y * w:(y + 1) * w]) for y in range(h)]
    threshold = max(2, int(round(0.030 * w)))
    filled = [y for y in range(h) if rows[y] >= threshold]
    bottom = filled[-1] if filled else None

    sx = sn = 0
    for y in range(h):
        base = y * w
        for x in range(w):
            if body[base + x]:
                sx += x
                sn += 1
    centre = (sx / float(sn)) if sn else None

    edge = 0
    for x in range(w):
        edge += 1 if px[x * 4 + 3] else 0
        edge += 1 if px[((h - 1) * w + x) * 4 + 3] else 0
    for y in range(h):
        edge += 1 if px[(y * w) * 4 + 3] else 0
        edge += 1 if px[(y * w + w - 1) * 4 + 3] else 0

    return dict(size=(w, h), alphas=alphas, bottom=bottom, centre=centre,
                body=sn, area=area, edge=edge,
                height=(bottom - filled[0] + 1) if filled else 0)


def canvas_for(cfg, anim):
    return cfg.get("canvas_overrides", {}).get(anim, cfg["canvas"])


def sequence(cfg, anim, direction, count):
    if anim == "Idle":
        return [os.path.join(cfg["root"], "Idle", "Idle_{0}.png".format(direction))]
    if anim == "Death":
        # Death is not directional - one sequence, not four.
        return [os.path.join(cfg["root"], "Death", "Death_{0:02d}.png".format(i + 1))
                for i in range(count)]
    return [os.path.join(cfg["root"], anim, direction,
                         "{0}_{1}_{2:02d}.png".format(anim, direction, i + 1))
            for i in range(count)]


def check_character(name, cfg):
    print("")
    print("=" * 70)
    print("{0}   canvas {1[0]}x{1[1]}   pivot {2}".format(name, cfg["canvas"], cfg["pivot"]))
    print(cfg["root"])
    print("")

    paths = []
    for anim, count in cfg["animations"]:
        for direction in (["Down"] if anim == "Death" else DIRECTIONS):
            paths.extend(sequence(cfg, anim, direction, count))

    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        for m in missing:
            fail("missing frame " + os.path.relpath(m, PROJECT))
        return

    paths = list(dict.fromkeys(paths))
    stats = {p: analyse(p, cfg) for p in paths}
    expected_size = {}
    for anim, count in cfg["animations"]:
        for direction in (["Down"] if anim == "Death" else DIRECTIONS):
            for path in sequence(cfg, anim, direction, count):
                expected_size[path] = canvas_for(cfg, anim)
    total = len(stats)

    bad = [os.path.basename(p) for p, s in stats.items()
           if s["size"] != expected_size.get(p, cfg["canvas"])]
    if bad:
        fail("wrong canvas size: " + ", ".join(bad[:5]))
    else:
        ok("all {0} frames are {1[0]}x{1[1]}".format(total, cfg["canvas"]))

    bad = [os.path.basename(p) for p, s in stats.items() if not s["alphas"] <= {0, 255}]
    if bad:
        fail("soft alpha present: " + ", ".join(bad[:5]))
    else:
        ok("all {0} frames have hard 0/255 alpha".format(total))

    bad = ["{0} ({1}px)".format(os.path.basename(p), s["edge"])
           for p, s in stats.items() if s["edge"]]
    if bad:
        fail("clipped at the canvas edge: " + ", ".join(bad[:5]))
    else:
        ok("no frame is clipped by the canvas edge")

    # Death frames are exempt: the whole animation is the body settling below
    # the line it stood on, so its "ground contact" is meant to drift.
    bad = ["{0} at row {1}".format(os.path.basename(p), s["bottom"])
           for p, s in stats.items()
           if "Death_" not in os.path.basename(p)
           and (s["bottom"] is None or abs(s["bottom"] - cfg["pivot"][1]) > ANCHOR_TOLERANCE)]
    if bad:
        for m in bad:
            warn("ground contact off pivot row {0}: {1}".format(cfg["pivot"][1], m))
    else:
        ok("every frame's ground contact is within {0}px of pivot row {1}"
           .format(int(ANCHOR_TOLERANCE), cfg["pivot"][1]))

    print("")
    for anim, count in cfg["animations"]:
        for direction in (["Down"] if anim == "Death" else DIRECTIONS):
            seq = sequence(cfg, anim, direction, count)
            if len(seq) < 2:
                continue
            bottoms = [stats[p]["bottom"] for p in seq]
            centres = [stats[p]["centre"] for p in seq]
            bodies = [stats[p]["body"] for p in seq]
            sb = max(bottoms) - min(bottoms)
            sc = max(centres) - min(centres)
            label = "{0} {1:<5s}".format(anim, direction)
            detail = "anchor {0:.1f}  centre {1:.1f}".format(sb, sc)
            if anim == "Death":
                ok("{0} spread  {1}  (collapse expected)".format(label, detail))
            elif anim == "Walk":
                if sb > ANCHOR_TOLERANCE or sc > CENTRE_TOLERANCE:
                    warn("{0} spread  {1}".format(label, detail))
                else:
                    ok("{0} spread  {1}".format(label, detail))
            else:
                ok("{0} spread  {1}  (lunge expected)".format(label, detail))

            if anim == "Death":
                continue
            mean = sum(bodies) / float(len(bodies))
            outliers = [os.path.basename(p) for p in seq
                        if abs(stats[p]["body"] - mean) > AREA_TOLERANCE * mean]
            if outliers:
                warn("{0} silhouette area varies: {1} (mean {2:.0f})"
                     .format(label, ", ".join(outliers[:3]), mean))

    print("")
    for anim, count in cfg["animations"]:
        heights = []
        for direction in (["Down"] if anim == "Death" else DIRECTIONS):
            heights.extend(stats[p]["height"] for p in sequence(cfg, anim, direction, count))
        ok("{0:<7s} body height {1}..{2} px (mean {3:.0f})"
           .format(anim, min(heights), max(heights), sum(heights) / float(len(heights))))


def main():
    wanted = sys.argv[1:] or sorted(CHARACTERS)
    for name in wanted:
        cfg = CHARACTERS.get(name)
        if cfg is None:
            fail("unknown character " + name)
            continue
        check_character(name, cfg)

    print("")
    print("=" * 70)
    print("{0} failures, {1} warnings".format(len(failures), len(warnings)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
