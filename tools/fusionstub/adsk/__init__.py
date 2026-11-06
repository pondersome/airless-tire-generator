"""Minimal stand-in for Fusion's `adsk` package so the add-in module can be
imported outside Fusion. Only the pure-geometry parts of the add-in (pattern
math, validation, anchor outlines) can be exercised with it; anything that
touches the Fusion API will fail, by design."""


def terminate():
    pass


def autoTerminate(value):
    pass
