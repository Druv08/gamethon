"""
Protect the King - 2D
Builds a visual comparison sheet of the four real Ravager idle frames.

    output: Docs/ravager_idle_comparison.png

Shows both downscale methods side by side so the quality trade-off can be
judged by eye, with the feet-anchor row drawn as a single continuous line
across all four views - if the line does not touch every pair of boots at the
same height, the alignment is wrong.

Run:  python Tools/BuildRavagerComparison.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png
import ExtractRavagerIdle as X

ZOOM = 3
PAD = 14
LABEL_H = 22

NEUTRAL_A = (105, 105, 112, 255)
NEUTRAL_B = (88, 88, 95, 255)
LINE_FEET = (255, 60, 60, 255)
LINE_PIVOT = (80, 255, 80, 255)
TEXT = (245, 245, 245, 255)

FONT = {
    "A": ["010", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"], "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"], "F": ["111", "100", "110", "100", "100"],
    "G": ["011", "100", "101", "101", "011"], "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"], "K": ["101", "110", "100", "110", "101"],
    "L": ["100", "100", "100", "100", "111"], "N": ["101", "111", "111", "111", "101"],
    "O": ["010", "101", "101", "101", "010"], "P": ["110", "101", "110", "100", "100"],
    "R": ["110", "101", "110", "101", "101"], "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"], "U": ["101", "101", "101", "101", "111"],
    "W": ["101", "101", "111", "111", "101"], "X": ["101", "101", "010", "101", "101"],
    "1": ["010", "110", "010", "010", "111"], "2": ["110", "001", "010", "100", "111"],
    "4": ["101", "101", "111", "001", "001"], "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"], "0": ["111", "101", "101", "101", "111"],
    "/": ["001", "001", "010", "100", "100"], "-": ["000", "000", "111", "000", "000"],
    "(": ["001", "010", "010", "010", "001"], ")": ["100", "010", "010", "010", "100"],
    ",": ["000", "000", "000", "010", "100"], ".": ["000", "000", "000", "000", "010"],
    " ": ["000", "000", "000", "000", "000"], "=": ["000", "111", "000", "111", "000"],
    ":": ["000", "010", "000", "010", "000"],
}


def text(img, x, y, message, colour, scale=2):
    cursor = x
    for ch in message.upper():
        glyph = FONT.get(ch)
        if glyph:
            for row, bits in enumerate(glyph):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                px = cursor + col * scale + dx
                                py = y + row * scale + dy
                                if 0 <= px < img.width and 0 <= py < img.height:
                                    img.set(px, py, colour)
        cursor += 4 * scale


def main():
    img = ptk_png.read_png(X.SOURCE)
    X.remove_background(img)
    groups = X.find_view_groups(img)
    if len(groups) != 4:
        print("expected 4 views, got %d" % len(groups))
        return 1

    views = []
    for name, (x0, x1) in zip(X.GROUP_ORDER, groups):
        y0, y1 = X.vertical_bounds(img, x0, x1)
        head_cx = X.helmet_centre(img, x0, x1, y0)
        views.append((name, head_cx, X.FEET_ROW[name], (x0, y0, x1, y1)))

    order = ["Down", "Up", "Left", "Right"]      # display order requested
    modes = [("box  (area average)  - INSTALLED", "box"),
             ("nearest neighbour    - comparison", "nearest")]

    cell = X.FRAME_W * ZOOM
    width = PAD + 4 * (cell + PAD)
    height = PAD + len(modes) * (LABEL_H + cell + PAD) + LABEL_H

    sheet = ptk_png.Image(width, height)
    # neutral checkerboard so transparency and dark armour are both readable
    for y in range(height):
        for x in range(width):
            sheet.set(x, y, NEUTRAL_A if ((x // 8) + (y // 8)) % 2 == 0 else NEUTRAL_B)

    for mi, (label, mode) in enumerate(modes):
        top = PAD + mi * (LABEL_H + cell + PAD)
        text(sheet, PAD, top + 4, label, TEXT, 2)
        row_top = top + LABEL_H

        for ci, name in enumerate(order):
            entry = next(v for v in views if v[0] == name)
            _, head_cx, feet, clip = entry
            frame = X.build_frame(img, head_cx, feet, mode, clip)

            left = PAD + ci * (cell + PAD)
            for oy in range(X.FRAME_H):
                for ox in range(X.FRAME_W):
                    r, g, b, a = frame.get(ox, oy)
                    if not a:
                        continue
                    for dy in range(ZOOM):
                        for dx in range(ZOOM):
                            sheet.set(left + ox * ZOOM + dx,
                                      row_top + oy * ZOOM + dy, (r, g, b, 255))

            # pivot column (green), inside this cell only
            for yy in range(cell):
                sheet.set(left + X.PIVOT_X * ZOOM, row_top + yy, LINE_PIVOT)

            text(sheet, left + 4, row_top + cell + 3, name, TEXT, 2)

        # feet baseline drawn straight across all four cells
        fy = row_top + X.PIVOT_Y * ZOOM
        for x in range(PAD, width - PAD):
            sheet.set(x, fy, LINE_FEET)

    text(sheet, PAD, height - LABEL_H + 2,
         "128X128  SCALE 1/4  PIVOT (64,119)  RED=FEET ROW 119  GREEN=COLUMN 64",
         TEXT, 2)

    out = os.path.join(X.PROJECT, "Docs", "ravager_idle_comparison.png")
    ptk_png.write_png(out, sheet)
    print("wrote %s  (%dx%d)" % (out, width, height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
