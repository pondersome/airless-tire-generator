"""Airless Tire Generator for Autodesk Fusion - a Ponderbotics project.
https://github.com/pondersome/airless-tire-generator
MIT License, see LICENSE in the repository root.

Generates parametric airless (structured) tires for 3D printing: a ring of
printable structure between an inner rim and an optional tread rim, with
optional anchors that key the tire to a separately designed hub.

Add-in: loads at Fusion startup and adds a button to SOLID > CREATE (next to
Spur Gear). Because it stays loaded, right-click > Repeat works too.

Pattern type is chosen first; it decides which parameter group is shown and
how the shared parameters are used. Implemented: Gothic arch, Curved spoke, Honeycomb.

All structural thicknesses are given as a number of slicer lines times the
line width, so every member prints as whole wall loops with no gap fill.

Geometry (top view, XY plane, extruded +Z by width):
    bore (hub interface) r0 .. inner rim .. r1 .. spoke zone .. r2 .. tread rim .. r3
Tread rim = 0 lines means no outer rim: the structure runs past the OD and is
trimmed to a cylinder at r3, so the structure itself is the contact surface.
Anchors (pegs, T-slots, dovetails) can project inward from the bore. They are
joined to the tire, and a separate hidden 'Hub cutter' body (anchors grown by
the clearance, 1 mm past each face) is made for Combine > Cut on the hub.
"""
import adsk.core, adsk.fusion, traceback, math, json, os, time

CMD_ID = 'Ponderbotics_AirlessTireGenerator'
CMD_NAME = 'Airless Tire Generator'
ATTR_GROUP = 'PonderboticsAirlessTire'
# settings stored on tires made by earlier pre-release names of this tool
LEGACY_ATTR_GROUPS = ('IronReignStructuredTire', 'IronReignWheelGenerator')
ATTR_NAME = 'params'
SCRIPT_VERSION = '1.11'
HERE = os.path.dirname(os.path.realpath(__file__))
ICON_FOLDER = os.path.join(HERE, 'resources')
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'last_settings.json')

PAT_GOTHIC = 'Gothic arch'
PAT_CURVED = 'Curved spoke'
PAT_HONEY = 'Honeycomb'
PATTERNS = [PAT_GOTHIC, PAT_CURVED, PAT_HONEY]
APEX_OUT = 'Toward tread'
APEX_IN = 'Toward hub'
SHAPE_C = 'C-curve (one arc)'
SHAPE_S = 'S-curve (two arcs)'

DEFAULTS = {
    'pattern': PAT_GOTHIC,
    # shared tire parameters (mm / counts)
    'tire_od': 96.0,
    'bore_d': 60.0,
    'width': 20.0,
    'line_w': 0.62,
    'inner_lines': 4,
    'outer_lines': 3,
    'fillet': 0.6,
    'keep_open': False,    # only used when tread rim = 0: open vs closed tread
    # Gothic arch parameters
    'g_count': 12,
    'g_spoke_lines': 2,
    'g_bulge': 0.15,
    'g_apex': APEX_OUT,
    'g_interleave': True,
    # Curved spoke parameters
    'c_count': 16,
    'c_spoke_lines': 2,
    'c_lean': 20.0,
    'c_bulge': 0.15,
    'c_shape': SHAPE_C,
    'c_alternate': False,
    # Honeycomb parameters
    'h_count': 28,
    'h_rows': 1,
    'h_lines': 2,
    'h_angle': 30.0,
    # Anchors projecting inward from the bore (count 0 = off)
    'a_peg_n': 0,
    'a_peg_dia': 4.0,      # round head: a rod running the full tire width
    'a_peg_id': 0.0,       # hole down the rod (0 = solid)
    'a_peg_stem_w': 2.0,   # rectangular stem joining the head to the bore
    'a_peg_stem_l': 1.5,   # bore to the edge of the head circle
    'a_peg_phase': 0.0,
    'a_t_n': 0,
    'a_t_neck_w': 3.0,
    'a_t_neck_d': 2.0,
    'a_t_head_w': 7.0,
    'a_t_head_d': 2.5,
    'a_t_phase': 0.0,
    'a_dt_n': 0,
    'a_dt_root_w': 4.0,
    'a_dt_tip_w': 7.0,
    'a_dt_d': 4.0,
    'a_dt_phase': 0.0,
    'a_cutter': True,
    'a_clear': 0.2,
}

_handlers = []          # live for the add-in's lifetime
_dialog_handlers = []   # live while one dialog is open
_menu_pick = (0.0, [])  # (time, entities) captured when the right-click menu opened
MENU_PICK_SECONDS = 60  # how long a right-click pick stays usable for Repeat
_app = None
_ui = None
_target = None   # tire selected at launch: {'occ', 'parent', 'transform', 'name'}


# ----------------------------------------------------------------- settings
def migrate(raw):
    """Translate settings saved by older versions. v0.7 had 'keep_outer',
    which meant 'closed' for Gothic arch but 'open' for Honeycomb; v0.6 and
    earlier had no toggle (Gothic was open, Honeycomb closed)."""
    raw = dict(raw)
    if 'a_peg_w' in raw and 'a_peg_dia' not in raw:   # v1.2 square pegs
        raw['a_peg_dia'] = raw['a_peg_w']
        raw.setdefault('a_peg_id', 0.0)
    if 'a_peg_stem_w' not in raw and 'a_peg_dia' in raw:   # v1.2/v1.3 had no stem
        raw['a_peg_stem_w'] = round(float(raw['a_peg_dia']) / 2.0, 2)
    if 'keep_open' not in raw:
        gothic = raw.get('pattern') == PAT_GOTHIC
        if 'keep_outer' in raw:
            ko = bool(raw['keep_outer'])
            raw['keep_open'] = (not ko) if gothic else ko
        else:
            raw['keep_open'] = gothic
    return {k: v for k, v in raw.items() if k in DEFAULTS}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, 'r') as f:
            s.update(migrate(json.load(f)))
    except Exception:
        pass
    return s


def replace_target(occ, comp):
    """Resolve the occurrence to replace: the selected one, or the component's
    only occurrence. None if ambiguous (component used more than once)."""
    if occ is None:
        design = adsk.fusion.Design.cast(_app.activeProduct)
        occs = design.rootComponent.allOccurrencesByComponent(comp)
        if occs.count != 1:
            return None
        occ = occs.item(0)
    native = occ.nativeObject if occ.nativeObject else occ
    return {'occ': native, 'parent': native.sourceComponent,
            'transform': native.transform2, 'name': comp.name}


def settings_from_selection():
    """If a generated tire (occurrence, component or body) is selected,
    return (settings, component name, replace target) from its stored attribute.
    Right-click > Repeat clears the active selection before the dialog opens,
    so fall back to what was selected when the right-click menu appeared."""
    global _menu_pick
    ents = []
    try:
        sels = _ui.activeSelections
        ents = [sels.item(i).entity for i in range(sels.count)]
    except Exception:
        pass
    found = tire_from_entities(ents)
    if found[0] is None:
        t0, picked = _menu_pick
        if picked and time.time() - t0 < MENU_PICK_SECONDS:
            found = tire_from_entities([e for e in picked if e is not None and e.isValid])
    _menu_pick = (0.0, [])
    return found


def tire_from_entities(ents):
    try:
        for ent in ents:
            comp = None
            occ = adsk.fusion.Occurrence.cast(ent)
            body = adsk.fusion.BRepBody.cast(ent)
            if occ:
                comp = occ.component
            elif body:
                comp = body.parentComponent
            else:
                comp = adsk.fusion.Component.cast(ent)
            if comp is None:
                continue
            a = None
            for grp in (ATTR_GROUP,) + LEGACY_ATTR_GROUPS:
                a = comp.attributes.itemByName(grp, ATTR_NAME)
                if a:
                    break
            if a:
                s = dict(DEFAULTS)
                s.update(migrate(json.loads(a.value)))
                try:
                    tgt = replace_target(occ, comp)
                except Exception:
                    tgt = None
                return s, comp.name, tgt
    except Exception:
        pass
    return None, None, None


def relevant_keys(p):
    """Shared keys plus only the chosen pattern's keys, and only the anchor
    types that are in use."""
    pre = {PAT_GOTHIC: 'g_', PAT_CURVED: 'c_', PAT_HONEY: 'h_'}.get(p['pattern'], '#')
    keys = [k for k in DEFAULTS if not k[:2] in ('g_', 'c_', 'h_', 'a_') or k.startswith(pre)]
    used = [t for t in ('peg', 't', 'dt') if int(p.get('a_%s_n' % t, 0)) > 0]
    for k in DEFAULTS:
        if any(k.startswith('a_%s_' % t) for t in used):
            keys.append(k)
    if used:
        keys += ['a_cutter', 'a_clear']
    return keys


def record_params(comp, p):
    """Store settings on the component: full JSON as an attribute (read back
    by the script for regen) and a readable summary in Description."""
    rec = dict(p)
    rec['_script_version'] = SCRIPT_VERSION
    comp.attributes.add(ATTR_GROUP, ATTR_NAME, json.dumps(rec))
    parts = []
    for k in relevant_keys(p):
        v = p[k]
        parts.append('%s=%s' % (k, ('%g' % v) if isinstance(v, float) else v))
    try:
        comp.description = 'AirlessTireGenerator %s: %s' % (SCRIPT_VERSION, '; '.join(parts))
    except Exception:
        pass


def save_settings(s):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------- geometry helpers (mm in, cm out)
def P(x, y):
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, 0)


def polar(r, a):
    return (r * math.cos(a), r * math.sin(a))


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def nearest_end(curve, pt):
    s, e = curve.startSketchPoint, curve.endSketchPoint
    return s if s.geometry.distanceTo(pt) <= e.geometry.distanceTo(pt) else e


class TireError(Exception):
    pass


def ring_radii(p):
    lw = p['line_w']
    r0 = p['bore_d'] / 2.0
    r1 = r0 + p['inner_lines'] * lw
    r3 = p['tire_od'] / 2.0
    r2 = r3 - p['outer_lines'] * lw
    return r0, r1, r2, r3


def validate_common(p):
    r0, r1, r2, r3 = ring_radii(p)
    if p['line_w'] <= 0 or p['width'] <= 0:
        raise TireError('Line width and tire width must be positive.')
    if r0 <= 0:
        raise TireError('Bore diameter must be positive.')
    if r2 - r1 < 2.0:
        raise TireError('Spoke zone is only %.2f mm deep. Increase tire OD or reduce bore/rim thickness.' % (r2 - r1))
    return r0, r1, r2, r3


# ----------------------------------------------------------------- Gothic arch
def gothic_legs(p):
    """Return list of legs. Each leg: dict(kind='arc'|'line', ...) in mm, plus
    sampled centerline points for clearance checks."""
    r0, r1, r2, r3 = validate_common(p)
    lw = p['line_w']
    t = p['g_spoke_lines'] * lw
    ti = p['inner_lines'] * lw
    to = p['outer_lines'] * lw
    n = int(p['g_count'])
    bulge = p['g_bulge']
    if n < 3:
        raise TireError('Need at least 3 arches.')
    if not (0.0 <= bulge < 0.45):
        raise TireError('Bulge must be between 0 and 0.45 (fraction of leg length).')
    check_spoke_fits(t, ti, to)

    # leg ends are buried at mid-rim so the union is clean
    r_in_end = r1 - ti / 2.0
    r_out_end = tread_end(r2, to, t)
    if to <= 0 and not p.get('keep_open'):
        # closed: legs meet ON the OD, so the junction stays inside the tire
        # and the trim only shaves a small land off the tip. Open: the junction
        # lies past the OD and is trimmed away, leaving separate leg tips.
        r_out_end = r3
    if p['g_apex'] == APEX_OUT:
        ra, rb = r_out_end, r_in_end
    else:
        ra, rb = r_in_end, r_out_end

    alpha = 2 * math.pi / n
    rounds = (0, 1) if p.get('g_interleave') else (0,)
    legs = []
    warnings = []
    for rnd in rounds:
        for k in range(n):
            phi = k * alpha + rnd * alpha / 2.0  # second round offset by half an arch
            A = polar(ra, phi)
            for side in (-1, 1):
                B = polar(rb, phi + side * alpha / 2.0)
                leg = make_leg(B, A, phi, bulge, t, k, side)
                leg['round'] = rnd
                legs.append(leg)
        w = check_clearance([l for l in legs if l['round'] == rnd], n, t, r1, r2, lw)
        if w and w not in warnings:
            warnings.append(w)
    for l in legs:
        l['seed'] = (l['k'] == 0)
    label = 'Gothic N%d%s OD%g' % (n, 'x2' if p.get('g_interleave') else '', p['tire_od'])
    return {'legs': legs, 'radii': (r0, r1, r2, r3), 't': t, 'qty': n, 'label': label, 'warnings': warnings}


# ----------------------------------------------------------------- Curved spoke
def curved_legs(p):
    """Spokes from inner rim to tread. The outer end leads the inner end by
    'lean' degrees; each spoke bows into a C (one arc) or S (two arcs with a
    smooth inflection at mid-span). 'Alternate' mirrors every other spoke so
    the wheel behaves the same in both rotation directions."""
    r0, r1, r2, r3 = validate_common(p)
    lw = p['line_w']
    t = p['c_spoke_lines'] * lw
    ti = p['inner_lines'] * lw
    to = p['outer_lines'] * lw
    n = int(p['c_count'])
    bulge = p['c_bulge']
    lean = math.radians(p['c_lean'])
    alt = bool(p.get('c_alternate'))
    s_shape = (p['c_shape'] == SHAPE_S)
    if n < 3:
        raise TireError('Need at least 3 spokes.')
    if alt and n % 2:
        raise TireError('Alternating spokes need an even spoke count.')
    if abs(bulge) >= 0.45:
        raise TireError('Bulge must be between -0.45 and 0.45 (fraction of spoke length).')
    check_spoke_fits(t, ti, to)

    r_in_end = r1 - ti / 2.0
    r_out_end = tread_end(r2, to, t)
    alpha = 2 * math.pi / n
    legs = []
    for k in range(n):
        mir = -1 if (alt and k % 2) else 1
        th = k * alpha
        A = polar(r_in_end, th)
        B = polar(r_out_end, th + mir * lean)
        b = bulge * mir
        sg = 1 if b >= 0 else -1
        if s_shape:
            M = ((A[0] + B[0]) / 2.0, (A[1] + B[1]) / 2.0)
            legs.append(make_leg(A, M, 0, abs(b), t, k, 0, sign=sg))
            legs.append(make_leg(M, B, 0, abs(b), t, k, 1, sign=-sg))
        else:
            legs.append(make_leg(A, B, 0, abs(b), t, k, 0, sign=sg))

    # spokes leaning the same way must not touch between the rims; with
    # 'alternate', mirrored neighbours may cross on purpose (V / X lattice)
    period = 2 if alt else 1
    lo, hi = r1 + 2 * t, r2 - 2 * t
    pts = {}
    for l in legs:
        pts.setdefault(l['k'], []).extend(pt for pt in l['samples'] if lo < math.hypot(*pt) < hi)
    worst = None
    for k in range(n):
        for pa in pts[k]:
            for pb in pts[(k + period) % n]:
                d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                worst = d if worst is None else min(worst, d)
    warnings = []
    w = gap_warning('spokes', worst, t, lw) if worst is not None else None
    if w:
        warnings.append(w)

    for l in legs:
        l['seed'] = (l['k'] < period)
    label = 'Curved%s N%d L%g OD%g' % ('S' if s_shape else 'C', n, p['c_lean'], p['tire_od'])
    if alt:
        label += ' alt'
    return {'legs': legs, 'radii': (r0, r1, r2, r3), 't': t, 'qty': n // period, 'label': label,
            'warnings': warnings}


# ----------------------------------------------------------------- Honeycomb
def straight_wall(Pt, Qt, t, k, tag, ext_p, ext_q):
    """Straight band from Pt to Qt, extended past each end (to close the
    corners where three walls meet, or to bury the end in a rim)."""
    (px, py), (qx, qy) = Pt, Qt
    dx, dy = qx - px, qy - py
    c = math.hypot(dx, dy)
    ux, uy = dx / c, dy / c
    P2 = (px - ux * ext_p, py - uy * ext_p)
    Q2 = (qx + ux * ext_q, qy + uy * ext_q)
    leg = make_leg(P2, Q2, 0, 0, t, k, tag)
    leg['len'] = c
    return leg


def honey_legs(p):
    """Polar honeycomb. Zigzag wall lines run around the wheel; radial walls
    join each zigzag peak to the valley of the next line, and the first/last
    lines to the rims. 'Cell rows' = number of full cell rows (zigzag lines =
    rows + 1). Cell angle 30 = regular hexagons, 0 = rectangular bricks,
    negative = re-entrant (auxetic) cells. The angle is exact at mid-zone;
    cells widen toward the tread."""
    r0, r1, r2, r3 = validate_common(p)
    lw = p['line_w']
    t = p['h_lines'] * lw
    ti = p['inner_lines'] * lw
    to = p['outer_lines'] * lw
    n = int(p['h_count'])
    rows = int(p['h_rows'])
    ang = p['h_angle']
    if n < 3:
        raise TireError('Need at least 3 cells around.')
    if rows < 1:
        raise TireError('Need at least 1 cell row.')
    if not (-45.0 <= ang <= 60.0):
        raise TireError('Cell angle must be between -45 and 60 degrees.')
    check_spoke_fits(t, ti, to)

    alpha = 2 * math.pi / n
    depth = r2 - r1
    r_mid = (r1 + r2) / 2.0
    half_w = r_mid * alpha / 2.0          # horizontal run of one zigzag wall at mid-zone
    d = math.tan(math.radians(ang)) * half_w   # zigzag amplitude (negative = re-entrant)
    lines_n = rows + 1
    outer_walls = to > 0 or bool(p.get('keep_open'))   # open: radial lugs to the OD
    if outer_walls:
        # rim bond + line + rows * (bond + line) + rim bond
        # depth = (rows + 2) * h + (rows + 1) * d
        h = (depth - lines_n * d) / (rows + 2)
    else:
        # no tread rim: the last zigzag line's outermost points sit on the OD
        # depth = (rows + 1) * h + rows * d + max(d, 0)
        h = (depth - rows * d - max(d, 0.0)) / (rows + 1)
    warnings = []
    if h <= t / 2.0:
        raise TireError('Radial walls would be only %.2f mm long, so the cells collapse. '
                        'Use more cells around (smaller cells), fewer rows, or a smaller cell angle.' % h)
    if h < 2 * t:
        warnings.append('Warning: radial walls are only %.2f mm long (walls are %.2f mm thick), '
                        'so cells are nearly flat.' % (h, t))
    if d < 0:
        w = gap_warning('re-entrant cell points', h + 2 * d, t, lw)
        if w:
            warnings.append(w)
    zig_len = math.hypot(half_w, d)
    if zig_len <= t:
        raise TireError('Zigzag walls would be only %.2f mm long, no longer than they are thick. '
                        'Use fewer cells around.' % zig_len)
    if zig_len < 2 * t:
        warnings.append('Warning: zigzag walls are only %.2f mm long, so cells are tiny.' % zig_len)

    e = 0.3 * t                     # corner overlap where three walls meet
    r_in_end = r1 - ti / 2.0
    r_out_end = tread_end(r2, to, t)

    def V(kline):                   # centre radius of zigzag line k
        return r1 + h + d / 2.0 + kline * (h + d)

    def node(kline, j):             # j counts half-cells around the wheel
        peak = (j + kline) % 2 == 0
        r = V(kline) + (d / 2.0 if peak else -d / 2.0)
        return polar(r, j * alpha / 2.0), peak

    legs = []
    for kline in range(lines_n):
        for j in range(2 * n):
            (A, _), (B, _) = node(kline, j), node(kline, j + 1)
            leg = straight_wall(A, B, t, j // 2, 'z', e, e)
            leg['seed'] = j < 2
            legs.append(leg)
        for j in range(2 * n):
            A, peak = node(kline, j)
            if kline == 0 and not peak:            # inner rim -> first line valleys
                leg = straight_wall(polar(r_in_end, j * alpha / 2.0), A, t, j // 2, 'ri', 0, e)
            elif kline == lines_n - 1 and peak and outer_walls:   # last line peaks -> tread rim / OD
                leg = straight_wall(A, polar(r_out_end, j * alpha / 2.0), t, j // 2, 'ro', e, 0)
            elif kline < lines_n - 1 and peak:     # peak -> next line valley
                B, _ = node(kline + 1, j)
                leg = straight_wall(A, B, t, j // 2, 'b', e, e)
            else:
                continue
            leg['seed'] = j < 2
            legs.append(leg)
    label = 'Honey N%d R%d A%g OD%g' % (n, rows, ang, p['tire_od'])
    return {'legs': legs, 'radii': (r0, r1, r2, r3), 't': t, 'qty': n, 'label': label, 'warnings': warnings}


def tread_end(r2, to, t):
    """Radius where structure ends at the tread: buried mid-rim, or, with no
    tread rim, a spoke thickness past the OD (trimmed back to the OD later)."""
    return r2 + to / 2.0 if to > 0 else r2 + t


def check_spoke_fits(t, ti, to):
    if t >= ti or (to > 0 and t >= to):
        raise TireError('Spoke (%.2f mm) must be thinner than both rims (inner %.2f, tread %.2f mm) '
                         'so spoke ends stay buried in the rims. Add rim lines or remove spoke lines.' % (t, ti, to))


def make_leg(Pt, Qt, phi, bulge, t, k, side, sign=None):
    """Band of thickness t along the arc from Pt to Qt with sagitta bulge*chord.
    sign=None: bow away from the radial axis at angle phi (Gothic legs).
    sign=+1/-1: bow to the left/right of the Pt->Qt direction."""
    px, py = Pt
    qx, qy = Qt
    dx, dy = qx - px, qy - py
    c = math.hypot(dx, dy)
    mx, my = (px + qx) / 2.0, (py + qy) / 2.0
    leg = {'k': k, 'side': side, 't': t, 'P': Pt, 'Q': Qt}
    if bulge < 1e-4:
        leg['kind'] = 'line'
        leg['samples'] = [(px + dx * i / 20.0, py + dy * i / 20.0) for i in range(21)]
        return leg
    s = bulge * c
    nx, ny = -dy / c, dx / c
    if sign is None:
        # bulge away from this arch's axis (pointed-arch legs bow outward)
        def off_axis(sg):
            x, y = mx + sg * nx * s, my + sg * ny * s
            return abs(wrap(math.atan2(y, x) - phi))
        sign = 1 if off_axis(1) > off_axis(-1) else -1
    nx, ny = nx * sign, ny * sign
    R = (c * c / 4.0 + s * s) / (2.0 * s)
    qmx, qmy = mx + nx * s, my + ny * s
    cx, cy = qmx - nx * R, qmy - ny * R
    a1 = math.atan2(py - cy, px - cx)
    a2 = math.atan2(qy - cy, qx - cx)
    sweep = wrap(a2 - a1)
    leg.update(kind='arc', C=(cx, cy), R=R, a1=a1, sweep=sweep)
    leg['samples'] = [(cx + R * math.cos(a1 + sweep * i / 30.0), cy + R * math.sin(a1 + sweep * i / 30.0))
                      for i in range(31)]
    return leg


def gap_warning(what, dist, t, lw):
    """Centerline distance between two members -> warning text or None.
    Overlapping members just merge in the join, so that is only a note; the
    real problem is a gap narrower than one slicer line (unprintable sliver,
    and a common cause of fillet failures)."""
    gap = dist - t
    if gap <= 0:
        return ('Note: neighbouring %s touch mid-span (overlap %.2f mm), so they merge into one member there.'
                % (what, -gap))
    if gap < lw:
        return ('Warning: neighbouring %s leave only a %.2f mm gap mid-span, narrower than one line (%.2f mm). '
                'The slicer will fill or skip it, and fillets may fail there.' % (what, gap, lw))
    return None


def check_clearance(legs, n, t, r1, r2, lw):
    """Neighbouring arches bow toward each other; make sure they only meet at
    their shared base, not mid-span."""
    by = {(l['k'], l['side']): l for l in legs}
    lo, hi = r1 + 2 * t, r2 - 2 * t
    worst = None
    for k in range(n):
        a = by[(k, 1)]['samples']
        b = by[((k + 1) % n, -1)]['samples']
        a = [pt for pt in a if lo < math.hypot(*pt) < hi]
        b = [pt for pt in b if lo < math.hypot(*pt) < hi]
        for pa in a:
            for pb in b:
                d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                worst = d if worst is None else min(worst, d)
    return gap_warning('arches', worst, t, lw) if worst is not None else None


def draw_leg(lines, arcs, leg):
    t = leg['t']
    if leg['kind'] == 'line':
        (px, py), (qx, qy) = leg['P'], leg['Q']
        dx, dy = qx - px, qy - py
        c = math.hypot(dx, dy)
        ox, oy = -dy / c * t / 2.0, dx / c * t / 2.0
        pts = [P(px + ox, py + oy), P(qx + ox, qy + oy), P(qx - ox, qy - oy), P(px - ox, py - oy)]
        l0 = lines.addByTwoPoints(pts[0], pts[1])
        l1 = lines.addByTwoPoints(l0.endSketchPoint, pts[2])
        l2 = lines.addByTwoPoints(l1.endSketchPoint, pts[3])
        lines.addByTwoPoints(l2.endSketchPoint, l0.startSketchPoint)
        return
    cx, cy = leg['C']
    R, a1, sw = leg['R'], leg['a1'], leg['sweep']
    a2 = a1 + sw
    made = []
    for r in (R - t / 2.0, R + t / 2.0):
        sp = P(cx + r * math.cos(a1), cy + r * math.sin(a1))
        ep = P(cx + r * math.cos(a2), cy + r * math.sin(a2))
        arc = arcs.addByCenterStartSweep(P(cx, cy), sp, sw)
        made.append((arc, sp, ep))
    (ai, si, ei), (ao, so, eo) = made
    lines.addByTwoPoints(nearest_end(ai, si), nearest_end(ao, so))
    lines.addByTwoPoints(nearest_end(ai, ei), nearest_end(ao, eo))


# ----------------------------------------------------------------- anchors
ANCHOR_NAMES = {'peg': 'round pegs', 't': 'T-slots', 'dt': 'dovetails'}


def anchor_local(kind, p, r0, emb):
    """Polygon anchor (T-slot, dovetail) outline centred on angle 0 as
    (radius, tangential offset) points, rooted emb mm into the inner rim so it
    unions cleanly with the tire. Round pegs are built separately."""
    rr = r0 + emb
    if kind == 't':
        wn, dn, wh, dh = p['a_t_neck_w'], p['a_t_neck_d'], p['a_t_head_w'], p['a_t_head_d']
        if min(wn, dn, wh, dh) <= 0:
            raise TireError('T-slot neck and head sizes must be positive.')
        if wh <= wn:
            raise TireError('T-slot head width must be wider than the neck.')
        a, b = r0 - dn, r0 - dn - dh
        return [(rr, -wn / 2), (a, -wn / 2), (a, -wh / 2), (b, -wh / 2),
                (b, wh / 2), (a, wh / 2), (a, wn / 2), (rr, wn / 2)], dn + dh, wh
    if kind == 'dt':
        wr, wt, d = p['a_dt_root_w'], p['a_dt_tip_w'], p['a_dt_d']
        if min(wr, wt, d) <= 0:
            raise TireError('Dovetail widths and depth must be positive.')
        if wt <= wr:
            raise TireError('Dovetail tip width must be wider than the root (that is what locks it).')
        h_rr = wr / 2 - emb * (wt - wr) / (2 * d)   # sides continued into the rim
        if h_rr <= 0.2:
            raise TireError('Dovetail sides converge inside the rim. Use a smaller tip width or more depth.')
        return [(rr, -h_rr), (r0 - d, -wt / 2), (r0 - d, wt / 2), (rr, h_rr)], d, wt
    raise TireError('Unknown anchor type %s' % kind)


def to_xy(local, ang):
    c, s_ = math.cos(ang), math.sin(ang)
    return [(r * c - v * s_, r * s_ + v * c) for r, v in local]


def offset_polygon(pts, c):
    """Grow a simple polygon outward by c (mitred corners)."""
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    if area < 0:
        pts = pts[::-1]
    n = len(pts)
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        nx, ny = dy / L, -dx / L          # outward for CCW
        lines.append(((x0 + nx * c, y0 + ny * c), (dx, dy)))
    out = []
    for i in range(n):
        (p0, d0), (p1, d1) = lines[i - 1], lines[i]
        den = d0[0] * d1[1] - d0[1] * d1[0]
        if abs(den) < 1e-12:
            out.append(p1)
            continue
        t = ((p1[0] - p0[0]) * d1[1] - (p1[1] - p0[1]) * d1[0]) / den
        out.append((p0[0] + d0[0] * t, p0[1] + d0[1] * t))
    return out


def anchor_specs(p, radii):
    """Validated anchor types in use: list of dicts plus warnings."""
    r0, r1, r2, r3 = radii
    emb = (r1 - r0) / 2.0
    lw = p['line_w']
    specs, warnings, spans = [], [], []
    for kind in ('peg', 't', 'dt'):
        n = int(p.get('a_%s_n' % kind, 0))
        if n <= 0:
            continue
        if kind == 'peg':
            dia, idia = p['a_peg_dia'], p['a_peg_id']
            sw, sl = p['a_peg_stem_w'], p['a_peg_stem_l']
            if dia <= 0 or sw <= 0 or sl < 0:
                raise TireError('Peg diameter and stem width must be positive (stem length can be 0).')
            if sw >= dia:
                raise TireError('Peg stem (%.1f mm) must be narrower than the head (%.1f mm), '
                                'or nothing locks.' % (sw, dia))
            R = dia / 2.0
            rc = r0 - sl - R                          # head centre radius
            chord = math.sqrt(R * R - (sw / 2.0) ** 2)  # stem meets the circle here
            if idia > 0:
                if (dia - idia) / 2.0 < lw:
                    raise TireError('Peg rod wall is %.2f mm, thinner than one line (%.2f mm). '
                                    'Use a smaller hole, or 0 for a solid rod.' % ((dia - idia) / 2.0, lw))
                if chord <= idia / 2.0:
                    raise TireError('Peg stem is so wide it would reach into the hole. '
                                    'Use a narrower stem or a smaller hole.')
            depth = sl + dia
            # stem polygon from inside the rim to where it meets the head circle
            local = [(r0 + emb, -sw / 2), (rc + chord, -sw / 2), (rc + chord, sw / 2), (r0 + emb, sw / 2)]
            tipw = dia
        else:
            local, depth, tipw = anchor_local(kind, p, r0, emb)
        if r0 - depth < 2.0:
            raise TireError('%s reach within %.1f mm of the axle centre. Reduce their depth.'
                            % (ANCHOR_NAMES[kind].capitalize(), r0 - depth))
        phase = math.radians(p['a_%s_phase' % kind])
        # angular footprint at the bore (widest point at or inside the bore)
        half = max(abs(v) for r, v in local if r <= r0 + 1e-9)
        half_ang = math.asin(min(0.999, half / r0))
        for k in range(n):
            spans.append((phase + k * 2 * math.pi / n, half_ang, kind))
        # crowding at the tips (inside the bore, where there is less room)
        r_tip = rc if kind == 'peg' else r0 - depth      # pegs: widest at the head centre
        pitch = 2 * r_tip * math.sin(math.pi / n) if n > 1 else 1e9
        tip_gap = pitch - tipw
        if tip_gap <= 0:
            warnings.append('Warning: %s overlap by %.2f mm at their tips. Use fewer, narrower or shallower anchors.'
                            % (ANCHOR_NAMES[kind], -tip_gap))
        elif tip_gap < lw:
            warnings.append('Warning: %s are only %.2f mm apart at their tips (need about one line, %.2f mm).'
                            % (ANCHOR_NAMES[kind], tip_gap, lw))
        sp = {'kind': kind, 'n': n, 'phase': phase, 'local': local}
        if kind == 'peg':
            sp.update(dia=dia, id=idia, rc=rc)
        specs.append(sp)
    # overlap between any two anchors around the bore
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            a1, h1, k1 = spans[i]
            a2, h2, k2 = spans[j]
            gap_ang = abs(wrap(a1 - a2)) - h1 - h2
            if gap_ang * r0 < lw:
                names = ANCHOR_NAMES[k1] if k1 == k2 else '%s and %s' % (ANCHOR_NAMES[k1], ANCHOR_NAMES[k2])
                msg = ('Warning: %s overlap or nearly touch at the bore. Change the counts or a phase angle.'
                       % names)
                if msg not in warnings:
                    warnings.append(msg)
    return specs, warnings


def build_anchor_bodies(comp, specs, width_vi, grow=0.0, start_mm=0.0, length_mm=None):
    """Draw every copy of every anchor directly in a sketch (no body pattern)
    and extrude them in one feature per sketch, so the features report exactly
    the bodies they made. grow > 0 builds the cutter version (grown by the
    clearance, solid). Returns the list of new bodies."""
    made = []
    for sp in specs:
        angles = [sp['phase'] + k * 2 * math.pi / sp['n'] for k in range(sp['n'])]
        tag = ('Cutter ' if grow > 0 else 'Anchor ') + ANCHOR_NAMES[sp['kind']]

        # stems / T-slot / dovetail outlines
        sk = comp.sketches.add(comp.xYConstructionPlane)
        sk.name = tag + (' stems' if sp['kind'] == 'peg' else '')
        sk.isComputeDeferred = True
        for ang in angles:
            pts = to_xy(sp['local'], ang)
            if grow > 0:
                pts = offset_polygon(pts, grow)
            draw_polygon(sk.sketchCurves.sketchLines, pts)
        sk.isComputeDeferred = False
        made += extrude_all(comp, sk, width_vi, start_mm, length_mm)

        # peg heads: circles (annulus when the rod has a hole)
        if sp['kind'] == 'peg':
            R = sp['dia'] / 2.0 + grow
            hole = 0.0 if grow > 0 else sp['id'] / 2.0
            sk = comp.sketches.add(comp.xYConstructionPlane)
            sk.name = tag + ' heads'
            sk.isComputeDeferred = True
            circles = sk.sketchCurves.sketchCircles
            for ang in angles:
                cx, cy = polar(sp['rc'], ang)
                circles.addByCenterRadius(P(cx, cy), R / 10.0)
                if hole > 0:
                    circles.addByCenterRadius(P(cx, cy), hole / 10.0)
            sk.isComputeDeferred = False
            made += extrude_all(comp, sk, width_vi, start_mm, length_mm,
                                skip_loops=1 if hole > 0 else None)
    return made


def draw_polygon(lines, pts):
    first = prev = None
    for i in range(len(pts)):
        nxt = pts[(i + 1) % len(pts)]
        if prev is None:
            ln = lines.addByTwoPoints(P(*pts[i]), P(*nxt))
            first = ln
        elif i == len(pts) - 1:
            ln = lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
        else:
            ln = lines.addByTwoPoints(prev.endSketchPoint, P(*nxt))
        prev = ln


def extrude_all(comp, sk, width_vi, start_mm, length_mm, skip_loops=None):
    """Extrude every profile in the sketch as new bodies. With skip_loops=1 the
    single-loop profiles (the holes inside annuli) are left out."""
    profs = adsk.core.ObjectCollection.create()
    for pr in sk.profiles:
        if skip_loops is not None and pr.profileLoops.count == skip_loops:
            continue
        profs.add(pr)
    if profs.count == 0:
        raise TireError('Sketch "%s" has no profiles to extrude.' % sk.name)
    f = extrude_extent(comp.features.extrudeFeatures, profs, width_vi, start_mm, length_mm)
    return [b for b in f.bodies]


def extrude_extent(ext, prof, width_vi, start_mm, length_mm):
    NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    if length_mm is None:
        return ext.addSimple(prof, width_vi, NEW)
    ei = ext.createInput(prof, NEW)
    ei.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(
        adsk.core.ValueInput.createByReal(length_mm / 10.0)),
        adsk.fusion.ExtentDirections.PositiveExtentDirection)
    ei.startExtent = adsk.fusion.OffsetStartDefinition.create(
        adsk.core.ValueInput.createByReal(start_mm / 10.0))
    return ext.add(ei)


def cutter_ring(comp, r_in, r_out, width_mm):
    """Thin annulus that connects all cutter pieces into one body, extended
    1 mm past each face like the rest of the cutter."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = 'Cutter ring'
    for r in (r_in, r_out):
        sk.sketchCurves.sketchCircles.addByCenterRadius(P(0, 0), r / 10.0)
    prof = None
    for pr in sk.profiles:
        if pr.profileLoops.count == 2:
            prof = pr
    if prof is None:
        raise TireError('Could not build the cutter ring profile.')
    f = extrude_extent(comp.features.extrudeFeatures, prof, None, -1.0, width_mm + 2.0)
    return f.bodies.item(0)


def join_bodies(comp, target, tools_list):
    """Join tools into target. Bodies that don't touch become extra lumps of
    one multi-lump body (Fusion supports that), which is what the cutter needs."""
    tools_list = [b for b in tools_list if b != target]
    if not tools_list:
        return
    tools = adsk.core.ObjectCollection.create()
    for b in tools_list:
        tools.add(b)
    ci = comp.features.combineFeatures.createInput(target, tools)
    ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    comp.features.combineFeatures.add(ci)


# ----------------------------------------------------------------- build
def compute(p):
    if p['pattern'] == PAT_GOTHIC:
        g = gothic_legs(p)
    elif p['pattern'] == PAT_CURVED:
        g = curved_legs(p)
    elif p['pattern'] == PAT_HONEY:
        g = honey_legs(p)
    else:
        raise TireError('"%s" is not implemented yet.' % p['pattern'])
    specs, aw = anchor_specs(p, g['radii'])
    g['anchors'] = specs
    g['warnings'] = g.get('warnings', []) + aw
    if specs and p.get('a_cutter') and p.get('a_clear', 0) < 0:
        raise TireError('Cutter clearance cannot be negative.')
    return g


def assess(p):
    """Run the geometry checks without touching the design.
    Returns (error text or None, list of warnings)."""
    try:
        g = compute(p)
        return None, g.get('warnings', [])
    except TireError as e:
        return str(e), []
    except Exception as e:
        return 'Unexpected problem in the settings: %s' % e, []


def build(p, parent=None, transform=None):
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        raise TireError('Open a Fusion design first.')

    g = compute(p)
    legs, (r0, r1, r2, r3), qty, label = g['legs'], g['radii'], g['qty'], g['label']
    t_spoke = g['t']

    root = design.rootComponent
    owner = parent if parent else root
    tl_start = timeline_marker(design)
    occ = owner.occurrences.addNewComponent(transform if transform else adsk.core.Matrix3D.create())
    comp = occ.component
    to = p['outer_lines'] * p['line_w']
    if to <= 0:
        label += ' norim ' + ('open' if p.get('keep_open') else 'closed')
    comp.name = 'Tire %s' % label
    plane = comp.xYConstructionPlane
    width = adsk.core.ValueInput.createByReal(p['width'] / 10.0)
    NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation

    # rims
    sk_r = comp.sketches.add(plane)
    sk_r.name = 'Rims'
    circles = sk_r.sketchCurves.sketchCircles
    ring_set = (r0, r1, r2, r3) if to > 0 else (r0, r1)
    for r in ring_set:
        circles.addByCenterRadius(P(0, 0), r / 10.0)
    want = [{round(r0, 4), round(r1, 4)}]
    if to > 0:
        want.append({round(r2, 4), round(r3, 4)})
    rim_profiles = adsk.core.ObjectCollection.create()
    for prof in sk_r.profiles:
        radii = set()
        for loop in prof.profileLoops:
            for pc in loop.profileCurves:
                geo = pc.geometry
                if isinstance(geo, adsk.core.Circle3D):
                    radii.add(round(geo.radius * 10.0, 4))
        if radii in want:
            rim_profiles.add(prof)
    if rim_profiles.count != len(want):
        raise TireError('Could not isolate rim profiles (found %d).' % rim_profiles.count)
    ext = comp.features.extrudeFeatures
    rim_feat = ext.addSimple(rim_profiles, width, NEW)

    # spokes: one sketch per leg of the first arch of each round, so each sketch
    # holds exactly one closed band (no enclosed arch interiors), then pattern.
    seed = adsk.core.ObjectCollection.create()
    for leg in [l for l in legs if l['seed']]:
        sk = comp.sketches.add(plane)
        sk.name = 'Spoke k%d r%d %s' % (leg['k'], leg.get('round', 0), leg['side'])
        draw_leg(sk.sketchCurves.sketchLines, sk.sketchCurves.sketchArcs, leg)
        if sk.profiles.count != 1:
            raise TireError('Spoke sketch "%s" produced %d profiles, expected 1.' % (sk.name, sk.profiles.count))
        f = ext.addSimple(sk.profiles.item(0), width, NEW)
        for b in f.bodies:
            seed.add(b)
    if qty > 1:
        cp = comp.features.circularPatternFeatures
        ci = cp.createInput(seed, comp.zConstructionAxis)
        ci.quantity = adsk.core.ValueInput.createByReal(qty)
        ci.totalAngle = adsk.core.ValueInput.createByString('360 deg')
        ci.isSymmetric = False
        cp.add(ci)

    # union everything into one body
    rim_bodies = [b for b in rim_feat.bodies]
    target = rim_bodies[0]
    tools = adsk.core.ObjectCollection.create()
    for b in comp.bRepBodies:
        if b != target:
            tools.add(b)
    ci = comp.features.combineFeatures.createInput(target, tools)
    ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    comp.features.combineFeatures.add(ci)
    target.name = 'Tire'

    if g['anchors']:
        # Don't trust feature.bodies for multi-profile extrudes (it can report
        # only one body). The component only holds the tire at this point, so
        # every other body is an anchor; join them all, as the spoke union does.
        build_anchor_bodies(comp, g['anchors'], width)
        join_bodies(comp, target, [b for b in comp.bRepBodies if b != target])
        cutter = None
        if p.get('a_cutter'):
            clear = max(p['a_clear'], 1e-4)
            # Fusion splits a body whose pieces don't touch into separate
            # bodies, so tie the cutter pieces together with a ring at the bore
            # (bore - clearance out to where the anchors are rooted). Cutting
            # the hub with it also sizes the hub OD to bore - 2 x clearance.
            ring = cutter_ring(comp, r0 - clear, r0 + (r1 - r0) / 2.0, p['width'])
            build_anchor_bodies(comp, g['anchors'], width, grow=clear,
                                start_mm=-1.0, length_mm=p['width'] + 2.0)
            join_bodies(comp, ring, [b for b in comp.bRepBodies if b != target and b != ring])
            cutter = ring
            cutter.name = 'Hub cutter (clearance %.2f mm)' % p['a_clear']
            cutter.isLightBulbOn = False
        loose = [b.name for b in comp.bRepBodies if b != target and b != cutter]
        if loose:
            g['warnings'].append('Warning: %d bodies were left unjoined: %s'
                                 % (len(loose), ', '.join(loose[:6]) + (' ...' if len(loose) > 6 else '')))

    if to <= 0:
        trim_to_od(comp, target, r3, width, t_spoke)
    record_params(comp, p)

    note = '\n'.join(g.get('warnings', []))
    if p['fillet'] > 0:
        hi = r2 + 0.01 if to > 0 else r3 - 0.05   # never fillet the trimmed tread edges
        fn = fillet_junctions(comp, target, r1, hi, p['fillet'])
        note = (note + '\n' + fn) if note else fn
    group_timeline(design, tl_start, comp.name)
    return comp, note


def timeline_marker(design):
    """Timeline position where new features will land (None for direct-modeling designs)."""
    try:
        if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            return None
        return design.timeline.markerPosition
    except Exception:
        return None


def group_timeline(design, start, name):
    """Collapse everything this tire added to the timeline into one named group."""
    if start is None:
        return
    try:
        tl = design.timeline
        end = tl.markerPosition - 1
        if end > start:
            grp = tl.timelineGroups.add(start, end)
            grp.name = name
            grp.isCollapsed = True
    except Exception:
        pass   # grouping is cosmetic; never fail the build over it


def trim_to_od(comp, body, r3, width, t):
    """No tread rim: cut away everything outside the OD so the structure ends
    in a clean cylinder, making the spoke/cell ends the contact surface."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = 'Tread trim'
    r_big = r3 + 3 * t + 5.0
    for r in (r3, r_big):
        sk.sketchCurves.sketchCircles.addByCenterRadius(P(0, 0), r / 10.0)
    prof = None
    for pr in sk.profiles:
        if pr.profileLoops.count == 2:
            prof = pr
    if prof is None:
        raise TireError('Could not build the tread trim profile.')
    ext = comp.features.extrudeFeatures
    ei = ext.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
    ei.setDistanceExtent(False, width)
    ei.participantBodies = [body]
    ext.add(ei)


def fillet_junctions(comp, body, lo, hi, radius_mm):
    """Fillet the axial (Z-parallel) seam edges where spokes meet rims and each other."""
    edges = adsk.core.ObjectCollection.create()
    tol = 0.01  # mm
    for e in body.edges:
        g = e.geometry
        if not isinstance(g, adsk.core.Line3D):
            continue
        sp, ep = g.startPoint, g.endPoint
        if abs(sp.x - ep.x) > 1e-5 or abs(sp.y - ep.y) > 1e-5:
            continue  # not axial
        if e.faces.count != 2 or e.faces.item(0) == e.faces.item(1):
            continue
        r = math.hypot(sp.x, sp.y) * 10.0
        if lo - tol <= r <= hi:
            edges.add(e)
    if edges.count == 0:
        return 'No junction edges found to fillet.'
    fillets = comp.features.filletFeatures
    try:
        fi = fillets.createInput()
        fi.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByReal(radius_mm / 10.0), True)
        fillets.add(fi)
        return 'Filleted %d junction edges at %.2f mm.' % (edges.count, radius_mm)
    except Exception:
        return ('Fillet of %d junction edges at %.2f mm failed (radius probably too big for a tight crotch). '
                'Body was built without fillets; try a smaller fillet or 0.' % (edges.count, radius_mm))


# ----------------------------------------------------------------- dialog
def read_inputs(inputs):
    p = {}
    p['pattern'] = inputs.itemById('pattern').selectedItem.name
    for k in ('tire_od', 'bore_d', 'width', 'line_w', 'fillet', 'g_bulge'):
        p[k] = inputs.itemById(k).value
    for k in ('inner_lines', 'outer_lines', 'g_count', 'g_spoke_lines'):
        p[k] = inputs.itemById(k).value
    p['keep_open'] = inputs.itemById('keep_open').value
    p['g_apex'] = inputs.itemById('g_apex').selectedItem.name
    p['g_interleave'] = inputs.itemById('g_interleave').value
    for k in ('c_count', 'c_spoke_lines', 'c_lean', 'c_bulge', 'c_alternate'):
        p[k] = inputs.itemById(k).value
    p['c_shape'] = inputs.itemById('c_shape').selectedItem.name
    for k in ('h_count', 'h_rows', 'h_lines', 'h_angle'):
        p[k] = inputs.itemById(k).value
    for k in ('a_peg_n', 'a_peg_dia', 'a_peg_id', 'a_peg_stem_w', 'a_peg_stem_l', 'a_peg_phase',
              'a_t_n', 'a_t_neck_w', 'a_t_neck_d', 'a_t_head_w', 'a_t_head_d', 'a_t_phase',
              'a_dt_n', 'a_dt_root_w', 'a_dt_tip_w', 'a_dt_d', 'a_dt_phase',
              'a_cutter', 'a_clear'):
        p[k] = inputs.itemById(k).value
    return p


def summary(p):
    lw = p['line_w']
    tread = ('%.2f mm' % (p['outer_lines'] * lw)) if p['outer_lines'] > 0 else 'none (open structure)'
    s = 'Inner rim %.2f mm, tread rim %s' % (p['inner_lines'] * lw, tread)
    if p['pattern'] == PAT_GOTHIC:
        s += ', spokes %.2f mm' % (p['g_spoke_lines'] * lw)
    elif p['pattern'] == PAT_CURVED:
        s += ', spokes %.2f mm' % (p['c_spoke_lines'] * lw)
    elif p['pattern'] == PAT_HONEY:
        s += ', cell walls %.2f mm' % (p['h_lines'] * lw)
    used = ['%d %s' % (int(p['a_%s_n' % t]), ANCHOR_NAMES[t]) for t in ('peg', 't', 'dt')
            if int(p.get('a_%s_n' % t, 0)) > 0]
    if used:
        s += ', anchors: ' + ', '.join(used)
    try:
        r0, r1, r2, r3 = ring_radii(p)
        s += ', spoke zone %.2f mm deep' % (r2 - r1)
    except Exception:
        pass
    return s


def refresh(inputs):
    p = read_inputs(inputs)
    inputs.itemById('grp_gothic').isVisible = (p['pattern'] == PAT_GOTHIC)
    inputs.itemById('grp_curved').isVisible = (p['pattern'] == PAT_CURVED)
    inputs.itemById('grp_honey').isVisible = (p['pattern'] == PAT_HONEY)
    inputs.itemById('keep_open').isEnabled = (p['outer_lines'] == 0)
    err, warns = assess(p)
    lines = [summary(p)]
    if err:
        lines.append('PROBLEM (OK disabled): ' + err)
    lines.extend(warns)
    inputs.itemById('info').text = '\n'.join(lines)


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.isExecutedWhenPreEmpted = False
            global _target
            s, src, _target = settings_from_selection()
            if s is None:
                s = load_settings()
            inputs = cmd.commandInputs
            if src:
                inputs.addTextBoxCommandInput('src', 'Loaded from', src, 1, True)
                if _target:
                    rb = inputs.addBoolValueInput('replace', 'Replace selected tire', True, '', False)
                    rb.tooltip = ('Build the new tire in the same place and parent, then delete the old one. '
                                  'Features elsewhere that use the old tire (e.g. Combine cuts) will break. '
                                  'Ctrl+Z undoes the whole replace.')
                else:
                    inputs.addTextBoxCommandInput('noreplace', '', 'Component is used more than once; '
                                                  'select one occurrence to enable Replace.', 2, True)

            dd = inputs.addDropDownCommandInput('pattern', 'Pattern type',
                                                adsk.core.DropDownStyles.TextListDropDownStyle)
            for name in PATTERNS:
                dd.listItems.add(name, name == s['pattern'])
            if dd.selectedItem is None:
                dd.listItems.item(0).isSelected = True

            g = inputs.addGroupCommandInput('grp_tire', 'Tire').children
            g.addFloatSpinnerCommandInput('tire_od', 'Tire OD (mm)', '', 10, 500, 1, s['tire_od'])
            g.addFloatSpinnerCommandInput('bore_d', 'Bore / hub interface D (mm)', '', 1, 490, 1, s['bore_d'])
            g.addFloatSpinnerCommandInput('width', 'Width (mm)', '', 1, 200, 1, s['width'])
            g.addFloatSpinnerCommandInput('line_w', 'Slicer line width (mm)', '', 0.1, 2.0, 0.01, s['line_w'])
            g.addIntegerSpinnerCommandInput('inner_lines', 'Inner rim (lines)', 1, 50, 1, int(s['inner_lines']))
            g.addIntegerSpinnerCommandInput('outer_lines', 'Tread rim (lines, 0 = none)', 0, 50, 1, int(s['outer_lines']))
            ko = g.addBoolValueInput('keep_open', 'No tread rim: keep open', True, '', bool(s['keep_open']))
            ko.tooltip = ('Only with Tread rim = 0. Checked = open tread, unchecked = closed tread. '
                          'Gothic arch: open leaves separate leg tips at the OD; closed joins each arch on the OD. '
                          'Honeycomb: open keeps radial lugs to the OD; closed ends in a zigzag tread. '
                          'Curved spoke: always open (no effect).')
            g.addFloatSpinnerCommandInput('fillet', 'Junction fillet (mm, 0=off)', '', 0, 10, 0.1, s['fillet'])

            gg = inputs.addGroupCommandInput('grp_gothic', 'Gothic arch')
            c = gg.children
            c.addIntegerSpinnerCommandInput('g_count', 'Arch count', 3, 360, 1, int(s['g_count']))
            c.addIntegerSpinnerCommandInput('g_spoke_lines', 'Spoke thickness (lines)', 1, 20, 1, int(s['g_spoke_lines']))
            c.addFloatSpinnerCommandInput('g_bulge', 'Leg bulge (0=straight, 0.45 max)', '', 0, 0.45, 0.01, s['g_bulge'])
            ad = c.addDropDownCommandInput('g_apex', 'Arch apex', adsk.core.DropDownStyles.TextListDropDownStyle)
            for name in (APEX_OUT, APEX_IN):
                ad.listItems.add(name, name == s['g_apex'])
            if ad.selectedItem is None:
                ad.listItems.item(0).isSelected = True
            c.addBoolValueInput('g_interleave', 'Interleave 2nd round (offset 1/2 arch)', True, '',
                                bool(s['g_interleave']))

            cg = inputs.addGroupCommandInput('grp_curved', 'Curved spoke').children
            cg.addIntegerSpinnerCommandInput('c_count', 'Spoke count', 3, 360, 1, int(s['c_count']))
            cg.addIntegerSpinnerCommandInput('c_spoke_lines', 'Spoke thickness (lines)', 1, 20, 1, int(s['c_spoke_lines']))
            cg.addFloatSpinnerCommandInput('c_lean', 'Lean: tread end ahead of hub end (deg)', '', -90, 90, 1, s['c_lean'])
            cg.addFloatSpinnerCommandInput('c_bulge', 'Bulge (+ left / - right, 0.45 max)', '', -0.45, 0.45, 0.01, s['c_bulge'])
            sd = cg.addDropDownCommandInput('c_shape', 'Spoke shape', adsk.core.DropDownStyles.TextListDropDownStyle)
            for name in (SHAPE_C, SHAPE_S):
                sd.listItems.add(name, name == s['c_shape'])
            if sd.selectedItem is None:
                sd.listItems.item(0).isSelected = True
            cg.addBoolValueInput('c_alternate', 'Alternate direction (mirror every other spoke)', True, '',
                                 bool(s['c_alternate']))

            hg = inputs.addGroupCommandInput('grp_honey', 'Honeycomb').children
            hg.addIntegerSpinnerCommandInput('h_count', 'Cells around', 3, 360, 1, int(s['h_count']))
            hg.addIntegerSpinnerCommandInput('h_rows', 'Cell rows (radial)', 1, 10, 1, int(s['h_rows']))
            hg.addIntegerSpinnerCommandInput('h_lines', 'Wall thickness (lines)', 1, 20, 1, int(s['h_lines']))
            hg.addFloatSpinnerCommandInput('h_angle', 'Cell angle (30=hex, 0=brick, <0=auxetic)', '', -45, 60, 1,
                                           s['h_angle'])

            ag = inputs.addGroupCommandInput('grp_anchor', 'Anchors (into bore, count 0 = off)')
            ag.isExpanded = any(int(s['a_%s_n' % t]) > 0 for t in ('peg', 't', 'dt'))
            a = ag.children
            a.addIntegerSpinnerCommandInput('a_peg_n', 'Round pegs: count', 0, 60, 1, int(s['a_peg_n']))
            a.addFloatSpinnerCommandInput('a_peg_dia', '  head diameter (mm)', '', 0.5, 50, 0.1, s['a_peg_dia'])
            a.addFloatSpinnerCommandInput('a_peg_id', '  hole down the rod (mm, 0 = solid)', '', 0, 49, 0.1, s['a_peg_id'])
            a.addFloatSpinnerCommandInput('a_peg_stem_w', '  stem width (mm)', '', 0.2, 50, 0.1, s['a_peg_stem_w'])
            a.addFloatSpinnerCommandInput('a_peg_stem_l', '  stem length, bore to head (mm)', '', 0, 50, 0.1, s['a_peg_stem_l'])
            a.addFloatSpinnerCommandInput('a_peg_phase', '  phase (deg)', '', -180, 180, 1, s['a_peg_phase'])
            a.addIntegerSpinnerCommandInput('a_t_n', 'T-slots: count', 0, 60, 1, int(s['a_t_n']))
            a.addFloatSpinnerCommandInput('a_t_neck_w', '  neck width (mm)', '', 0.5, 50, 0.5, s['a_t_neck_w'])
            a.addFloatSpinnerCommandInput('a_t_neck_d', '  neck depth (mm)', '', 0.5, 50, 0.5, s['a_t_neck_d'])
            a.addFloatSpinnerCommandInput('a_t_head_w', '  head width (mm)', '', 0.5, 50, 0.5, s['a_t_head_w'])
            a.addFloatSpinnerCommandInput('a_t_head_d', '  head depth (mm)', '', 0.5, 50, 0.5, s['a_t_head_d'])
            a.addFloatSpinnerCommandInput('a_t_phase', '  phase (deg)', '', -180, 180, 1, s['a_t_phase'])
            a.addIntegerSpinnerCommandInput('a_dt_n', 'Dovetails: count', 0, 60, 1, int(s['a_dt_n']))
            a.addFloatSpinnerCommandInput('a_dt_root_w', '  root width at bore (mm)', '', 0.5, 50, 0.5, s['a_dt_root_w'])
            a.addFloatSpinnerCommandInput('a_dt_tip_w', '  tip width (mm)', '', 0.5, 50, 0.5, s['a_dt_tip_w'])
            a.addFloatSpinnerCommandInput('a_dt_d', '  depth into bore (mm)', '', 0.5, 50, 0.5, s['a_dt_d'])
            a.addFloatSpinnerCommandInput('a_dt_phase', '  phase (deg)', '', -180, 180, 1, s['a_dt_phase'])
            cb = a.addBoolValueInput('a_cutter', 'Make hub cutter body', True, '', bool(s['a_cutter']))
            cb.tooltip = ('Separate hidden body: the anchors grown by the clearance, tied together by a ring at '
                          'bore - clearance, 1 mm past each face. Combine > Cut (Keep Tools) on the hub carves the '
                          'anchor slots and sizes the hub OD to bore - 2 x clearance.')
            a.addFloatSpinnerCommandInput('a_clear', '  cutter clearance (mm)', '', 0, 2, 0.05, s['a_clear'])

            inputs.addTextBoxCommandInput('info', 'Resulting', '', 5, True)
            refresh(inputs)

            for ev, h in ((cmd.inputChanged, ChangedHandler()), (cmd.validateInputs, ValidateHandler()),
                          (cmd.execute, ExecuteHandler()), (cmd.destroy, DestroyHandler())):
                ev.add(h)
                _dialog_handlers.append(h)
        except Exception:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def all_inputs(args):
    """The command's full input collection. Event args.inputs can be just the
    children of the group holding the changed input, where lookups of inputs
    in other groups return None."""
    try:
        cmd = adsk.core.Command.cast(args.firingEvent.sender)
        if cmd:
            return cmd.commandInputs
    except Exception:
        pass
    return args.inputs


class ChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            refresh(all_inputs(args))
        except Exception:
            pass


class MarkingMenuHandler(adsk.core.MarkingMenuEventHandler):
    """Remember what was selected when the right-click menu opened."""
    def notify(self, args):
        global _menu_pick
        try:
            ents = [args.selectedEntities[i] for i in range(len(args.selectedEntities))]
            _menu_pick = (time.time(), ents)
        except Exception:
            _menu_pick = (0.0, [])


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    """Greys out OK while the settings can't be built, so the dialog stays
    open instead of failing after OK."""
    def notify(self, args):
        try:
            err, _ = assess(read_inputs(all_inputs(args)))
            args.areInputsValid = err is None
        except Exception:
            args.areInputsValid = True


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            p = read_inputs(inputs)
            save_settings(p)
            rb = inputs.itemById('replace')
            if rb and rb.value and _target:
                tgt = _target
                comp, note = build(p, tgt['parent'], tgt['transform'])
                old = tgt['occ']
                want = comp.name
                if old.isValid:
                    old.deleteMe()
                try:
                    comp.name = want  # reclaim the name if Fusion uniquified it
                except Exception:
                    pass
                msg = 'Replaced "%s" with "%s" (v%s).\n%s' % (tgt['name'], comp.name, SCRIPT_VERSION, summary(p))
            else:
                comp, note = build(p)
                msg = 'Created component "%s" (v%s).\n%s' % (comp.name, SCRIPT_VERSION, summary(p))
            if note:
                msg += '\n' + note
            _ui.messageBox(msg, CMD_NAME)
        except TireError as e:
            _ui.messageBox(str(e), CMD_NAME)
        except Exception:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()), CMD_NAME)


class DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        # Add-in stays loaded; just drop this dialog's per-run handlers.
        global _dialog_handlers
        _dialog_handlers = []


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        old = _ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        res = ICON_FOLDER if os.path.isdir(ICON_FOLDER) else ''
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, 'Generate a parametric airless (structured) tire', res)
        h = CreatedHandler()
        cmd_def.commandCreated.add(h)
        _handlers.append(h)
        mm = MarkingMenuHandler()
        _ui.markingMenuDisplaying.add(mm)
        _handlers.append(mm)

        ws = _ui.workspaces.itemById(WORKSPACE_ID)
        panel = ws.toolbarPanels.itemById(PANEL_ID) if ws else None
        if panel:
            ctrl = panel.controls.itemById(CMD_ID)
            if ctrl:
                ctrl.deleteMe()
            panel.controls.addCommand(cmd_def)
    except Exception:
        if _ui:
            _ui.messageBox('Airless Tire Generator failed to start:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        for h in _handlers:
            if isinstance(h, MarkingMenuHandler):
                _ui.markingMenuDisplaying.remove(h)
    except Exception:
        pass
    try:
        ws = _ui.workspaces.itemById(WORKSPACE_ID)
        panel = ws.toolbarPanels.itemById(PANEL_ID) if ws else None
        if panel:
            ctrl = panel.controls.itemById(CMD_ID)
            if ctrl:
                ctrl.deleteMe()
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except Exception:
        pass
