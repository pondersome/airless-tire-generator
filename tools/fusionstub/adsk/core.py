"""Fake of adsk.core: points, collections and value inputs for dry runs, plus
the base classes the add-in subclasses at import time."""
import math


class Point3D:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    @staticmethod
    def create(x=0.0, y=0.0, z=0.0):
        return Point3D(x, y, z)

    def distanceTo(self, o):
        return math.sqrt((self.x - o.x) ** 2 + (self.y - o.y) ** 2 + (self.z - o.z) ** 2)

    def __repr__(self):
        return 'P(%.4f, %.4f, %.4f)' % (self.x, self.y, self.z)


class ObjectCollection:
    def __init__(self):
        self._items = []

    @staticmethod
    def create():
        return ObjectCollection()

    def add(self, x):
        self._items.append(x)
        return True

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]

    def __iter__(self):
        return iter(list(self._items))

    def __len__(self):
        return len(self._items)


class ValueInput:
    def __init__(self, real=None, string=None):
        self.realValue, self.stringValue = real, string

    @staticmethod
    def createByReal(v):
        return ValueInput(real=float(v))

    @staticmethod
    def createByString(s):
        return ValueInput(string=s)


class Matrix3D:
    @staticmethod
    def create():
        return Matrix3D()


class Circle3D:
    def __init__(self, center, radius):
        self.center, self.radius = center, radius


class Line3D:
    def __init__(self, a, b):
        self.startPoint, self.endPoint = a, b


class _EventHandler:
    pass


CommandCreatedEventHandler = _EventHandler
InputChangedEventHandler = _EventHandler
CommandEventHandler = _EventHandler
ValidateInputsEventHandler = _EventHandler
MarkingMenuEventHandler = _EventHandler


class Command:
    @staticmethod
    def cast(x):
        return x


class DropDownStyles:
    TextListDropDownStyle = 0
