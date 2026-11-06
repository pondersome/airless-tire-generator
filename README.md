# Airless Tire Generator

*A Ponderbotics project.*

Parametric airless (structured) tires for 3D printing. Pick a structure, set a
few dimensions, and get a printable tire body plus an optional cutter that keys
it to your own hub design.

Built for robotics wheels (FTC/FRC-scale) printed in flexible filaments such as
TPU and foaming PEBA, but nothing in it is robot-specific.

| Platform | Status | Folder |
|---|---|---|
| Autodesk Fusion add-in | Working (pre-release) | [`fusion/AirlessTireGenerator`](fusion/AirlessTireGenerator) |
| Onshape | If requested | |
| Standalone | If requested | |

## Features

- **Three structures**
  - **Gothic arch**: pointed arches springing from the inner rim, with an
    optional interleaved second round offset by half an arch.
  - **Curved spoke**: C- or S-curved spokes with adjustable lean, optionally
    mirrored every other spoke for the same behaviour in both directions.
  - **Honeycomb**: polar hex cells; cell angle 30 = regular hexagons, 0 = bricks,
    negative = re-entrant (auxetic) cells.
- **Print-aware sizing**: every rim, spoke and cell wall is a whole number of
  slicer lines, so it prints as clean wall loops with no gap fill.
- **Optional tread rim**: with 0 lines the structure itself becomes the contact
  surface, with a choice of open or closed tread.
- **Hub anchors**: round pegs (circle on a stem, running the full width),
  T-slots and dovetails projecting into the bore, each with its own count, size
  and phase.
- **Hub cutter**: a single hidden body of the anchors grown by a clearance,
  ready for Combine > Cut on your hub. It also sizes the hub OD to
  bore - 2 x clearance.
- **Live validation**: problems show in the dialog as you type; only geometry
  that cannot be built blocks OK. Narrow, unprintable gaps are flagged as
  warnings.
- **Record and regenerate**: every tire stores its settings. Select a tire and
  run the command (or right-click > Repeat) to load them, and tick
  *Replace selected tire* to rebuild it in place.
- **Tidy timeline**: each generated tire collapses into one named timeline group.

## Install (Fusion)

1. Download or clone this repository anywhere you like.
2. In Fusion, open **Utilities > Add-Ins**.
3. Click the **+** icon and choose **Script or add-in from device**. (The icon
   is green in light mode but not in dark mode.)
4. Select the `fusion/AirlessTireGenerator` folder.
5. **AirlessTireGenerator** now appears in the Add-Ins list. Select it, click
   **Run**, and tick **Run on Startup**.

Fusion remembers the folder, so the add-in stays in the list and runs the code
in your copy of the repository. The **Airless Tire Generator** button appears in
**SOLID > CREATE**. Hover over it and choose *Pin to Toolbar* to keep it one
click away.

To update, pull or re-download the repository, then **Stop** and **Run** the
add-in in the Add-Ins list (or restart Fusion). If you move the repository,
remove the old entry from the list and add the folder again.

## Using it

1. **SOLID > CREATE > Airless Tire Generator.**
2. Choose a **Pattern type**; only that pattern's settings are shown.
3. Set the **Tire** dimensions:
   - Tire OD, bore (hub interface) diameter, width.
   - Slicer line width (e.g. 0.62 mm for a 0.6 mm nozzle).
   - Inner rim and tread rim thickness, in lines. Tread rim 0 = no outer rim.
   - Junction fillet (0 = off).
4. Optionally add **Anchors** and keep **Make hub cutter body** ticked.
5. Watch the **Resulting** box for thicknesses, warnings and problems, then OK.

A new component named after the settings is created, for example
`Tire Gothic N12x2 OD96`, containing a `Tire` body and, with anchors, a hidden
`Hub cutter` body.

### Keying a hub

The tire's bore is plain apart from the anchors. To key a hub to it:

1. Design the hub with its OD at or above the tire bore.
2. Show the `Hub cutter` body (or select it in the browser).
3. **Combine > Cut**: target = hub, tool = Hub cutter, *Keep Tools* on.

The hub gets every anchor slot at the chosen clearance and its OD is trimmed to
bore - 2 x clearance. Anchors run the full tire width, so the tire slides onto
the hub axially.

If you later regenerate the tire with *Replace selected tire*, the cutter is
rebuilt too and features that used the old one (such as that Combine) need to
be redone.

### Regenerating a tire

Select a generated tire (component, body, or in the canvas) and launch the
command. The dialog opens with that tire's settings. Change them and tick 
**Replace selected tire** to rebuild it at the same position; Ctrl+Z undoes the whole replace.

The settings are also written, readable, into the component's **Properties >
Description**.

## Design notes

- **Lines, not millimeters**: structural thicknesses are counts of slicer lines.
  Set the infill to 0% in the slicer and the structure prints as pure walls.
- **Members that touch are fine**: overlapping spokes or cells simply merge.
  The thing to avoid is a gap narrower than one line, which the slicer can't
  print cleanly; those are flagged as warnings.
- **Foaming filaments**: line width changes with foaming. Print a test spoke,
  measure it, and adjust the line width setting to match.
- **Open tread (tread rim = 0)**: *Keep open* chooses the result. Gothic arch:
  open leaves separate leg tips, closed joins each arch on the OD. Honeycomb:
  open gives radial lugs, closed gives a zigzag tread. Curved spokes are always
  open.

## Offline tools

[`tools/`](tools) has a smoke test of the validation rules and a PNG preview
renderer. Both run with plain Python 3, no Fusion needed:

```
python tools/smoke_test.py
python tools/preview.py pattern=honey outer_lines=0 --tread
```

## Roadmap

- Onshape version (FeatureScript).
- Standalone generator (STL/STEP output without a CAD host).
- More structures and anchor types, driven by testing feedback.

## License

MIT, see [LICENSE](LICENSE).
