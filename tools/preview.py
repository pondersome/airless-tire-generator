"""Render a PNG preview of a tire from add-in settings, without Fusion.

Usage:
    python tools/preview.py [key=value ...] [--out tire.png] [--size 800]
                            [--tread] [--cutter] [--z Z | --side]

Examples:
    python tools/preview.py pattern=gothic g_count=12 g_interleave=true
    python tools/preview.py pattern=honey h_angle=-20 outer_lines=0 --tread
    python tools/preview.py a_peg_n=6 a_dt_n=6 a_dt_phase=30 --cutter
    python tools/preview.py profile=grooved width=40 pg_contact_w=30 --side
    python tools/preview.py profile=crowned --tread --z deep

Settings are the add-in's DEFAULTS keys (see AirlessTireGenerator.py);
pattern accepts gothic / curved / honey, profile flat / crowned / grooved.
The preview draws spoke centrelines at their real thickness, so it shows
layout and clearances, not fillets. Shading: rims dark grey, structure black,
the first copy of a repeated element darker, cutter outline light grey
(--cutter), OD trim line when there is no tread rim.

With a tread profile, the top view shows one slice across the width: --z is
its height in mm from the bottom face ('deep' = where the structure is
squeezed most); without --z it shows the pattern as designed, at the tire's
largest diameter (a grooved tire's lands), which is drawn as a faint circle
on squeezed slices. --side draws the half-section across
the width instead (axis below): rims dark grey, the profile on top, and thin
lines showing where evenly spaced radii of the design end up, so you can see
the squeeze fade from the tread down to the inner rim.
"""
import argparse
import math
import struct
import sys
import zlib

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_addin, settings  # noqa: E402


def write_png(path, img, w, h):
    raw = b''.join(b'\x00' + bytes(img[j * w:(j + 1) * w]) for j in range(h))

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw))
                + chunk(b'IEND', b''))


class Canvas:
    """Greyscale canvas mapping model mm to pixels, with optional clip radius.
    size is the width in pixels (and the height unless given); span is the
    model width it shows, centred on (cx, cy)."""

    def __init__(self, size, cx, cy, span, height=None):
        self.w = size
        self.h = height or size
        self.img = bytearray(b'\xff' * self.w * self.h)
        self.sc = size / span
        self.cx, self.cy = cx, cy
        self.clip = None

    def px(self, x, y):
        return (self.w / 2 + (x - self.cx) * self.sc, self.h / 2 - (y - self.cy) * self.sc)

    def model(self, i, j):
        return ((i - self.w / 2) / self.sc + self.cx, (self.h / 2 - j) / self.sc + self.cy)

    def put(self, i, j, v):
        if 0 <= i < self.w and 0 <= j < self.h:
            if self.clip is not None:
                x, y = self.model(i, j)
                if math.hypot(x, y) > self.clip:
                    return
            self.img[j * self.w + i] = v

    def disc(self, x, y, r, v):
        ci, cj = self.px(x, y)
        R = max(r * self.sc, 0.6)
        for j in range(int(cj - R) - 1, int(cj + R) + 2):
            for i in range(int(ci - R) - 1, int(ci + R) + 2):
                if (i - ci) ** 2 + (j - cj) ** 2 <= R * R:
                    self.put(i, j, v)

    def polyline(self, pts, width, v):
        step = max(width / 3.0, 0.5 / self.sc)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) / step))
            for u in range(n + 1):
                self.disc(ax + (bx - ax) * u / n, ay + (by - ay) * u / n, width / 2.0, v)

    def ring(self, r_in, r_out, v):
        for j in range(self.h):
            for i in range(self.w):
                x, y = self.model(i, j)
                if r_in <= math.hypot(x, y) <= r_out:
                    self.put(i, j, v)

    def fill_between(self, x0, x1, lo, hi, v):
        """Fill between y = lo(x) and y = hi(x) for x0 <= x <= x1."""
        for i in range(max(0, int(self.px(x0, 0)[0])), min(self.w, int(self.px(x1, 0)[0]) + 1)):
            x = self.model(i + 0.5, 0)[0]
            if not x0 <= x <= x1:
                continue
            j_top, j_bot = self.px(x, hi(x))[1], self.px(x, lo(x))[1]
            for j in range(max(0, int(j_top)), min(self.h, int(j_bot) + 1)):
                self.put(i, j, v)

    def circle_line(self, r, v):
        steps = max(360, int(2 * math.pi * r * self.sc))
        for k in range(steps):
            a = 2 * math.pi * k / steps
            i, j = self.px(r * math.cos(a), r * math.sin(a))
            self.put(int(i), int(j), v)

    def polygon(self, pts, v):
        js = [self.px(x, y)[1] for x, y in pts]
        for j in range(max(0, int(min(js))), min(self.h, int(max(js)) + 2)):
            y = self.model(0, j)[1]
            xs = []
            for k in range(len(pts)):
                (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % len(pts)]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                ia, ib = self.px(a, y)[0], self.px(b, y)[0]
                for i in range(int(ia), int(ib) + 1):
                    self.put(i, j, v)

    def filled_circle(self, x, y, r, v):
        self.disc(x, y, r, v)


def render(mod, p, size=800, tread=False, cutter=False, z=None):
    """Top view. With a tread profile and a height z, the slice at z: the
    structure squeezed for the surface there, rims and members at full
    thickness."""
    g = mod.compute(p)
    r0, r1, r2, r3 = g['radii']
    t = g['t']
    to = p['outer_lines'] * p['line_w']
    open_tread = to <= 0
    shape = g.get('profile')
    d = shape.drop_z(z) if (shape is not None and z is not None) else 0.0
    f, _ = mod.radial_map(g['radii'], to, d)
    R = r3 - d            # tread surface at this height
    if tread:
        span = (r3 - r1) * 1.6 + 4
        cv = Canvas(size, 0, (r1 + r3) / 2.0, span)
    else:
        cv = Canvas(size, 0, 0, 2 * r3 * 1.06)

    # rims
    cv.ring(r0, r1, 90)
    if not open_tread:
        cv.ring(R - to, R, 90)

    # structure, clipped at the tread surface when there is no tread rim
    cv.clip = R if open_tread else None
    for leg in g['legs']:
        cv.polyline([mod.map_point(f, q) for q in leg['samples']], t, 0 if leg.get('seed') else 40)
    cv.clip = None
    if open_tread:
        cv.circle_line(R, 170)
    if d > 0:
        cv.circle_line(r3, 215)   # the largest diameter, for reference

    anchors = g.get('anchors', [])

    def copies():
        for sp in anchors:
            for k in range(sp['n']):
                yield sp, sp['phase'] + k * 2 * math.pi / sp['n']

    # hub cutter first, shown only inside the bore where it actually cuts the hub
    if cutter and anchors:
        clear = max(p['a_clear'], 0.05)
        cv.clip = r0
        for sp, ang in copies():
            cv.polygon(mod.offset_polygon(mod.to_xy(sp['local'], ang), clear), 200)
            if sp['kind'] == 'peg':
                cx, cy = mod.polar(sp['rc'], ang)
                cv.filled_circle(cx, cy, sp['dia'] / 2.0 + clear, 200)
        cv.ring(r0 - clear, r0, 200)   # the ring that ties the cutter pieces together
        cv.clip = None

    # anchors on top
    for sp, ang in copies():
        cv.polygon(mod.to_xy(sp['local'], ang), 0)
        if sp['kind'] == 'peg':
            cx, cy = mod.polar(sp['rc'], ang)
            cv.filled_circle(cx, cy, sp['dia'] / 2.0, 0)
            if sp['id'] > 0:
                cv.filled_circle(cx, cy, sp['id'] / 2.0, 255)
    return cv, g


def render_side(mod, p, size=800):
    """Half-section across the width (z to the right, radius up): how the
    profile squeezes the structure at every height."""
    g = mod.compute(p)
    r0, r1, r2, r3 = g['radii']
    W = p['width']
    to = p['outer_lines'] * p['line_w']
    shape = g.get('profile')

    def drop(z):
        return shape.drop_z(z) if shape is not None else 0.0

    def R(z):
        return r3 - drop(z)

    span = W + 4.0
    height = int(size * (r3 - r0 + 4.0) / span)
    cv = Canvas(size, W / 2.0, (r0 + r3) / 2.0 + 0.5, span, height)
    zs = [W * i / 400.0 for i in range(401)]

    if isinstance(shape, mod.GrooveProfile):      # the ball, seated in the groove
        bc = r3 - shape.depth + shape.Rg
        arc = [math.radians(-50 + 0.25 * i) for i in range(401)]
        cv.polyline([(W / 2.0 + shape.Rg * math.sin(a), bc - shape.Rg * math.cos(a)) for a in arc], 0.06, 190)
    cv.polyline([(-1.5, r3), (W + 1.5, r3)], 0.05, 200)          # largest diameter
    cv.fill_between(0, W, lambda z: r0, lambda z: r1, 90)          # inner rim (never moves)
    if to > 0:
        cv.fill_between(0, W, lambda z: R(z) - to, R, 90)           # tread rim follows the surface
    else:
        cv.polyline([(z, R(z)) for z in zs], 0.1, 0)
    top = r2 if to > 0 else r3
    for i in range(1, 8):                                          # evenly spaced design radii, squeezed
        rb = r1 + (top - r1) * i / 8.0
        cv.polyline([(z, mod.radial_map(g['radii'], to, drop(z))[0](rb)) for z in zs], 0.06, 0)
    for z in (0.0, W):                                             # the faces
        cv.polyline([(z, r1), (z, R(z))], 0.05, 160)
    return cv, g


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('overrides', nargs='*', help='setting overrides as key=value')
    ap.add_argument('--out', default='tire_preview.png')
    ap.add_argument('--size', type=int, default=800)
    ap.add_argument('--tread', action='store_true', help='zoom on a section of the tread at the top')
    ap.add_argument('--cutter', action='store_true', help='also draw the hub cutter outline')
    ap.add_argument('--z', default=None,
                    help="with a tread profile: slice height in mm from the bottom face, or 'deep'")
    ap.add_argument('--side', action='store_true', help='draw the half-section across the width instead')
    a = ap.parse_args(argv)

    mod = load_addin()
    p = settings(mod, a.overrides)
    err, warns = mod.assess(p)
    print(mod.summary(p))
    for w in warns:
        print(w)
    if err:
        print('PROBLEM: ' + err)
        return 1
    if a.side:
        cv, g = render_side(mod, p, a.size)
    else:
        z = None
        if a.z is not None:
            shape = mod.tread_profile(p)
            if shape is None:
                print('Note: --z has no effect on a flat tire.')
            else:
                z = shape.deep_z if a.z == 'deep' else float(a.z)
                if not 0 <= z <= p['width']:
                    print('PROBLEM: --z must be between 0 and the width (%g mm).' % p['width'])
                    return 1
                f, k = mod.radial_map(mod.ring_radii(mod.build_params(p)), p['outer_lines'] * p['line_w'],
                                      shape.drop_z(z))
                print('Slice at z=%.2f mm: surface %.2f mm in from the largest diameter, spoke zone squeezed to %.0f%%'
                      % (z, shape.drop_z(z), 100 * k))
        cv, g = render(mod, p, a.size, a.tread, a.cutter, z)
    write_png(a.out, cv.img, cv.w, cv.h)
    print('Wrote %s (%s)' % (a.out, g['label']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
