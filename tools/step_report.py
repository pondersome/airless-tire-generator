"""Summarise what makes an exported STEP file big.

Usage:
    python tools/step_report.py FILE.step

Prints the entity types that take the most space, the control-point grids
of the B-spline surfaces, and the B-spline curves by size and by direction:
lying across the tire at one height, running along its axis (Z), or
oblique. Written to find the spline edges that bloated profiled-tire
exports (a few thousand dense edge curves were most of a 47 MB file), but it
works on any STEP file. Standard library only; the file is only read.
"""
import collections
import math
import re
import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 2
    path = args[0]
    with open(path, 'r', encoding='latin-1') as fh:
        text = fh.read()
    data = text[text.find('DATA;') + 5:text.rfind('ENDSEC;')]
    count, size = collections.Counter(), collections.Counter()
    pts, curves, grids = {}, [], collections.Counter()
    for e in data.split(';'):
        e = e.strip()
        m = re.match(r'#(\d+)\s*=\s*(.*)', e, re.S)
        if not m:
            continue
        eid, body = int(m.group(1)), m.group(2)
        if body.startswith('('):      # complex entity: name it by its first few parts
            kind = 'complex(%s)' % ','.join(re.findall(r'\b([A-Z][A-Z_0-9]+)\s*\(', body)[:3])
        else:
            kind = body.split('(')[0].strip()
        count[kind] += 1
        size[kind] += len(e) + 1
        if kind == 'CARTESIAN_POINT':
            nums = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', body.split('(', 2)[2])
            pts[eid] = tuple(float(v) for v in nums[:3])
        elif 'B_SPLINE_SURFACE' in body:
            ms = re.search(r'B_SPLINE_SURFACE(?:_WITH_KNOTS)?\s*\(\s*(?:\'[^\']*\'\s*,\s*)?(\d+)\s*,\s*(\d+)\s*,'
                           r'\s*\((.*?)\)\s*\)\s*,', body, re.S)
            if ms:
                rows = re.findall(r'\(([^()]*)\)', ms.group(3))
                grids[(int(ms.group(1)), int(ms.group(2)), len(rows),
                       len(rows[0].split(',')) if rows else 0)] += 1
        elif 'B_SPLINE_CURVE' in body:
            mc = (re.search(r'B_SPLINE_CURVE\s*\(\s*(\d+)\s*,\s*\(([^)]*)\)', body)
                  or re.search(r'B_SPLINE_CURVE_WITH_KNOTS\s*\(\s*\'[^\']*\'\s*,\s*(\d+)\s*,\s*\(([^)]*)\)', body))
            if mc:
                curves.append((int(mc.group(1)), [int(x) for x in re.findall(r'#(\d+)', mc.group(2))],
                               'RATIONAL' in body))

    print('%s: %.1f MB, %d entities, %d points' % (re.split(r'[\\/]', path)[-1], len(text) / 1e6,
                                                     sum(count.values()), len(pts)))
    print('\n%-46s %9s %8s' % ('entity type (largest first)', 'count', 'MB'))
    for kind, n in size.most_common(14):
        print('%-46s %9d %8.2f' % (kind[:46], count[kind], n / 1e6))

    if grids:
        print('\nB-spline surfaces (degree u x v, control points rows x columns):')
        for (du, dv, nr, nc), n in grids.most_common(8):
            print('  %d x %d, %3d x %3d: %d surfaces' % (du, dv, nr, nc, n))

    if curves:
        in_curves = sum(len(ids) for _, ids, _ in curves)
        print('\nB-spline curves: %d, holding %d control points (%.0f%% of all points)'
              % (len(curves), in_curves, 100.0 * in_curves / max(len(pts), 1)))
        hist = collections.Counter()
        for deg, ids, rat in curves:
            n = len(ids)
            band = '<=10' if n <= 10 else '11-30' if n <= 30 else '31-100' if n <= 100 else '>100'
            hist[(deg, rat, band)] += 1
        for (deg, rat, band), n in sorted(hist.items()):
            print('  degree %d%-9s %6s control points: %5d curves' % (deg, ' rational' if rat else '', band, n))
        cls, cls_pts = collections.Counter(), collections.Counter()
        for deg, ids, rat in curves:
            P = [pts[i] for i in ids if i in pts]
            if not P:
                continue
            dz = max(p[2] for p in P) - min(p[2] for p in P)
            dxy = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in (P[0], P[-1]) for b in P)
            kind = ('lying across at one height' if dz < 0.05 else
                    'running along the axis' if dz > 2 * dxy else 'oblique')
            cls[kind] += 1
            cls_pts[kind] += len(ids)
        print('  by direction:')
        for kind, n in cls.most_common():
            print('    %-30s %5d curves, %8d control points' % (kind, n, cls_pts[kind]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
