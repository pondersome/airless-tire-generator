"""Recording fake of adsk.fusion for dry runs of the add-in's build()
(see tools/dry_build.py). Only the calls build() makes are covered.

Strictness on purpose:
- sketch profiles are found only through shared sketch points (or explicit
  coincident constraints), never by coordinates, so loops must be connected;
- arcs are stored counterclockwise in sketch space, so start/end can swap;
- sketches on the XZ plane have sketch Y = model -Z, like Fusion;
- ARCS_TAKE_SKETCH_POINTS = False makes addByThreePoints reject sketch
  points, to exercise the add-in's fallback.
"""
import math
from . import core

ARCS_TAKE_SKETCH_POINTS = True
LOG = []          # (kind, details) of every feature made, in order


def _log(kind, **kw):
    LOG.append((kind, kw))


class FeatureOperations:
    JoinFeatureOperation = 'join'
    CutFeatureOperation = 'cut'
    IntersectFeatureOperation = 'intersect'
    NewBodyFeatureOperation = 'new'
    NewComponentFeatureOperation = 'newcomp'


class DesignTypes:
    DirectDesignType = 0
    ParametricDesignType = 1


class ExtentDirections:
    PositiveExtentDirection = 1
    NegativeExtentDirection = 2


class DistanceExtentDefinition:
    def __init__(self, v):
        self.distance = v

    @staticmethod
    def create(v):
        return DistanceExtentDefinition(v)


class OffsetStartDefinition:
    def __init__(self, v):
        self.offset = v

    @staticmethod
    def create(v):
        return OffsetStartDefinition(v)


def _cast(cls):
    return staticmethod(lambda x: x if isinstance(x, cls) else None)


# ------------------------------------------------------------------ planes
class ConstructionPlane:
    def __init__(self, kind, z=0.0):
        self.kind, self.z = kind, z      # 'xy' (z offset) or 'xz'
        self.name = kind
        self.isLightBulbOn = True

    def to_sketch(self, p):
        if self.kind == 'xz':
            return core.Point3D(p.x, -p.z, 0)
        return core.Point3D(p.x, p.y, 0)

    def to_model(self, p):
        if self.kind == 'xz':
            return core.Point3D(p.x, 0, -p.y)
        return core.Point3D(p.x, p.y, self.z)


class ConstructionPlaneInput:
    def setByOffset(self, plane, value):
        self.base, self.offset = plane, value.realValue
        return True


class ConstructionPlanes:
    def __init__(self, comp):
        self.comp = comp
        self.items = []

    def createInput(self):
        return ConstructionPlaneInput()

    def add(self, inp):
        if inp.base.kind != 'xy':
            raise ValueError('fake only offsets XY-parallel planes')
        pl = ConstructionPlane('xy', inp.base.z + inp.offset)
        self.items.append(pl)
        _log('plane', z=pl.z)
        return pl


class ConstructionAxis:
    pass


# ------------------------------------------------------------------ sketches
class SketchPoint:
    cast = None

    def __init__(self, sk, p):
        self.sketch = sk
        self.geometry = p
        self.alias = self      # merged by coincident constraints

    def root(self):
        sp = self
        while sp.alias is not sp:
            sp = sp.alias
        return sp


SketchPoint.cast = _cast(SketchPoint)


class _Curve:
    def __init__(self, sk, kind, pts, geometry=None):
        self.sketch, self.kind = sk, kind
        self.startSketchPoint, self.endSketchPoint = pts
        self.geometry = geometry


class SketchCurves:
    def __init__(self, sk):
        self.sketchLines = SketchLines(sk)
        self.sketchArcs = SketchArcs(sk)
        self.sketchCircles = SketchCircles(sk)
        self.sketchFittedSplines = SketchFittedSplines(sk)


def _pt(sk, x, allow_sp=True):
    if isinstance(x, SketchPoint):
        if not allow_sp:
            raise TypeError('sketch point not accepted here')
        if x.sketch is not sk:
            raise ValueError('sketch point from another sketch')
        return x
    if not isinstance(x, core.Point3D):
        raise TypeError('expected Point3D or SketchPoint, got %r' % (x,))
    if abs(x.z) > 1e-9:
        raise ValueError('sketch-space point off the sketch plane: %r' % x)
    return SketchPoint(sk, x)


class SketchLines:
    def __init__(self, sk):
        self.sk = sk

    def addByTwoPoints(self, a, b):
        c = _Curve(self.sk, 'line', (_pt(self.sk, a), _pt(self.sk, b)))
        c.geometry = core.Line3D(c.startSketchPoint.geometry, c.endSketchPoint.geometry)
        self.sk.curves.append(c)
        return c


class SketchArcs:
    def __init__(self, sk):
        self.sk = sk

    def addByThreePoints(self, a, m, b):
        sa = _pt(self.sk, a, ARCS_TAKE_SKETCH_POINTS)
        sb = _pt(self.sk, b, ARCS_TAKE_SKETCH_POINTS)
        if not isinstance(m, core.Point3D):
            raise TypeError('mid point must be a Point3D')
        A, M, B = sa.geometry, m, sb.geometry
        cross = (M.x - A.x) * (B.y - M.y) - (M.y - A.y) * (B.x - M.x)
        if abs(cross) < 1e-12:
            raise ValueError('three-point arc through collinear points')
        pts = (sa, sb) if cross > 0 else (sb, sa)     # stored counterclockwise
        c = _Curve(self.sk, 'arc', pts)
        c.mid = M
        self.sk.curves.append(c)
        return c

    def addByCenterStartSweep(self, center, start, sweep):
        cp = center.geometry if isinstance(center, SketchPoint) else center
        sp = _pt(self.sk, start)
        r = sp.geometry.distanceTo(cp)
        a0 = math.atan2(sp.geometry.y - cp.y, sp.geometry.x - cp.x)
        ep = SketchPoint(self.sk, core.Point3D(cp.x + r * math.cos(a0 + sweep), cp.y + r * math.sin(a0 + sweep), 0))
        pts = (sp, ep) if sweep > 0 else (ep, sp)
        c = _Curve(self.sk, 'arc', pts)
        self.sk.curves.append(c)
        return c


class SketchCircles:
    def __init__(self, sk):
        self.sk = sk

    def addByCenterRadius(self, center, r):
        cp = center.geometry if isinstance(center, SketchPoint) else center
        c = _Curve(self.sk, 'circle', (None, None), core.Circle3D(cp, r))
        self.sk.curves.append(c)
        return c


class SketchFittedSplines:
    def __init__(self, sk):
        self.sk = sk

    def add(self, fit):
        pts = list(fit)
        if len(pts) < 2:
            raise ValueError('spline needs 2+ points')
        a = _pt(self.sk, pts[0])
        b = _pt(self.sk, pts[-1])
        c = _Curve(self.sk, 'spline', (a, b))
        c.fit = [p.geometry if isinstance(p, SketchPoint) else p for p in pts]
        self.sk.curves.append(c)
        return c


class GeometricConstraints:
    def __init__(self, sk):
        self.sk = sk

    def addCoincident(self, a, b):
        if not (isinstance(a, SketchPoint) and isinstance(b, SketchPoint)):
            raise TypeError('fake only supports point-point coincidence')
        if a.geometry.distanceTo(b.geometry) > 1e-6:
            raise ValueError('coincident points too far apart: %r %r' % (a.geometry, b.geometry))
        a.root().alias = b.root()


class ProfileCurve:
    def __init__(self, geometry):
        self.geometry = geometry


class ProfileLoop:
    def __init__(self, curves):
        self.profileCurves = [ProfileCurve(c.geometry) for c in curves]
        self.curves = curves


class Profile:
    def __init__(self, sk, loops):
        self.sketch = sk
        self.profileLoops = core.ObjectCollection()
        for lp in loops:
            self.profileLoops.add(ProfileLoop(lp))


class Profiles:
    def __init__(self, items):
        self._items = items

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]

    def __iter__(self):
        return iter(self._items)


class Sketch:
    def __init__(self, comp, plane):
        self.comp, self.plane = comp, plane
        self.name = 'Sketch'
        self.curves = []
        self.sketchCurves = SketchCurves(self)
        self.geometricConstraints = GeometricConstraints(self)
        self.isComputeDeferred = False

    def modelToSketchSpace(self, p):
        return self.plane.to_sketch(p)

    @property
    def profiles(self):
        """Closed loops of connected curves (by shared sketch points) and the
        regions between concentric circles."""
        out = []
        others = [c for c in self.curves if c.kind != 'circle']
        adj = {}
        for c in others:
            for sp in (c.startSketchPoint.root(), c.endSketchPoint.root()):
                adj.setdefault(id(sp), []).append(c)
        seen = set()
        for c in others:
            if id(c) in seen:
                continue
            comp, stack, nodes = [], [c], set()
            while stack:
                x = stack.pop()
                if id(x) in seen:
                    continue
                seen.add(id(x))
                comp.append(x)
                for sp in (x.startSketchPoint.root(), x.endSketchPoint.root()):
                    nodes.add(id(sp))
                    stack.extend(adj[id(sp)])
            if all(len(adj[n]) == 2 for n in nodes):
                out.append(Profile(self, [comp]))
        groups = {}
        for c in self.curves:
            if c.kind == 'circle':
                ctr = c.geometry.center
                groups.setdefault((round(ctr.x, 7), round(ctr.y, 7)), []).append(c)
        for cs in groups.values():
            cs.sort(key=lambda c: c.geometry.radius)
            out.append(Profile(self, [[cs[0]]]))
            for a, b in zip(cs, cs[1:]):
                out.append(Profile(self, [[a], [b]]))
        return Profiles(out)


class Sketches:
    def __init__(self, comp):
        self.comp = comp
        self.items = []

    def add(self, plane):
        sk = Sketch(self.comp, plane)
        self.items.append(sk)
        return sk

    @property
    def count(self):
        return len(self.items)


# ------------------------------------------------------------------ bodies & features
class BRepBody:
    cast = None
    _n = 0

    def __init__(self, comp, src):
        BRepBody._n += 1
        self.name = 'Body%d' % BRepBody._n
        self.comp, self.src = comp, src
        self.isLightBulbOn = True
        self.edges = []


BRepBody.cast = _cast(BRepBody)


class Bodies:
    def __init__(self):
        self._items = []

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]

    def __iter__(self):
        return iter(list(self._items))


class Feature:
    def __init__(self, bodies):
        self.bodies = Bodies()
        self.bodies._items = bodies


def _new_bodies(comp, src, n=1):
    bs = [BRepBody(comp, src) for _ in range(n)]
    comp.bRepBodies._items.extend(bs)
    return bs


def _profiles_of(x):
    if isinstance(x, Profile):
        return [x]
    if isinstance(x, core.ObjectCollection):
        return list(x)
    raise TypeError('expected profile(s), got %r' % (x,))


class ExtrudeInput:
    def __init__(self, prof, op):
        self.prof, self.op = prof, op
        self.participantBodies = None
        self.startExtent = None

    def setOneSideExtent(self, extent, direction):
        self.extent = extent

    def setDistanceExtent(self, sym, dist):
        self.extent = dist


class ExtrudeFeatures:
    def __init__(self, comp):
        self.comp = comp

    def addSimple(self, prof, dist, op):
        ps = _profiles_of(prof)
        _log('extrude', op=op, profiles=len(ps), dist=dist.realValue)
        if op == FeatureOperations.NewBodyFeatureOperation:
            return Feature(_new_bodies(self.comp, 'extrude', len(ps)))
        return Feature([])

    def createInput(self, prof, op):
        _profiles_of(prof)
        return ExtrudeInput(prof, op)

    def add(self, inp):
        ps = _profiles_of(inp.prof)
        _log('extrude', op=inp.op, profiles=len(ps))
        if inp.op == FeatureOperations.NewBodyFeatureOperation:
            return Feature(_new_bodies(self.comp, 'extrude', len(ps)))
        return Feature([])


class LoftSections:
    def __init__(self):
        self.items = []

    def add(self, prof):
        if not isinstance(prof, Profile):
            raise TypeError('loft section must be a profile')
        self.items.append(prof)
        return prof


class LoftInput:
    def __init__(self, op):
        self.op = op
        self.loftSections = LoftSections()
        self.isSolid = False


class LoftFeatures:
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, op):
        return LoftInput(op)

    def add(self, li):
        secs = li.loftSections.items
        if len(secs) < 2:
            raise ValueError('loft needs 2+ sections')
        if not li.isSolid:
            raise ValueError('loft is not solid')
        ncurves = set(sum(len(lp.curves) for lp in s.profileLoops) for s in secs)
        if len(ncurves) != 1:
            raise ValueError('loft sections differ in curve count: %s' % ncurves)
        zs = [s.sketch.plane.z for s in secs]
        if any(b <= a for a, b in zip(zs, zs[1:])):
            raise ValueError('loft sections not in rising order: %s' % zs)
        _log('loft', sections=len(secs), z=zs)
        return Feature(_new_bodies(self.comp, 'loft'))


class RevolveInput:
    def __init__(self, prof, axis, op):
        self.prof, self.axis, self.op = prof, axis, op
        self.participantBodies = None
        self.angle = None

    def setAngleExtent(self, sym, angle):
        self.angle = angle


class RevolveFeatures:
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, prof, axis, op):
        if not isinstance(prof, Profile):
            raise TypeError('revolve takes one profile')
        return RevolveInput(prof, axis, op)

    def add(self, ri):
        if ri.angle is None:
            raise ValueError('revolve without an angle')
        _log('revolve', op=ri.op, sketch=ri.prof.sketch.name)
        if ri.op == FeatureOperations.NewBodyFeatureOperation:
            return Feature(_new_bodies(self.comp, 'revolve'))
        return Feature([])


class PatternInput:
    def __init__(self, ents, axis):
        self.ents, self.axis = ents, axis


class CircularPatternFeatures:
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, ents, axis):
        return PatternInput(ents, axis)

    def add(self, ci):
        q = int(round(ci.quantity.realValue))
        n = len(list(ci.ents))
        _log('pattern', seeds=n, qty=q)
        return Feature(_new_bodies(self.comp, 'pattern', n * (q - 1)))


class CombineInput:
    def __init__(self, target, tools):
        self.target, self.tools = target, tools
        self.operation = None


class CombineFeatures:
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, target, tools):
        return CombineInput(target, tools)

    def add(self, ci):
        tools = list(ci.tools)
        _log('combine', op=ci.operation, tools=len(tools))
        if ci.operation == FeatureOperations.JoinFeatureOperation:
            gone = set(id(b) for b in tools)
            self.comp.bRepBodies._items = [b for b in self.comp.bRepBodies._items if id(b) not in gone]
        return Feature([ci.target])


class FilletFeatures:
    def createInput(self):
        raise RuntimeError('fake has no edges to fillet')


class Features:
    def __init__(self, comp):
        self.extrudeFeatures = ExtrudeFeatures(comp)
        self.loftFeatures = LoftFeatures(comp)
        self.revolveFeatures = RevolveFeatures(comp)
        self.circularPatternFeatures = CircularPatternFeatures(comp)
        self.combineFeatures = CombineFeatures(comp)
        self.filletFeatures = FilletFeatures()


class Attributes:
    def __init__(self):
        self.d = {}

    def add(self, g, n, v):
        self.d[(g, n)] = v

    def itemByName(self, g, n):
        return None


class Component:
    cast = None

    def __init__(self):
        self.name = 'Component'
        self.description = ''
        self.attributes = Attributes()
        self.sketches = Sketches(self)
        self.features = Features(self)
        self.constructionPlanes = ConstructionPlanes(self)
        self.xYConstructionPlane = ConstructionPlane('xy', 0.0)
        self.xZConstructionPlane = ConstructionPlane('xz')
        self.zConstructionAxis = ConstructionAxis()
        self.bRepBodies = Bodies()
        self.occurrences = Occurrences()


Component.cast = _cast(Component)


class Occurrence:
    cast = None

    def __init__(self, comp):
        self.component = comp
        self.nativeObject = None


Occurrence.cast = _cast(Occurrence)


class Occurrences:
    def addNewComponent(self, m):
        return Occurrence(Component())


class Design:
    cast = None

    def __init__(self):
        self.rootComponent = Component()
        self.designType = DesignTypes.DirectDesignType


Design.cast = _cast(Design)
