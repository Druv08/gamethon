"""
Protect the King - 2D
Extracts the 8-frame DEATH collapse for Ravager and Swarm Node.

    source : <Downloads>/gamethon pics/design 2d pics/<char> pics/*.png  (READ ONLY)
    output : ArtSource/Characters/.../<Char>/Frames/Death/Death_01..08.png
             ArtSource/Characters/.../<Char>/Sheets/<Char>_Death_8F.png

Run:  python Tools/ExtractDeathAnimations.py --measure
      python Tools/ExtractDeathAnimations.py

Uses the shared machinery in Tools/ptk_sheet.py, so the four corrections proven
on the walk and attack sheets apply here unchanged.


WHAT IS DIFFERENT ABOUT A DEATH SHEET
-------------------------------------
* It is 8 columns x ONE row, not two. Death is not directional - a character
  collapses the same way whichever way it was facing - so there is a single
  sequence rather than four.

* The whole point of the animation is that the body SINKS. Frame 1 stands and
  frame 8 is a heap on the floor, so body height is meaningless as a scale
  reference for anything but the first frame. Scale is therefore measured on
  frame 1 alone, where the character is still standing, and applied to all
  eight.

* Anchoring is a single fixed anchor taken from frame 1, exactly as the attack
  sheets are handled. Anchoring per frame would pin the collapsing silhouette
  back to the pivot every frame and cancel the collapse - the character would
  appear to melt in place rather than fall. The fixed anchor also guarantees
  frame 1 lines up with the last living frame, so nothing jumps at the moment
  of death.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ptk_sheet
from ExtractSwarmNodeAnimations import eye_height as swarm_eye_height

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLUMNS = 8

# 192x208, against 192x192 for every other animation - and the SAME pivot.
#
# A corpse settles below the line its feet stood on: Ravager's axe drops flat
# and lies on the ground, which in this view reads as lower on screen. Measured,
# that reaches 17 px below the standing feet row, against the 12 px a 192-tall
# canvas leaves under the pivot. Everything else fits comfortably.
#
# The extra 16 px is added to the BOTTOM only, so the pivot stays at (96,179)
# and the feet still land on the actor origin exactly as they do in idle, walk
# and attack. Paper2D stores a pivot per sprite, so a taller death frame costs
# nothing at runtime and nothing has to move.
CANVAS = (192, 208)
PIVOT = (96, 179)
SRC_ALPHA_THRESHOLD = 128
OUT_ALPHA_THRESHOLD = 128


def ravager_effect(r, g, b):
    """Blue energy: axe blades, visor, chest core."""
    return b > 140 and b - r > 70


def swarm_effect(r, g, b):
    """The hot beam only - the dark red limb nodes are body."""
    return r > 190 and g > 70


def ravager_scale(cell):
    """Ravager stands 116 px helmet-to-feet in the finished frames."""
    body, _full, w, h = ptk_sheet.build_masks(cell, SRC_ALPHA_THRESHOLD, ravager_effect)
    anchor = ptk_sheet.ground_anchor(body, w, h)
    return 116.0 / float(anchor["height"]), "body height {0}px".format(anchor["height"])


def swarm_scale(cell):
    """Swarm Node is sized by its rigid central eye, not by its body."""
    eye = swarm_eye_height(cell)
    return 15.0 / float(eye), "eye {0}px".format(eye)


CHARACTERS = [
    dict(
        name="Ravager",
        root=os.path.join(PROJECT, "ArtSource", "Characters", "Guards", "Ravager"),
        file=r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\ravager pics"
             r"\83e94960-7a31-4b0c-81c7-05ea77120f65.png",
        effect=ravager_effect,
        scale_from=ravager_scale,
    ),
    dict(
        name="SwarmNode",
        root=os.path.join(PROJECT, "ArtSource", "Characters", "Enemies", "SwarmNode"),
        file=r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\swarmnode pics"
             r"\051a9431-6851-4705-ae1c-10d27041e85d.png",
        effect=swarm_effect,
        scale_from=swarm_scale,
    ),
]


def log(message):
    print(message)


def fail(message):
    raise SystemExit("ERROR: " + message)


def process(spec, measure_only):
    if not os.path.isfile(spec["file"]):
        fail("source sheet missing: " + spec["file"])

    sheet = ptk_png.read_png(spec["file"])
    grid = ptk_sheet.Grid(sheet, COLUMNS, 1)
    cells = [grid.cell(c, 0) for c in range(COLUMNS)]

    scale, how = spec["scale_from"](cells[0])

    masks = [ptk_sheet.build_masks(c, SRC_ALPHA_THRESHOLD, spec["effect"]) for c in cells]
    metrics = [ptk_sheet.ground_anchor(m[0], m[2], m[3]) for m in masks]
    bounds = [ptk_sheet.mask_bounds(m[1], m[2], m[3]) for m in masks]

    if any(m is None for m in metrics):
        fail(spec["name"] + ": a death frame is empty")

    # One anchor for the whole sequence, taken from the standing frame. See the
    # module docstring: per-frame anchoring would cancel the collapse.
    anchor = (metrics[0]["centre"], metrics[0]["bottom"])
    anchors = [anchor] * COLUMNS

    log("")
    log("=" * 76)
    log("{0} death  <-  {1}".format(spec["name"], os.path.basename(spec["file"])))
    log("  {0}x{1}, cell {2:.1f}x{3}, 8 frames x 1 row (non-directional)".format(
        sheet.width, sheet.height, grid.cell_w, grid.cell_h))
    log("  frame 1 {0}  ->  scale x{1:.4f}".format(how, scale))
    log("  collapse: body height {0} -> {1} px source".format(
        metrics[0]["height"], metrics[-1]["height"]))

    if measure_only:
        l, r, u, d = ptk_sheet.required_extent(metrics, anchors, bounds, scale)
        log("  needs left={0:.1f} right={1:.1f} up={2:.1f} down={3:.1f}"
            "   (canvas gives {4} / {5} / {6} / {7})".format(
                l, r, u, d, PIVOT[0], CANVAS[0] - PIVOT[0] - 1,
                PIVOT[1], CANVAS[1] - PIVOT[1] - 1))
        return []

    out_dir = os.path.join(spec["root"], "Frames", "Death")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    results = []
    for c in range(COLUMNS):
        ox, oy = grid.origin(c, 0)
        frame = ptk_sheet.render_frame(
            sheet, ox, oy, grid.cell_w, grid.cell_h,
            anchors[c][0], anchors[c][1], scale, CANVAS, PIVOT)
        ptk_sheet.harden_alpha(frame, OUT_ALPHA_THRESHOLD)
        # Seed low: by the last frame the character is a heap on the floor and
        # there is nothing left up where a standing torso would be.
        dropped = ptk_sheet.keep_connected(frame, (PIVOT[0], PIVOT[1] - 12))
        clipped = ptk_sheet.border_contact(frame)
        name = "Death_{0:02d}.png".format(c + 1)
        ptk_png.write_png(os.path.join(out_dir, name), frame)
        results.append(dict(name=name, dropped=dropped, clipped=clipped))
        note = ""
        if dropped:
            note += "  spill removed {0}px".format(dropped)
        if clipped:
            note += "  CLIPPED {0}px".format(clipped)
        log("    {0}{1}".format(name, note))

    sheets_dir = os.path.join(spec["root"], "Sheets")
    if not os.path.isdir(sheets_dir):
        os.makedirs(sheets_dir)
    cw, ch = CANVAS
    contact = ptk_png.Image(cw * COLUMNS, ch)
    for c in range(COLUMNS):
        contact.paste(ptk_png.read_png(os.path.join(out_dir, "Death_{0:02d}.png".format(c + 1))),
                      c * cw, 0)
    ptk_png.write_png(os.path.join(sheets_dir, "{0}_Death_8F.png".format(spec["name"])), contact)
    log("  sheet  {0}_Death_8F.png  ({1}x{2})".format(spec["name"], contact.width, contact.height))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    log("Death animation extraction")
    every = []
    for spec in CHARACTERS:
        every.extend(process(spec, args.measure))

    if args.measure:
        return

    log("")
    log("=" * 76)
    log("{0} frames written".format(len(every)))
    clipped = [r for r in every if r["clipped"]]
    if clipped:
        log("CLIPPED: " + ", ".join("{0} ({1}px)".format(r["name"], r["clipped"]) for r in clipped))
    else:
        log("no frame touches its canvas edge - nothing was clipped")


if __name__ == "__main__":
    main()
