"""Shared helpers for the offline tools: load the Fusion add-in module with the
stub `adsk` package, and parse key=value setting overrides."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ADDIN_DIR = os.path.join(REPO, 'fusion', 'AirlessTireGenerator')

PATTERN_ALIASES = {
    'gothic': 'Gothic arch',
    'curved': 'Curved spoke',
    'honey': 'Honeycomb',
    'honeycomb': 'Honeycomb',
}
PROFILE_ALIASES = {
    'flat': 'Flat',
    'crown': 'Crowned',
    'crowned': 'Crowned',
    'groove': 'Grooved',
    'grooved': 'Grooved',
}


def load_addin():
    """Import AirlessTireGenerator.py from the Fusion add-in folder without
    writing __pycache__ into it."""
    sys.dont_write_bytecode = True
    for path in (os.path.join(HERE, 'fusionstub'), ADDIN_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)
    import AirlessTireGenerator
    return AirlessTireGenerator


def settings(mod, overrides):
    """DEFAULTS updated with overrides, coerced to each default's type.
    overrides: dict, or a list of 'key=value' strings."""
    if isinstance(overrides, (list, tuple)):
        pairs = {}
        for item in overrides:
            if '=' not in item:
                raise SystemExit('Expected key=value, got %r' % item)
            k, v = item.split('=', 1)
            pairs[k.strip()] = v.strip()
        overrides = pairs
    p = dict(mod.DEFAULTS)
    for k, v in overrides.items():
        if k not in p:
            raise SystemExit('Unknown setting %r. Known: %s' % (k, ', '.join(sorted(p))))
        p[k] = coerce(mod, k, v, p[k])
    return p


def coerce(mod, key, value, default):
    if not isinstance(value, str):
        return value
    if key == 'pattern':
        return PATTERN_ALIASES.get(value.lower(), value)
    if key == 'profile':
        return PROFILE_ALIASES.get(value.lower(), value)
    if isinstance(default, bool):
        return value.lower() in ('1', 'true', 'yes', 'on')
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return value
