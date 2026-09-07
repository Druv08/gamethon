"""
Protect the King - 2D
Cuts the five destroyed guard-base spots out of the destroyed-state map render.

RUN (plain Python, no Unreal needed):
    python Tools/ExtractDestroyedBases.py

Reads   C:\\Users\\druvk\\Downloads\\gamethon pics\\design 2d pics\\destoyed map spots.png
Writes  ArtSource/Map/DestroyedBases/Destroyed_<Guard>.png


WHY A CROP AND NOT THE WHOLE IMAGE
----------------------------------
The supplied artwork is a FULL map, 1672x941, showing every base and the core
already ruined. Swapping the ground to it would show the whole battlefield
destroyed the moment one base fell, so only the base spots are taken.

The two renders are pixel-aligned - same dimensions, same layout, same camera -
so a crop taken at a base's coordinates drops back onto the intact map exactly
where it came from. That alignment is what lets these be plain overlays with no
per-base positioning work: the sprite goes at the base actor's own location and
lands on the ruins it was cut from.

The edges are feathered on an ellipse rather than cut square, because the
destroyed render also scatters fires and debris across ground that is NOT
ruined in the intact version. A hard rectangle would show a visible seam where
that extra detail stops; a fade blends the ruined platform into the intact
terrain still drawn underneath it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptk_png  # noqa: E402

SRC = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics\destoyed map spots.png"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "ArtSource", "Map", "DestroyedBases")

TEX_W, TEX_H = 1672, 941

# Same normalised coordinates the battlefield and the level builder use.
BASES = {
    "Aegis":    (0.368, 0.225),
    "Wraith":   (0.632, 0.222),
    "Reaver":   (0.283, 0.560),
    "Ravager":  (0.718, 0.558),
    "Sentinel": (0.500, 0.795),
}

# Half-extents of the crop, in source pixels.
#
# A base platform is about 230x175 px, so half of it is 115x88. The crop is
# kept only a little larger than that ON PURPOSE.
#
# The temptation is to take a wide margin and fade gently across it, but the
# destroyed render is not merely the intact one with a broken platform - its
# whole surrounding terrain is darker and strewn with extra fires and debris.
# Any overlay boundary drawn over that terrain shows as a ring, and a WIDER
# crop makes the ring bigger rather than softer. Cropping tight keeps the
# transition on the platform's own stone rim, where the two renders agree.
HALF_W, HALF_H = 138, 112

# Fraction of the ellipse that stays fully opaque before the fade begins.
# 0.80 of 138 is 110 px, just inside the platform's 115 px half-width, so the
# ruins are carried at full strength and the short fade lands on the rim.
SOLID_FRACTION = 0.80


def feathered_crop(image, cx, cy):
    """Elliptical crop centred on (cx, cy), alpha fading to zero at the edge."""
    x0 = max(cx - HALF_W, 0)
    y0 = max(cy - HALF_H, 0)
    x1 = min(cx + HALF_W, image.width)
    y1 = min(cy + HALF_H, image.height)

    out = ptk_png.Image(x1 - x0, y1 - y0)
    for y in range(out.height):
        # Normalised offset from the ellipse centre, -1..1 on each axis.
        ny = (y0 + y - cy) / float(HALF_H)
        for x in range(out.width):
            nx = (x0 + x - cx) / float(HALF_W)
            radius = (nx * nx + ny * ny) ** 0.5

            if radius >= 1.0:
                continue
            if radius <= SOLID_FRACTION:
                alpha = 1.0
            else:
                # Smoothstep across the rim reads better than a linear ramp -
                # a straight fade leaves a faint visible ring at both ends.
                t = (radius - SOLID_FRACTION) / (1.0 - SOLID_FRACTION)
                alpha = 1.0 - (t * t * (3.0 - 2.0 * t))

            r, g, b, a = image.get(x0 + x, y0 + y)
            out.set(x, y, (r, g, b, int(round(a * alpha))))
    return out


def main():
    if not os.path.isfile(SRC):
        print("ERROR: source not found:", SRC)
        return 1

    source = ptk_png.read_png(SRC)
    if source.width != TEX_W or source.height != TEX_H:
        print("ERROR: expected {0}x{1}, got {2}x{3} - the crops would be misplaced"
              .format(TEX_W, TEX_H, source.width, source.height))
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    print("source {0}x{1}".format(source.width, source.height))

    for name, (u, v) in sorted(BASES.items()):
        cx = int(round(u * TEX_W))
        cy = int(round(v * TEX_H))
        crop = feathered_crop(source, cx, cy)
        path = os.path.join(OUT_DIR, "Destroyed_{0}.png".format(name))
        ptk_png.write_png(path, crop)
        print("  {0:<10s} centre ({1:4d},{2:4d})  ->  {3}x{4}  {5}"
              .format(name, cx, cy, crop.width, crop.height,
                      os.path.basename(path)))

    print("done -", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
