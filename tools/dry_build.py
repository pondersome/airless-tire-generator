"""Dry-run the add-in's Fusion build outside Fusion.

Usage:
    python tools/dry_build.py [--strict-arcs] [key=value ...]

Runs build() against the recording fake of Fusion's API in fusionstub/ and
checks what it would draw:
- every sketch closes into the profiles the build expects;
- on profiled tires, each member is sketched at the heights the profile
  calls for, with its sides half a wall thickness from where the squeeze puts
  its centreline (within the straightness tolerance);
- the tread rim and tread trim sketches lie on the profile.
It catches Python errors and geometry slips in the build path before a
Fusion session. It can't tell whether Fusion's lofts, joins or fillets will
succeed: nothing is solid-modelled.

With no settings it runs a set of flat and profiled tires; with key=value
settings (as for preview.py) it dry-runs that one tire. --strict-arcs makes
the fake refuse sketch points as arc ends, to exercise the add-in's
fallback. Exits non-zero if anything fails.
"""
import math
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_addin, settings  # noqa: E402

m = load_addin()
import adsk.fusion as fake  # noqa: E402  (the fake from fusionstub/, loaded with the add-in)

CONFIGS = [
    ('flat gothic', {}),
    ('flat honeycomb, open, anchors', {'pattern': 'honey', 'outer_lines': 0, 'keep_open': True, 'a_peg_n': 6,
                                       'a_dt_n': 6, 'a_dt_phase': 30}),
    ('grooved gothic', {'profile': 'grooved'}),
    ('grooved honeycomb, open (flywheel)', {'pattern': 'honey', 'tire_od': 88, 'bore_d': 64, 'width': 40,
                                            'h_count': 48, 'h_rows': 2, 'h_lines': 1, 'outer_lines': 0,
                                            'keep_open': True, 'profile': 'grooved', 'pg_contact_w': 30,
                                            'a_peg_n': 12}),
    ('grooved full width, S spokes, alt', {'pattern': 'curved', 'c_shape': 'S-curve (two arcs)',
                                           'c_alternate': True, 'c_lean': 10, 'c_bulge': 0.2,
                                           'profile': 'grooved', 'pg_contact_w': 20}),
    ('crowned gothic', {'profile': 'crowned'}),
    ('crowned flat crown, open gothic', {'profile': 'crowned', 'pc_crown_r': 0, 'pc_shoulder_r': 6,
                                         'outer_lines': 0}),
    ('crowned single arc, honeycomb', {'pattern': 'honey', 'profile': 'crowned', 'pc_crown_w': 20,
                                       'pc_crown_r': 40}),
    ('crowned shoulders only, curved', {'pattern': 'curved', 'profile': 'crowned', 'pc_crown_w': 0,
                                        'pc_crown_r': 0, 'pc_shoulder_r': 20}),
]


class App:
    def __init__(self):
        self.activeProduct = fake.Design()


# ------------------------------------------------------------------ geometry helpers
def seg_dist(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - a[0] - u * ax, p[1] - a[1] - u * ay)


def circle3(a, b, c):
    """Centre and radius of the circle through three points."""
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    sa, sb, sc = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
    ux = (sa * (b[1] - c[1]) + sb * (c[1] - a[1]) + sc * (a[1] - b[1])) / d
    uy = (sa * (c[0] - b[0]) + sb * (a[0] - c[0]) + sc * (b[0] - a[0])) / d
    return (ux, uy), math.hypot(a[0] - ux, a[1] - uy)


def curve_samples(sk, c):
    """Points along a sketch curve, in model mm (x, y)."""
    def mm(q):
        p = sk.plane.to_model(q)
        return (p.x * 10.0, p.y * 10.0)
    if c.kind == 'line':
        a, b = mm(c.startSketchPoint.geometry), mm(c.endSketchPoint.geometry)
        return [(a[0] + (b[0] - a[0]) * i / 10.0, a[1] + (b[1] - a[1]) * i / 10.0) for i in range(11)]
    if c.kind == 'spline':
        return [mm(q) for q in c.fit]
    a, b, mid = mm(c.startSketchPoint.geometry), mm(c.endSketchPoint.geometry), mm(c.mid)
    (ux, uy), r = circle3(a, mid, b)
    t0, t1 = math.atan2(a[1] - uy, a[0] - ux), math.atan2(b[1] - uy, b[0] - ux)
    tm = math.atan2(mid[1] - uy, mid[0] - ux)
    sw = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > sw:          # the arc runs the other way round
        sw -= 2 * math.pi
    return [(ux + r * math.cos(t0 + sw * i / 10.0), uy + r * math.sin(t0 + sw * i / 10.0)) for i in range(11)]


# ------------------------------------------------------------------ checks
def check_bands(comp, p, g):
    """Section sketches: one per seed member per height the profile calls
    for, each side within tolerance of half a thickness from the squeezed
    centreline. Returns (sketch count, worst error mm, curve kinds, longest spline)."""
    shape = g['profile']
    to = p['outer_lines'] * p['line_w']
    seeds = [l for l in g['legs'] if l['seed']]
    want = []
    for i in range(len(seeds)):
        for z0, z1, curved in shape.zones():
            want += [(i, z) for z in (shape.sections(z0, z1) if curved else [z0])]
    got = [sk for sk in comp.sketches.items if sk.name.startswith('Spoke ')]
    if len(got) != len(want):
        raise AssertionError('%d section sketches, expected %d' % (len(got), len(want)))
    worst, kinds, max_fit = 0.0, {}, 0
    for sk, (i, zw) in zip(got, want):
        mt = re.match(r'Spoke (\d+) \(k(\d+) r(\d+) (\S+)\) z([\d.]+)$', sk.name)
        z = sk.plane.z * 10.0
        if not mt or int(mt.group(1)) != i or abs(z - zw) > 1e-6:
            raise AssertionError('sketch "%s" at z=%.3f, expected member %d at z=%.3f' % (sk.name, z, i, zw))
        leg = seeds[i]
        d = shape.drop_z(z)
        f, _ = m.radial_map(g['radii'], to, d if d >= 1e-9 else 0.0)
        if leg['kind'] == 'line':
            (ax, ay), (bx, by) = leg['P'], leg['Q']
            base = [(ax + (bx - ax) * j / 400.0, ay + (by - ay) * j / 400.0) for j in range(401)]
        else:
            (cx, cy), R, a1, sw = leg['C'], leg['R'], leg['a1'], leg['sweep']
            base = [(cx + R * math.cos(a1 + sw * j / 400.0), cy + R * math.sin(a1 + sw * j / 400.0))
                    for j in range(401)]
        cl = [m.map_point(f, q) for q in base]
        if len(sk.curves) != 4:
            raise AssertionError('sketch "%s" has %d curves, expected 4' % (sk.name, len(sk.curves)))
        for c in sk.curves:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
            if c.kind == 'spline':
                max_fit = max(max_fit, len(c.fit))
            pts = curve_samples(sk, c)
            span = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
            if c.kind == 'line' and abs(span - leg['t']) < 1e-6:
                continue          # an end cap, buried in a rim
            for q in pts:
                dist = min(seg_dist(q, a, b) for a, b in zip(cl, cl[1:]))
                worst = max(worst, abs(dist - leg['t'] / 2.0))
    return len(got), worst, kinds, max_fit


def check_revolves(comp, p, g):
    """Tread rim / trim sketches: every point on the tread surface, on the
    rim's inner surface, or on a closing line."""
    shape = g['profile']
    r3 = g['radii'][3]
    W = p['width']
    to = p['outer_lines'] * p['line_w']
    out = []
    for sk in comp.sketches.items:
        if sk.name not in ('Tread rim profile', 'Tread trim'):
            continue
        pts = []
        for c in sk.curves:
            pts += [c.startSketchPoint.geometry, c.endSketchPoint.geometry]
            if c.kind == 'arc':
                pts.append(c.mid)
        worst = 0.0
        for q in pts:
            mq = sk.plane.to_model(q)
            r, z = mq.x * 10.0, mq.z * 10.0
            if not -1e-6 <= z <= W + 1e-6:
                continue          # the trim's box beyond the faces
            R = r3 - shape.drop_z(z)
            dists = [abs(r - R)]
            if sk.name == 'Tread rim profile':
                dists.append(abs(r - (R - to)))
            if abs(z) < 1e-6 or abs(z - W) < 1e-6:
                dists.append(0.0 if r <= R + 1e-6 else r - R)     # a closing line at a face
            if sk.name == 'Tread trim' and r > R:
                dists.append(0.0)                                  # the trim's outer box
            worst = max(worst, min(dists))
        out.append((sk.name, len(sk.curves), sk.profiles.count, worst))
    return out


# ------------------------------------------------------------------ run
def run(label, p):
    fake.LOG[:] = []
    m._app = App()
    err, warns = m.assess(p)
    if err:
        print('%-36s refused by validation: %s' % (label, err))
        return True       # nothing to build; the dialog would disable OK
    try:
        comp, note = m.build(p)
        g = m.compute(p)
        kinds = {}
        for kind, kw in fake.LOG:
            kinds[kind] = kinds.get(kind, 0) + 1
        bodies = [b.name for b in comp.bRepBodies]
        print('%-36s %d sketches, %s; bodies: %s' % (label, comp.sketches.count,
                                                     ', '.join('%d %s' % (v, k) for k, v in sorted(kinds.items())),
                                                     ', '.join(bodies)))
        good = 'Tire' in bodies
        if g['profile'] is not None:
            n, worst, ck, max_fit = check_bands(comp, p, g)
            ok = worst < m.STRAIGHT_TOL + 0.002
            good &= ok
            print('    %d section sketches (%s%s): sides within %.4f mm of the squeezed centreline  %s'
                  % (n, ', '.join('%d %ss' % (v, k) for k, v in sorted(ck.items())),
                     ('; splines up to %d points' % max_fit) if max_fit else '', worst, 'OK' if ok else 'BAD'))
            for name, ncurves, nprof, off in check_revolves(comp, p, g):
                ok = nprof == 1 and off < 1e-6
                good &= ok
                print('    %-18s %d curves, %d profile, off the profile by %.1e mm  %s'
                      % (name, ncurves, nprof, off, 'OK' if ok else 'BAD'))
            lofts = [kw['sections'] for kind, kw in fake.LOG if kind == 'loft']
            print('    %d lofts of %s sections' % (len(lofts), '/'.join(str(s) for s in sorted(set(lofts)))))
        if not good:
            print('    BAD: see above' if 'Tire' in bodies else '    BAD: no Tire body')
        return good
    except Exception:
        print('%-36s BUILD FAILED' % label)
        traceback.print_exc()
        return False


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if '--strict-arcs' in args:
        args.remove('--strict-arcs')
        fake.ARCS_TAKE_SKETCH_POINTS = False
        print('(arcs refuse sketch points: exercising the coincident-constraint fallback)')
    configs = [('given settings', settings(m, args))] if args else [(l, settings(m, o)) for l, o in CONFIGS]
    results = [run(label, p) for label, p in configs]
    print('\n%d of %d OK' % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
