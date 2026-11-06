"""Render a PNG preview of a tire from add-in settings, without Fusion.

Usage:
    python tools/preview.py [key=value ...] [--out tire.png] [--size 800]
                            [--tread] [--cutter]

Examples:
    python tools/preview.py pattern=gothic g_count=12 g_interleave=true
    python tools/preview.py pattern=honey h_angle=-20 outer_lines=0 --tread
    python tools/preview.py a_peg_n=6 a_dt_n=6 a_dt_phase=30 --cutter

Settings are the add-in's DEFAULTS keys (see AirlessTireGenerator.py);
pattern accepts gothic / curved / honey. The preview draws spoke centrelines
at their real thickness, so it shows layout and clearances, not fillets.
Shading: rims dark grey, structure black, the first copy of a repeated
element darker, cutter outline light grey (--cutter), OD trim line when there
is no tread rim.
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
    """Greyscale canvas mapping model mm to pixels, with optional clip radius."""

    def __init__(self, size, cx, cy, span):
        self.n = size
        self.img = bytearray(b'\xff' * size * size)
        self.sc = size / span
        self.cx, self.cy = cx, cy
        self.clip = None

    def px(self, x, y):
        return (self.n / 2 + (x - self.cx) * self.sc, self.n / 2 - (y - self.cy) * self.sc)

    def model(self, i, j):
        return ((i - self.n / 2) / self.sc + self.cx, (self.n / 2 - j) / self.sc + self.cy)

    def put(self, i, j, v):
        if 0 <= i < self.n and 0 <= j < self.n:
            if self.clip is not None:
                x, y = self.model(i, j)
                if math.hypot(x, y) > self.clip:
                    return
            self.img[j * self.n + i] = v

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
        for j in range(self.n):
            for i in range(self.n):
                x, y = self.model(i, j)
                if r_in <= math.hypot(x, y) <= r_out:
                    self.put(i, j, v)

    def circle_line(self, r, v):
        steps = max(360, int(2 * math.pi * r * self.sc))
        for k in range(steps):
            a = 2 * math.pi * k / steps
            i, j = self.px(r * math.cos(a), r * math.sin(a))
            self.put(int(i), int(j), v)

    def polygon(self, pts, v):
        js = [self.px(x, y)[1] for x, y in pts]
        for j in range(max(0, int(min(js))), min(self.n, int(max(js)) + 2)):
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


def render(mod, p, size=800, tread=False, cutter=False):
    g = mod.compute(p)
    r0, r1, r2, r3 = g['radii']
    t = g['t']
    open_tread = p['outer_lines'] <= 0
    if tread:
        span = (r3 - r1) * 1.6 + 4
        cv = Canvas(size, 0, (r1 + r3) / 2.0, span)
    else:
        cv = Canvas(size, 0, 0, 2 * r3 * 1.06)

    # rims
    cv.ring(r0, r1, 90)
    if not open_tread:
        cv.ring(r2, r3, 90)

    # structure, clipped at the OD when there is no tread rim
    cv.clip = r3 if open_tread else None
    for leg in g['legs']:
        cv.polyline(leg['samples'], t, 0 if leg.get('seed') else 40)
    cv.clip = None
    if open_tread:
        cv.circle_line(r3, 170)

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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('overrides', nargs='*', help='setting overrides as key=value')
    ap.add_argument('--out', default='tire_preview.png')
    ap.add_argument('--size', type=int, default=800)
    ap.add_argument('--tread', action='store_true', help='zoom on a section of the tread at the top')
    ap.add_argument('--cutter', action='store_true', help='also draw the hub cutter outline')
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
    cv, g = render(mod, p, a.size, a.tread, a.cutter)
    write_png(a.out, cv.img, cv.n, cv.n)
    print('Wrote %s (%s)' % (a.out, g['label']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
