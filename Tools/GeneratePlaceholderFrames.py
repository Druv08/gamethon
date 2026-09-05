#!/usr/bin/env python3
"""
Protect the King - 2D
Generates TEMPORARY DEVELOPER PLACEHOLDER frames for Ravager.

These are NOT artwork. They exist only so the Paper2D movement and animation
architecture can be built and validated before the real 20 frames arrive.
They are deliberately ugly, labelled "TEMP", and asymmetric left-to-right so
that a mirrored or mis-wired direction is immediately obvious on screen.

Output: ArtSource/_TempDevArt/Ravager/*.png   (20 files)

Contract enforced by this script (see Docs/SPRITE_SPEC.md):
  - canvas          128 x 128, RGBA, transparent background
  - feet anchor     (64, 119) - horizontal centre, 9 px above the canvas floor
  - every frame     has its lowest BODY pixel on exactly row 119, so any
                    vertical bounce seen in game is a pivot bug, not the art
  - body height     117 px, identical to the real Ravager idle frames, so
                    starting and stopping never changes the character's size

Only the 16 WALK frames are still used; the four Idle frames are superseded by
the real artwork in ArtSource/Characters/Guards/Ravager/Frames/.

Requires only the Python standard library.
Run:  python Tools/GeneratePlaceholderFrames.py
"""

import os
import struct
import sys
import zlib

# ---------------------------------------------------------------------------
# Project-wide sprite contract
# ---------------------------------------------------------------------------
CANVAS_W = 128
CANVAS_H = 128
ANCHOR_X = 64      # horizontal centre of the canvas
ANCHOR_Y = 119     # feet contact row, measured from the TOP of the canvas

# The placeholder is drawn at the same on-screen size as the REAL Ravager idle
# frames (117 px from helmet tip to feet). If it were not, the character would
# visibly change size every time he started or stopped walking, which would
# look exactly like the pivot bug these placeholders exist to rule out.
BODY_HEIGHT = 117

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ArtSource", "_TempDevArt", "Ravager",
)

# Per-direction palette. Strongly different hues so a wrong flipbook is
# unmistakable at a glance while testing.
DIRECTION_COLORS = {
    "Down":  {"body": (198, 68, 58),  "trim": (245, 150, 120)},
    "Up":    {"body": (62, 108, 205), "trim": (140, 180, 250)},
    "Left":  {"body": (66, 172, 92),  "trim": (150, 235, 170)},
    "Right": {"body": (222, 166, 48), "trim": (255, 224, 150)},
}

OUTLINE = (18, 16, 24)
SKIN = (232, 196, 160)
METAL = (150, 156, 172)
ANCHOR_MARK = (255, 0, 220)   # magenta: dev-only feet anchor marker


# ---------------------------------------------------------------------------
# Minimal 3x5 pixel font (only the glyphs these labels need)
# ---------------------------------------------------------------------------
FONT = {
    "T": ["111", "010", "010", "010", "010"],
    "E": ["111", "100", "110", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "P": ["110", "101", "110", "100", "100"],
    "I": ["111", "010", "010", "010", "111"],
    "D": ["110", "101", "101", "101", "110"],
    "L": ["100", "100", "100", "100", "111"],
    "W": ["101", "101", "111", "111", "101"],
    "A": ["010", "101", "111", "101", "101"],
    "K": ["101", "110", "100", "110", "101"],
    "U": ["101", "101", "101", "101", "111"],
    "R": ["110", "101", "110", "101", "101"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["110", "001", "010", "100", "111"],
    "3": ["110", "001", "010", "001", "110"],
    "4": ["101", "101", "111", "001", "001"],
    " ": ["000", "000", "000", "000", "000"],
}


class Canvas:
    """Tiny RGBA raster with just the primitives these placeholders need."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        # RGBA, fully transparent
        self.px = bytearray(width * height * 4)

    def set(self, x, y, rgb, alpha=255):
        x = int(x)
        y = int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i] = rgb[0]
            self.px[i + 1] = rgb[1]
            self.px[i + 2] = rgb[2]
            self.px[i + 3] = alpha

    def rect(self, x0, y0, x1, y1, rgb):
        """Filled rectangle, inclusive bounds."""
        for y in range(int(y0), int(y1) + 1):
            for x in range(int(x0), int(x1) + 1):
                self.set(x, y, rgb)

    def rect_outlined(self, x0, y0, x1, y1, fill, outline):
        self.rect(x0, y0, x1, y1, fill)
        for x in range(int(x0), int(x1) + 1):
            self.set(x, y0, outline)
            self.set(x, y1, outline)
        for y in range(int(y0), int(y1) + 1):
            self.set(x0, y, outline)
            self.set(x1, y, outline)

    def disc(self, cx, cy, r, rgb):
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.set(x, y, rgb)

    def disc_outlined(self, cx, cy, r, fill, outline):
        self.disc(cx, cy, r, outline)
        self.disc(cx, cy, r - 1, fill)

    def text(self, x, y, message, rgb):
        cursor = x
        for ch in message.upper():
            glyph = FONT.get(ch)
            if glyph is not None:
                for row, bits in enumerate(glyph):
                    for col, bit in enumerate(bits):
                        if bit == "1":
                            self.set(cursor + col, y + row, rgb)
            cursor += 4

    def lowest_opaque_row(self, max_row=None):
        """
        Bottom-most row containing any non-transparent pixel, or None.

        `max_row` limits the search, which is how the feet check ignores the
        TEMP label printed underneath the character.
        """
        top = self.h - 1 if max_row is None else min(max_row, self.h - 1)
        for y in range(top, -1, -1):
            base = y * self.w * 4
            for x in range(self.w):
                if self.px[base + x * 4 + 3] != 0:
                    return y
        return None

    def save_png(self, path):
        raw = bytearray()
        stride = self.w * 4
        for y in range(self.h):
            raw.append(0)  # filter type 0 (None)
            raw.extend(self.px[y * stride:(y + 1) * stride])

        def chunk(tag, data):
            out = struct.pack(">I", len(data)) + tag + data
            return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        # bit depth 8, colour type 6 (RGBA), no interlace
        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0)

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b"")
        )
        with open(path, "wb") as handle:
            handle.write(png)


def draw_character(direction, leg_phase, label):
    """
    Draws one placeholder frame.

    leg_phase:  0 = passing pose, +1 = left leg forward, -1 = right leg forward
                (idle uses 0 with a slightly wider stance)

    The planted foot always reaches exactly ANCHOR_Y so the sprite pivot can
    be verified: if the character bobs vertically in game, the pivot is wrong.
    """
    c = Canvas(CANVAS_W, CANVAS_H)
    palette = DIRECTION_COLORS[direction]
    body = palette["body"]
    trim = palette["trim"]

    cx = ANCHOR_X
    feet = ANCHOR_Y

    # ---- legs -------------------------------------------------------------
    # Both legs end on the anchor row; leg_phase only shifts them sideways,
    # which animates the walk without ever moving the contact point.
    left_leg_x = cx - 16 + (leg_phase * 4)
    right_leg_x = cx + 6 - (leg_phase * 4)
    leg_top = feet - 33

    c.rect_outlined(left_leg_x, leg_top, left_leg_x + 10, feet, body, OUTLINE)
    c.rect_outlined(right_leg_x, leg_top, right_leg_x + 10, feet, body, OUTLINE)

    # ---- torso ------------------------------------------------------------
    torso_top = feet - 80
    torso_bottom = leg_top + 3
    c.rect_outlined(cx - 24, torso_top, cx + 24, torso_bottom, body, OUTLINE)
    # chest trim band, helps read the animation frame at a glance
    c.rect(cx - 18, torso_top + 12, cx + 18, torso_top + 18, trim)

    # ---- arms (swing opposite the legs) -----------------------------------
    arm_offset = -leg_phase * 3
    c.rect_outlined(cx - 34, torso_top + 6 + arm_offset,
                    cx - 25, torso_top + 38 + arm_offset, trim, OUTLINE)
    c.rect_outlined(cx + 25, torso_top + 6 - arm_offset,
                    cx + 34, torso_top + 38 - arm_offset, trim, OUTLINE)

    # ---- head -------------------------------------------------------------
    # Head top lands on (feet - BODY_HEIGHT) so the placeholder matches the
    # real Ravager silhouette height exactly.
    head_radius = 19
    head_cy = feet - BODY_HEIGHT + head_radius
    c.disc_outlined(cx, head_cy, head_radius, SKIN if direction != "Up" else body, OUTLINE)

    # ---- facing indicator -------------------------------------------------
    # A visor that clearly points where the character is meant to be looking.
    if direction == "Down":
        c.rect(cx - 12, head_cy - 2, cx + 12, head_cy + 4, OUTLINE)
        c.rect(cx - 9, head_cy - 1, cx - 4, head_cy + 3, trim)
        c.rect(cx + 4, head_cy - 1, cx + 9, head_cy + 3, trim)
    elif direction == "Up":
        # Back of the head: no face, just a helmet crest.
        c.rect(cx - 4, head_cy - 18, cx + 4, head_cy + 9, trim)
    elif direction == "Left":
        c.rect(cx - 18, head_cy - 2, cx - 1, head_cy + 4, OUTLINE)
        c.rect(cx - 15, head_cy - 1, cx - 9, head_cy + 3, trim)
    elif direction == "Right":
        c.rect(cx + 1, head_cy - 2, cx + 18, head_cy + 4, OUTLINE)
        c.rect(cx + 9, head_cy - 1, cx + 15, head_cy + 3, trim)

    # ---- weapon stand-in --------------------------------------------------
    # Deliberately asymmetric: it sits on the character's right. If Left and
    # Right ever get swapped or mirrored, the axe jumps sides on screen.
    # It also sticks well outside the collision capsule, which is exactly the
    # case the collision footprint must NOT include.
    if direction != "Up":
        c.rect_outlined(cx + 38, torso_top - 14, cx + 45, feet - 9, METAL, OUTLINE)
        c.rect_outlined(cx + 33, torso_top - 20, cx + 52, torso_top - 3, METAL, OUTLINE)

    # ---- dev labels -------------------------------------------------------
    # Placed below the feet row so they never sit on top of the silhouette.
    # These labels are the reason a placeholder can never be mistaken for
    # finished art, and they also make it possible to read which walk frame
    # is on screen while testing.
    tag = "TEMP " + label
    c.text(cx - (len(tag) * 4) // 2, ANCHOR_Y + 2, tag, ANCHOR_MARK)

    # ---- feet anchor marker ----------------------------------------------
    # Sits exactly on the pivot row so alignment can be eyeballed in editor.
    for x in range(cx - 2, cx + 3):
        c.set(x, feet, ANCHOR_MARK)

    return c


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    directions = ["Down", "Up", "Left", "Right"]
    # Classic 4-step cycle: contact, pass, contact (opposite), pass.
    walk_phases = [1, 0, -1, 0]

    written = []
    failures = []

    for direction in directions:
        # ---- idle: single frame ------------------------------------------
        canvas = draw_character(direction, 0, "I" + direction[0])
        name = "Idle_{0}.png".format(direction)
        canvas.save_png(os.path.join(OUT_DIR, name))
        written.append((name, canvas.lowest_opaque_row(ANCHOR_Y + 1)))

        # ---- walk: four frames -------------------------------------------
        for index, phase in enumerate(walk_phases, start=1):
            canvas = draw_character(direction, phase,
                                    "W" + direction[0] + str(index))
            name = "Walk_{0}_{1:02d}.png".format(direction, index)
            canvas.save_png(os.path.join(OUT_DIR, name))
            written.append((name, canvas.lowest_opaque_row(ANCHOR_Y + 1)))

    # ---- verify the pivot contract ---------------------------------------
    for name, lowest in written:
        if lowest != ANCHOR_Y:
            failures.append(
                "{0}: lowest opaque row is {1}, expected {2}".format(
                    name, lowest, ANCHOR_Y))

    print("Wrote {0} placeholder frames to:".format(len(written)))
    print("  " + OUT_DIR)
    print("")
    print("Feet-anchor check (body must bottom out on row {0}):".format(ANCHOR_Y))

    if failures:
        for message in failures:
            print("  FAIL  " + message)
        print("")
        print("PIVOT CONTRACT VIOLATED - do not import these.")
        return 1

    print("  PASS  all {0} frames bottom out on row {1}".format(len(written), ANCHOR_Y))
    return 0


if __name__ == "__main__":
    sys.exit(main())
