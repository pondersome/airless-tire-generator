# Offline tools

These run with plain Python 3 (standard library only), no Fusion needed. They
import the Fusion add-in straight from `fusion/AirlessTireGenerator`, using the
stub `adsk` package in `fusionstub/`, and exercise its pure-geometry code:
pattern math, validation rules and anchor outlines. Nothing that calls the
Fusion API runs here, so they check the design rules, not the Fusion build.

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
python tools/preview.py [key=value ...] [--out tire.png] [--size 800] [--tread] [--cutter]
```

Renders a PNG of a tire from any settings. Keys are the add-in's `DEFAULTS`
names; `pattern` accepts `gothic`, `curved` or `honey`. It prints the same
summary, warnings and problems the dialog would show.

- `--tread` zooms in on a section of the tread at the top.
- `--cutter` adds the hub cutter outline (inside the bore) in light grey.

Examples:

```
python tools/preview.py pattern=gothic g_count=12 g_interleave=true
python tools/preview.py pattern=honey h_angle=-20 outer_lines=0 --tread
python tools/preview.py a_peg_n=6 a_t_n=6 a_t_phase=30 --cutter
```

Members are drawn as their centrelines at full thickness, so the preview shows
layout and clearances but not fillets or the exact band ends.

## fusionstub/

A minimal stand-in for Fusion's `adsk` package: just the classes the add-in
subclasses at import time. Extend it if the add-in starts subclassing other
Fusion classes at module level.
