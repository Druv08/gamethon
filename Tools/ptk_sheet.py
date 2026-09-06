"""
Protect the King - 2D
Reusable machinery for slicing a generated animation sheet into Unreal-ready
frames.

Ravager's extraction proved out four corrections that every delivered sheet so
far has needed, and there are nine more characters to come. This module holds
the parts that are genuinely character-independent; a character script supplies
only its own masks, scale metric and sheet list.

    Tools/ExtractSwarmNodeAnimations.py    - first consumer
    Tools/ExtractRavagerAnimations.py      - predecessor, kept as-is because its
                                             output is already committed and
                                             verified frame-by-frame

WHAT IS GENERIC (here)
----------------------
  * cell grid over an N-column x M-row sheet, including non-integer pitch
  * backward-mapped area-average resampling straight from sheet to final canvas
  * cross-cell sampling with a fence, for art that overruns its cell
  * connected-component cleanup, to drop a neighbour's spill
  * hard 0/255 alpha
  * canvas-fit measurement and clipping detection

WHAT IS CHARACTER-SPECIFIC (the caller)
---------------------------------------
  * which pixels are "body" vs "transient effect"
  * what rigid feature sets the scale (Ravager: helmet-to-feet; Swarm Node: the
    central eye, because a crawling blob has no standing height)
  * where the ground anchor is
  * how to prove a sheet really holds the direction its row order claims

THE FOUR CORRECTIONS
--------------------
1. Sheets delivered together are NOT always at the same scale. Measure a rigid
   feature per sheet and normalise, or the character changes size mid-fight.
2. Walk sheets drift across the cell; attack sheets lunge and return. Drift must
   go, lunge must stay. The test is whether frame 8 comes back to frame 1.
3. Effects and weapons overrun the source cell. Sampling has to be allowed out
   of the cell, fenced short of the neighbouring character.
4. A neighbour's effect spills in anyway. Keep only what is connected to this
   frame's own silhouette.
"""

from collections import deque

import ptk_png


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------
class Grid(object):
    """Cell geometry over a sheet. Pitch is float; column edges are rounded."""

    def __init__(self, sheet, columns, rows):
        self.sheet = sheet
        self.columns = columns
        self.rows = rows
        self.cell_w = sheet.width / float(columns)
        self.cell_h = sheet.height // rows

    def origin(self, col, row):
        return int(round(col * self.cell_w)), row * self.cell_h

    def cell(self, col, row):
        x0, y0 = self.origin(col, row)
        x1 = int(round((col + 1) * self.cell_w))
        return self.sheet.crop(x0, y0, x1, y0 + self.cell_h)


# ---------------------------------------------------------------------------
# Masks
# ---------------------------------------------------------------------------
def build_masks(img, alpha_threshold, is_effect):
    """
    (body, full, w, h) as flat 0/1 bytearrays.

    `body` excludes transient effect pixels so that geometry - anchor, scale,
    bounds - is measured off the creature and never off a beam or a glow that
    only exists for two frames.
    """
    w, h, px = img.width, img.height, img.px
    body = bytearray(w * h)
    full = bytearray(w * h)
    for y in range(h):
        base = y * w * 4
        row = y * w
        for x in range(w):
            i = base + x * 4
            if px[i + 3] < alpha_threshold:
                continue
            full[row + x] = 1
            if not is_effect(px[i], px[i + 1], px[i + 2]):
                body[row + x] = 1
    return body, full, w, h


def mask_bounds(mask, w, h):
    xs = [x for x in range(w) if any(mask[y * w + x] for y in range(h))]
    if not xs:
        return None
    ys = [y for y in range(h) if any(mask[y * w + x] for x in range(w))]
    return (xs[0], xs[-1], ys[0], ys[-1])


def row_profile(mask, w, h):
    return [sum(mask[y * w:(y + 1) * w]) for y in range(h)]


def ground_anchor(body, w, h, min_run=None):
    """
    (bottom_row, centre_x) - the ground contact and horizontal centre.

    `bottom` ignores rows carrying only a stray pixel or two, so a single
    speck of noise cannot drag the anchor down.
    """
    threshold = min_run if min_run else max(2, int(round(0.030 * w)))
    rows = row_profile(body, w, h)
    filled = [y for y in range(h) if rows[y] >= threshold]
    if not filled:
        return None
    sx = sn = 0
    for y in range(h):
        base = y * w
        for x in range(w):
            if body[base + x]:
                sx += x
                sn += 1
    if not sn:
        return None
    return dict(bottom=filled[-1], top=filled[0], centre=sx / float(sn),
                height=filled[-1] - filled[0] + 1, area=sn)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
def render_frame(sheet, origin_x, origin_y, cell_w, cell_h,
                 anchor_x, anchor_y, scale, canvas, pivot, fence_fraction=0.66,
                 x_bounds=None):
    """
    Renders one finished frame by mapping every destination pixel back into the
    sheet and area-averaging the source box it covers.

    Working backwards means the anchor lands on the pivot to sub-pixel accuracy
    with no intermediate resample, so rounding can never re-introduce the jitter
    this pipeline exists to remove.

    Sampling may leave the cell sideways, because effects do, but is fenced to
    `fence_fraction` of a cell either side of the anchor - past anything of
    ours, short of the neighbour's body. It never leaves the row: no sheet so
    far needs more vertical reach than the cell already provides, and allowing
    it would pull in the row above.

    `x_bounds` is an optional hard (lo, hi) clamp in sheet coordinates, for
    sheets drawn so tightly that the fence still reaches a neighbour. Bounding
    to the cell makes foreign content impossible rather than merely unlikely,
    which is what lets a caller then reason about the leftovers by colour -
    see Wraith, whose bow detaches on one frame and whose released arrow has to
    go. Default None keeps the original behaviour byte-for-byte.

    Colour is averaged premultiplied, so transparent background can never bleed
    a dark fringe into the silhouette edge.
    """
    out_w, out_h = canvas
    step = 1.0 / scale
    fence = cell_w * fence_fraction
    abs_x = origin_x + anchor_x
    abs_y = origin_y + anchor_y

    x_lo = max(0, int(abs_x - fence))
    x_hi = min(sheet.width, int(abs_x + fence) + 1)
    if x_bounds is not None:
        x_lo = max(x_lo, x_bounds[0])
        x_hi = min(x_hi, x_bounds[1])
    y_lo = origin_y
    y_hi = min(sheet.height, origin_y + cell_h)

    out = ptk_png.Image(out_w, out_h)
    src = sheet.px
    sw = sheet.width

    for oy in range(out_h):
        sy0 = abs_y + (oy - pivot[1]) * step
        iy0 = max(y_lo, int(sy0))
        iy1 = min(y_hi, int(sy0 + step) + 1)
        if iy0 >= iy1:
            continue
        for ox in range(out_w):
            sx0 = abs_x + (ox - pivot[0]) * step
            ix0 = max(x_lo, int(sx0))
            ix1 = min(x_hi, int(sx0 + step) + 1)
            if ix0 >= ix1:
                continue
            r = g = b = a = 0
            n = 0
            for yy in range(iy0, iy1):
                base = yy * sw * 4
                for xx in range(ix0, ix1):
                    i = base + xx * 4
                    al = src[i + 3]
                    r += src[i] * al
                    g += src[i + 1] * al
                    b += src[i + 2] * al
                    a += al
                    n += 1
            if not n or not a:
                continue
            out.set(ox, oy, (r // a, g // a, b // a, a // n))
    return out


def harden_alpha(img, threshold=128):
    """Resolves the anti-aliased rim to a hard silhouette.

    The runtime material is masked, which thresholds anyway; cutting here means
    what ships is exactly what renders.
    """
    px = img.px
    for i in range(3, len(px), 4):
        px[i] = 255 if px[i] >= threshold else 0


def keep_connected(img, seed_xy):
    """
    Drops everything not joined to the character. Returns pixels discarded.

    This is what removes a neighbouring frame's effect after sampling was
    allowed across the cell boundary.
    """
    w, h, px = img.width, img.height, img.px
    solid = [px[i * 4 + 3] > 0 for i in range(w * h)]
    total = sum(1 for v in solid if v)
    if not total:
        return 0

    sx, sy = seed_xy
    if not (0 <= sx < w and 0 <= sy < h and solid[sy * w + sx]):
        found = None
        for dy in range(h):
            for cand in (sy - dy, sy + dy):
                if 0 <= cand < h and solid[cand * w + sx]:
                    found = (sx, cand)
                    break
            if found:
                break
        if not found:
            return 0
        sx, sy = found

    seen = bytearray(w * h)
    queue = deque([(sx, sy)])
    seen[sy * w + sx] = 1
    kept = 0
    while queue:
        x, y = queue.popleft()
        kept += 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                k = ny * w + nx
                if solid[k] and not seen[k]:
                    seen[k] = 1
                    queue.append((nx, ny))

    for k in range(w * h):
        if solid[k] and not seen[k]:
            px[k * 4 + 3] = 0
    return total - kept


def clean_islands(img, seed_xy, is_effect, max_gap=8, drop_effect=False):
    """
    Removes strays without removing the character's own detached gear.
    Returns pixels discarded.

    keep_connected() is the blunt version of this: it deletes everything not
    joined to the seed. That is right when the only possible stray is a
    neighbour's spill, but wrong the moment a character's own art legitimately
    separates - Wraith's bow parts from his arm by a pixel on the frame after
    release, and a strict flood erases the bow.

    Two questions are asked of every island that does not hold the seed:

      how far is it?   Sheets whose frames overlap leave a slice of the
                       NEIGHBOUR inside this cell, where clamping the sampler
                       cannot reach it. Anything more than `max_gap` from the
                       character is not his.

      what colour?     With `drop_effect`, a detached BRIGHT island is a fired
                       projectile that the game is about to spawn for real and
                       must not also be drawn; a detached DARK island is his
                       own gear and stays. Off by default, so a death dissolve
                       keeps its sparks.

    Distance is true pixel distance, not bounding-box distance: a drawn bow
    stretches the character's box far to one side, and a box test would then
    call the neighbour's cape "close" because it happens to sit beside the bow.
    It is measured by growing a front outwards from the character for `max_gap`
    steps and seeing what it reaches.
    """
    w, h, px = img.width, img.height, img.px
    solid = [px[i * 4 + 3] > 0 for i in range(w * h)]
    if not any(solid):
        return 0

    sx, sy = seed_xy
    if not (0 <= sx < w and 0 <= sy < h and solid[sy * w + sx]):
        found = None
        for dy in range(h):
            for cand in (sy - dy, sy + dy):
                if 0 <= cand < h and solid[cand * w + sx]:
                    found = (sx, cand)
                    break
            if found:
                break
        if not found:
            return 0
        sx, sy = found

    seen = bytearray(w * h)
    islands = []
    seed_box = None
    seed_set = set()
    for start in range(w * h):
        if not solid[start] or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        island = []
        holds_seed = False
        while queue:
            k = queue.popleft()
            island.append(k)
            if k == sy * w + sx:
                holds_seed = True
            x, y = k % w, k // w
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if solid[j] and not seen[j]:
                        seen[j] = 1
                        queue.append(j)
        xs = [k % w for k in island]
        ys = [k // w for k in island]
        box = (min(xs), max(xs), min(ys), max(ys))
        if holds_seed:
            seed_box = box
            seed_set = set(island)
        else:
            islands.append((island, box))

    if seed_box is None:
        return 0

    # Grow a front out of the character for max_gap steps, through anything.
    near = bytearray(w * h)
    front = [k for k in range(w * h) if seen[k] and solid[k] and k in seed_set]
    for k in front:
        near[k] = 1
    for _ in range(max_gap):
        nxt = []
        for k in front:
            x, y = k % w, k // w
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if not near[j]:
                        near[j] = 1
                        nxt.append(j)
        front = nxt

    dropped = 0
    for island, box in islands:
        remove = not any(near[k] for k in island)
        if not remove and drop_effect:
            effect = sum(1 for k in island
                         if is_effect(px[k * 4], px[k * 4 + 1], px[k * 4 + 2]))
            remove = effect >= len(island) * 0.5
        if remove:
            for k in island:
                px[k * 4 + 3] = 0
            dropped += len(island)
    return dropped


def border_contact(img):
    """Opaque pixels on the canvas edge - i.e. art that got clipped."""
    w, h, px = img.width, img.height, img.px
    n = 0
    for x in range(w):
        n += 1 if px[x * 4 + 3] else 0
        n += 1 if px[((h - 1) * w + x) * 4 + 3] else 0
    for y in range(h):
        n += 1 if px[(y * w) * 4 + 3] else 0
        n += 1 if px[(y * w + w - 1) * 4 + 3] else 0
    return n


# ---------------------------------------------------------------------------
# Anchoring policy
# ---------------------------------------------------------------------------
def anchors_for_row(metrics_row, hold_still):
    """
    Per-frame anchoring for cycles that play in place, one fixed anchor for
    sequences that deliberately move.

    A walk cycle must not travel: the generator's drift across the cell would
    read as the sprite sliding sideways and snapping home at the loop point, so
    every frame is pinned to its own anchor.

    An attack lunges out and comes back - frame 8 returns to frame 1 - so the
    row gets ONE anchor, taken from those rest frames. The lunge survives, and
    the rest pose still lands exactly on the pivot, which is what stops the
    character jumping the moment the attack starts.
    """
    if hold_still:
        return [(m["centre"], m["bottom"]) for m in metrics_row]
    n = len(metrics_row)
    centre = (metrics_row[0]["centre"] + metrics_row[n - 1]["centre"]) / 2.0
    bottom = sorted(m["bottom"] for m in metrics_row)[n // 2]
    return [(centre, bottom)] * n


def required_extent(metrics_row, anchors_row, bounds_row, scale):
    """How far the art reaches from the anchor, in finished-frame pixels."""
    left = right = up = down = 0.0
    for m, (ax, ay), bb in zip(metrics_row, anchors_row, bounds_row):
        if bb is None:
            continue
        left = max(left, (ax - bb[0]) * scale)
        right = max(right, (bb[1] - ax) * scale)
        up = max(up, (ay - bb[2]) * scale)
        down = max(down, (bb[3] - ay) * scale)
    return left, right, up, down
