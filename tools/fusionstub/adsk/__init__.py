"""Stand-in for Fusion's `adsk` package, so the add-in can be imported and
exercised outside Fusion.

- Importing: the event-handler base classes the add-in subclasses at import
  time (adsk.core), so smoke_test.py and preview.py can use its pure
  geometry code.
- Dry runs: a recording fake of the API calls build() makes (sketches,
  extrudes, lofts, revolves, patterns, combines), keeping sketch geometry so
  dry_build.py can check it. Nothing is solid-modelled, so it can't say
  whether Fusion's own features will succeed.
"""


def terminate():
    pass


def autoTerminate(value):
    pass
