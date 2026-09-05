"""
Protect the King - 2D
Dependency-free PNG reader/writer for the art pipeline.

Neither Pillow nor numpy is available on this machine, and installing packages
system-wide is not something this pipeline should do silently. Everything here
uses only the Python standard library.

Working at the byte level is also a feature rather than a workaround: every
operation in the Ravager pipeline has to be exact-pixel, with no resampling,
no interpolation and no anti-aliasing. A decoder we control cannot silently
smooth anything.

Supports: 8-bit RGB (colour type 2) and 8-bit RGBA (colour type 6),
non-interlaced - which covers every source image in this project.
"""

import struct
import zlib


class Image:
    """8-bit RGBA raster held as a flat bytearray, 4 bytes per pixel."""

    __slots__ = ("width", "height", "px")

    def __init__(self, width, height, px=None):
        self.width = width
        self.height = height
        self.px = px if px is not None else bytearray(width * height * 4)

    def index(self, x, y):
        return (y * self.width + x) * 4

    def get(self, x, y):
        i = (y * self.width + x) * 4
        return (self.px[i], self.px[i + 1], self.px[i + 2], self.px[i + 3])

    def set(self, x, y, rgba):
        i = (y * self.width + x) * 4
        self.px[i] = rgba[0]
        self.px[i + 1] = rgba[1]
        self.px[i + 2] = rgba[2]
        self.px[i + 3] = rgba[3]

    def crop(self, x0, y0, x1, y1):
        """Exact pixel copy of the half-open box [x0,x1) x [y0,y1)."""
        w = x1 - x0
        h = y1 - y0
        out = Image(w, h)
        src = self.px
        dst = out.px
        sw = self.width
        for row in range(h):
            s = ((y0 + row) * sw + x0) * 4
            d = row * w * 4
            dst[d:d + w * 4] = src[s:s + w * 4]
        return out

    def paste(self, other, x0, y0):
        """Copies `other` in at (x0, y0), overwriting. No blending."""
        src = other.px
        dst = self.px
        for row in range(other.height):
            ty = y0 + row
            if ty < 0 or ty >= self.height:
                continue
            s = row * other.width * 4
            d = (ty * self.width + x0) * 4
            dst[d:d + other.width * 4] = src[s:s + other.width * 4]

    def opaque_bounds(self, alpha_threshold=0):
        """(x0, y0, x1, y1) half-open box of pixels with alpha > threshold."""
        w, h, px = self.width, self.height, self.px
        min_x, min_y, max_x, max_y = w, h, -1, -1
        for y in range(h):
            base = y * w * 4
            for x in range(w):
                if px[base + x * 4 + 3] > alpha_threshold:
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
        if max_x < 0:
            return None
        return (min_x, min_y, max_x + 1, max_y + 1)


def _paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path):
    """Decodes an 8-bit RGB/RGBA non-interlaced PNG into an Image (RGBA)."""
    with open(path, "rb") as handle:
        data = handle.read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG: " + path)

    pos = 8
    width = height = None
    bit_depth = colour_type = interlace = None
    idat = bytearray()

    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length  # length + tag + body + crc

        if tag == b"IHDR":
            (width, height, bit_depth, colour_type,
             _compression, _filter, interlace) = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break

    if bit_depth != 8:
        raise ValueError("only 8-bit PNGs are supported (got {0})".format(bit_depth))
    if interlace:
        raise ValueError("interlaced PNGs are not supported")
    if colour_type == 2:
        channels = 3
    elif colour_type == 6:
        channels = 4
    else:
        raise ValueError("unsupported colour type {0}".format(colour_type))

    raw = zlib.decompress(bytes(idat))

    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0

    for y in range(height):
        filter_type = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride

        if filter_type == 0:
            pass
        elif filter_type == 1:  # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                if i >= channels:
                    left = line[i - channels]
                    upper_left = prev[i - channels]
                else:
                    left = 0
                    upper_left = 0
                line[i] = (line[i] + _paeth(left, prev[i], upper_left)) & 0xFF
        else:
            raise ValueError("bad PNG filter {0} on row {1}".format(filter_type, y))

        out[y * stride:(y + 1) * stride] = line
        prev = line

    image = Image(width, height)
    if channels == 4:
        image.px = out
    else:
        # Expand RGB to RGBA with alpha 255.
        rgba = bytearray(width * height * 4)
        rgba[3::4] = b"\xff" * (width * height)
        for c in range(3):
            rgba[c::4] = out[c::3]
        image.px = rgba

    return image


def write_png(path, image, compress_level=9):
    """Writes an Image as an 8-bit RGBA PNG (filter 0, no interlace)."""
    width, height = image.width, image.height
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: None
        raw += image.px[y * stride:(y + 1) * stride]

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), compress_level))
            + chunk(b"IEND", b""))

    with open(path, "wb") as handle:
        handle.write(blob)
