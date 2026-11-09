# Offline tools

These run with plain Python 3 (standard library only), no Fusion needed. They
import the Fusion add-in straight from `fusion/AirlessTireGenerator`, using the
stand-in `adsk` package in `fusionstub/`. `smoke_test.py` and `preview.py`
exercise its pure-geometry code (pattern math, validation rules, anchor
outlines); `dry_build.py` also runs its Fusion build against a recording fake
of the API. None of them can show what Fusion's own modelling will do with
the result: that still needs a build in Fusion.

## smoke_test.py

```
python tools/smoke_test.py
```

Runs a list of known cases through the add-in's validation and checks each
outcome (`ok`, `note`, `warn` or `error`, plus expected message text), and
checks that settings saved by older versions migrate correctly. Exits non-zero
on any mismatch, so it is worth running before committing changes to the
add-in. Add a case to `CASES` whenever a rule changes or a bug is fixed.

## preview.py

```
python tools/preview.py [key=value ...] [--out tire.png] [--size 800] [--tread] [--cutter] [--z Z | --side]
```

Renders a PNG of a tire from any settings. Keys are the add-in's `DEFAULTS`
names; `pattern` accepts `gothic`, `curved` or `honey`, `profile` accepts
`flat`, `crowned` or `grooved`. It prints the same summary, warnings and
problems the dialog would show.

- `--tread` zooms in on a section of the tread at the top.
- `--cutter` adds the hub cutter outline (inside the bore) in light grey.
- `--z Z` (tread profiles) draws the slice at height Z mm from the bottom face,
  squeezed as it will be built; `--z deep` picks the most squeezed slice. The
  tire's largest diameter (a grooved tire's lands) shows as a faint circle.
- `--side` draws the half-section across the width instead: rims, the profile,
  and thin lines showing where evenly spaced radii of the flat design end up,
  so you can see the squeeze fade from the tread down to the inner rim.

Examples:

```
python tools/preview.py pattern=gothic g_count=12 g_interleave=true
python tools/preview.py pattern=honey h_angle=-20 outer_lines=0 --tread
python tools/preview.py a_peg_n=6 a_t_n=6 a_t_phase=30 --cutter
python tools/preview.py profile=grooved width=40 pg_contact_w=30 --side
python tools/preview.py profile=crowned pc_crown_r=0 pc_shoulder_r=6 --tread --z deep
```

Members are drawn as their centrelines at full thickness, so the preview shows
layout and clearances but not fillets or the exact band ends.

## dry_build.py

```
python tools/dry_build.py [--strict-arcs] [key=value ...]
```

Runs the add-in's `build()` against the recording fake of Fusion's API and
checks what it would draw: every sketch closes into the profiles the build
expects; on profiled tires each member is sketched at the heights the profile
calls for, with its sides half a wall thickness from where the squeeze puts
its centreline; the tread rim and trim sketches lie on the profile. It prints
what each tire would ask of Fusion (sketches, extrudes, lofts, joins), which
is a fair guide to build time.

With no settings it runs a set of flat and profiled tires; with `key=value`
settings it dry-runs that one tire. `--strict-arcs` makes the fake refuse
sketch points as arc ends, to exercise the add-in's fallback. Exits non-zero
on any failure, so run it with the smoke test after changing the build code.
It catches Python errors and geometry slips, not modelling failures: nothing
is solid-modelled, so lofts, joins and fillets are only recorded.

## step_report.py

```
python tools/step_report.py FILE.step
```

Shows what makes an exported STEP file big: the entity types taking the most
space, the B-spline surface grids, and the B-spline curves by size and
direction (lying across the tire at one height, or running along its axis).
It found the dense spline edges that made an early profiled-tire export
47 MB; the same tire now exports at 12.5 MB. Only reads the file.

## fusionstub/

A stand-in for Fusion's `adsk` package. It holds the event-handler classes the
add-in subclasses at import time, and a recording fake of the API calls
`build()` makes for `dry_build.py`: sketches keep their geometry, profiles
are found only through shared sketch points (stricter than Fusion), sketches
on the XZ plane have Fusion's flipped axes, and arcs are stored
counterclockwise as Fusion stores them. Extend it if the build starts using
other API calls.
