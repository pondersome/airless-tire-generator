# Airless Tire Generator: project journey

A record of how this project came to be, what we were trying to do, what we
found and what we decided, so a new session can pick up without losing
context. It is more detailed than a hand-off on purpose: the reasoning behind
decisions and the dead ends matter as much as the final code.

- **Sessions covered:**
  1. 2026-11-03 to 2026-11-06: materials, design exploration and the generator
     up to v1.11 (session id `f3ea792b-2d54-417d-8b42-b8867b25a674`; the raw
     transcript is
     `C:\Users\IronReign\.claude\projects\C--Users-IronReign\f3ea792b-2d54-417d-8b42-b8867b25a674.jsonl`).
  2. 2026-11-06 to 2026-11-09, in this repo: tread profiles, v1.12 to v1.14
     (session id `e6490a10-da98-4e30-8834-a386621eae74`; the raw transcript is
     `C:\Users\IronReign\.claude\projects\D--Documents-GitHub-airless-tire-generator\e6490a10-da98-4e30-8834-a386621eae74.jsonl`).
- **State at the end:** Fusion add-in v1.14, committed (the user approves
  commits). A grooved honeycomb flinger built in Fusion, exported, and is test
  printing; crowned profiles have not been built in Fusion yet. See
  [Open issues](#5-open-issues).

---

## 1. Intent

The project grew out of a materials question. The user wanted to print with
**Siraya Tech PEBA-Air**, a foaming PEBA filament whose hardness depends on
print temperature (hotter = more foaming = softer), for FTC robot wheels. That
led to:

1. Bambu Studio filament profiles for PEBA-Air at each temperature, named by
   the resulting Shore A hardness.
2. A wheel concept: rigid **PC-GF hub** + flexible tire, ideally with a
   **stepped degree of foaming** (hub, firmer core, softer tread).
3. A realisation that **structure beats infill** for controlling tire
   behaviour (like the team's earlier Gothic-arch TPU wheels), which became
4. A **parametric airless tire generator**, first a Fusion script, now a Fusion
   add-in, intended to become a published Ponderbotics project with future
   Onshape and standalone versions.

Design intent that held throughout:

- **Print-aware geometry.** Every structural thickness is a whole number of
  slicer lines, so members print as clean wall loops with no gap fill and 0%
  infill.
- **Hubs are external designs.** Hubs focus on axle and drive geometry; the
  generator supplies the tire and a cutter to carve the matching interface
  into the hub.
- **Mix and match.** Tires print separately from hubs so tires can be swapped.
- **Results-based UI language.** Labels describe the outcome (for example
  "keep open"), not the process ("keep outer segments").
- **Don't block what isn't broken.** Only geometry that truly can't be built is
  an error; printability concerns are warnings.

---

## 2. Background work: PEBA-Air filament profiles (Bambu Studio)

Not part of this repo, but it set the context.

**Source:** MakerWorld model 2148738, "PEBA-Air foaming PEBA infill test 230C
to 270C" (3MF in Downloads as `PEBA_Air_Infil_and_Temp_Test_V2.3mf`). Its five
filament settings were H2C copies of assorted Bambu profiles (PETG HF, TPU 90A,
95A, 95A HF, Generic TPU), not "TPU 85A" as Studio displayed on the user's H2D.

**Hardness and settings (Siraya chart via search summary; Siraya's site
rate-limited direct fetches):**

| Profile | Nozzle | Flow (from project) | Shore A |
|---|---|---|---|
| PEBA-Air-95 | 230 C | 1.00 | ~95A |
| PEBA-Air-81 | 240 C | 0.92 | ~81A |
| PEBA-Air-76 | 250 C | 0.82 | ~76A |
| PEBA-Air-74 | 260 C | 0.72 | ~74A |
| PEBA-Air-70 | 270 C | 0.66 | ~70A |

Shared from the project: 6 mm3/s max volumetric speed, 0 retraction, fans 50%
fixed, aux fan off, no slowdown for layer cooling, ramming 3, prime 45/60,
pre-cooling 200 C. Bed was 100 C in the project; **later lowered to 65 C**.
Siraya recommends a 0.6 mm nozzle; reported flow at 270 C is lower (0.53-0.57)
than the project's 0.66.

**How the profiles ended up structured (after several iterations):**

- Studio's **Filament management** tab only lists filaments created through
  the **Create Filament** wizard (cloud-registered). Hand-written JSON
  profiles, even standalone ones with their own `P...` filament_id, appeared
  in dropdowns but not in that tab.
- Final structure: the wizard-made parent **`Siraya  Tech TPU PEBA-Air @Bambu
  Lab H2D 0.6 nozzle`** (note the double space typed in the wizard; left as is
  because the name is cloud-registered) holds all shared PEBA settings, default
  250 C / 0.82. Five child presets `PEBA-Air-95/81/76/74/70` in
  `...\BambuStudio\user\3894606953\filament\` inherit from it and override only
  temperature, flow, colour and notes. They kept their original cloud
  setting_ids so cloud records were updated rather than orphaned.
- The wizard's 0.8 nozzle twin was left for the user to delete in Filament
  management (deleting the file alone would be re-pulled from the cloud).
- Studio was upgraded to 2.9.0.74 mid-way; its first sync re-pulled the old
  cloud copies into `filament\` while flattened copies sat in `filament\base\`,
  creating duplicates that had to be untangled.

**Printer-side lessons:** the printer only knows a slot's filament type, colour,
temperature range and K value. Assign the parent filament to the H2D external
spool (TPU can't go through the AMS). All children share one filament_id, so
name K-calibration results per temperature and switch them on the slot.
Lowering the range on the slot can tame foaming ooze during load/unload.

**Bambu Studio details learned:** `.info` files hold `sync_info`
(create/update), `setting_id`, `base_id`, `updated_time`; Studio's cloud
timestamps ran ~7 h ahead of the local clock, so local edits needed a stamp past
the cloud's to win. Prime tower position is saved per plate; it moves when the
tower grows, the printer changes, or Arrange runs.

---

## 3. Design exploration that shaped the generator

- **Different hardness in one part.** Two hardnesses of PEBA need two nozzles
  at different temperatures, but the H2D's **left nozzle isn't suitable for
  flexibles**. Options considered: rigid core on the left + PEBA on the right;
  one temperature with structure doing the stiffening; per-layer/feature
  temperature switching via G-code post-processing (possible but slow, oozy,
  fuzzy boundaries); separate prints assembled.
- **Speed-driven foaming** (unverified for PEBA-Air): foaming depends on time
  in the melt zone, so slower volumetric flow may foam more at the same
  temperature; per-part speed modifiers could make a firm core and soft tread
  in one temperature. Suggested coupon tests (weigh coupons; weight tracks
  foaming better than durometer on small parts). Not yet tested.
- **PC-GF hub** (TINMORRY PC GF) works; slicer interlocking between PC-GF and
  TPU/PEBA tested well, but the team chose **separate prints** to mix and match
  tires.
- **Slicer modifiers**: a cylinder modifier with its own wall count gives walls
  on the inner (hub) surface and none on the outer (open gyroid grip) surface.
  The user hadn't used modifiers before and found them promising.
- **Infill symmetry**: no Bambu infill is truly radial; triangle-based lattices
  (triangles, tri-hexagon, honeycomb) are in-plane isotropic, gyroid nearly so;
  grid/rectilinear give lumpy 4-fold behaviour.
- **Turn to structure**: the team's earlier red TPU wheels
  (ironreignrobotics.org, 2022-03-19 "solve tip issues", NinjaFlex + nylon,
  Gothic arch design inspired by Monash University rover wheels) prompted
  designing structure directly instead of relying on infill.
- **Fusion interlock scripts**: nothing ready-made fit; native parametric
  approach documented (user parameters, pattern / pattern on path, Combine Cut
  with Keep Tools, Offset Face for clearance). This later became the add-in's
  anchors + hub cutter.
- **Release agent**: PEBA bonds hard to PEI like TPU; glue stick as a release
  layer, lower bed temp, cool fully before removal. (General knowledge; Siraya's
  own advice wasn't retrievable at the time.)

---

## 4. The generator: architecture and decisions

### Current form (v1.14)

- **Location:** `fusion/AirlessTireGenerator/AirlessTireGenerator.py` (single
  file, ~2250 lines), `.manifest`, `resources/16x16.svg`, `32x32.svg`.
  `last_settings.json` (per-user dialog memory) is git-ignored.
- **Add-in**, runs on startup, button in **SOLID > CREATE** next to Spur Gear.
  Installed by linking the repo folder in **Utilities > Add-Ins > + > Script or
  add-in from device**. `Shift+S` opens the Add-Ins dialog for Stop/Run cycles.
- **Command ID** `Ponderbotics_AirlessTireGenerator`; attribute group
  `PonderboticsAirlessTire` (legacy groups `IronReignStructuredTire`,
  `IronReignWheelGenerator` still read). Manifest id
  `5ab69ea8-d574-432b-8a39-e49cf2b644a5` (keep it fixed from now on).
- **Offline tools** in `tools/` (plain Python 3, no Fusion):
  - `smoke_test.py`: 58 checks of validation rules, profile maths and
    migrations, all pass.
  - `preview.py`: PNG renderer; `--z` draws a squeezed slice of a profiled
    tire, `--side` the half-section across the width.
  - `dry_build.py`: runs `build()` against the recording fake API and checks
    the sketches it would make; run it with the smoke test after build changes.
  - `step_report.py`: shows what makes an exported STEP file big.
  - `fusionstub/`: `adsk` stand-in, now a recording fake of the API calls
    `build()` makes. `_harness.py`: shared loading and settings parsing.

### Geometry model

Top view on XY, extruded +Z by width:
`bore r0 .. inner rim .. r1 .. structure .. r2 .. tread rim .. r3 (OD)`.

- Every member is a band of thickness `lines x line_w`, built from leg dicts
  (`kind` line/arc, centre, radius, sweep, sampled centreline).
- Leg ends are **buried mid-rim** so unions are clean; spokes must therefore be
  thinner than both rims.
- **Pattern type is the first choice** and decides which parameter group shows.

**Patterns:**

- **Gothic arch**: N arches, legs bow away from the arch axis (sagitta =
  bulge x chord, bulge < 0.45), apex toward tread or hub, optional **interleave**
  (second round offset by half an arch; the user's original wheels had this).
- **Curved spoke**: count, spoke lines, lean (tread end ahead of hub end), bulge
  (signed), C or S shape (S = two arcs with smooth inflection), alternate
  (mirror every other spoke, needs even count; mirrored neighbours may cross to
  make V/X lattices).
- **Honeycomb**: polar zigzag lines + radial walls; cells around, rows, wall
  lines, cell angle (30 hex, 0 brick, negative auxetic). Angle exact at
  mid-zone; walls straight chords with 0.3 t overlap at 3-way corners.

**Tread rim = 0** (no outer rim): structure runs past the OD and a final
**Tread trim** cut makes a clean cylinder. **Keep open** (results-based):

| Pattern | Keep open on | Keep open off (default) |
|---|---|---|
| Gothic | apex past OD, trimmed: separate leg tips | apex on OD: closed arch with small land |
| Honeycomb | outer radial walls kept to OD: open lugs | last zigzag on OD: closed zigzag tread |
| Curved | always open | always open |

**Anchors** (into the bore, full tire width, joined to the tire, not filleted):

- **Round pegs**: in the sketch, a circle (head, optional hole down the rod)
  joined to the bore by a rectangular **stem** ("keyhole"); extruded, the head
  is a rod running through the width. Params: head diameter, hole, stem width,
  stem length, count, phase.
- **T-slots**: neck width/depth, head width/depth.
- **Dovetails**: root width at bore, tip width (must be wider), depth.
- **Hub cutter**: anchors grown by the clearance, 1 mm past each face, tied
  together by a **ring from bore - clearance to the anchor roots**, so it is one
  connected body. Combine > Cut on the hub carves the slots and sizes the hub
  OD to bore - 2 x clearance. Hidden by default.

**Tread profiles** (v1.12 to v1.14) shape the tire across its width; Flat is
the default, so older settings load unchanged:

- **Crowned**: crown width, crown radius (0 = flat crown), shoulder radius.
  The shoulders run on tangentially from the crown edges to the faces. Tire
  OD is the crown, the largest diameter.
- **Grooved**: ball diameter and contact width give a centred circular groove
  of the ball's radius, with flat lands either side. **Tire OD is the groove
  bottom**, the working surface, held constant in A/B tests for constant
  surface speed; the lands come out at OD + 2 x depth (`build_params`).
- **The squeeze**: the pattern is laid out at the largest diameter (the crown,
  or the lands) and only ever compressed. At each height the bore and inner
  rim stay put, the spoke zone scales in proportion (`radial_map`), the tread
  rim moves with the surface keeping its line count, and member centrelines
  are mapped then re-thickened, so every wall stays whole slicer lines.
- **Build**: flat zones of the width are extruded; curved zones are lofted
  per seed member through sections (at most 8 mm and 20 degrees of surface
  turn apart, with a section at every arc junction); each member's pieces are
  fused before the circular pattern. The tread rim is a revolve of the exact
  profile; an open tread is trimmed by a revolve cut. Bands are drawn as
  simply as the geometry allows (`band_shape`): exact lines and arcs where
  unsqueezed, straight lines where the squeeze bends a straight wall less
  than 0.01 mm, otherwise splines through 9 points.
- The Resulting box shows the drops, the edge or lands OD, the steepest
  angle and the spoke zone depth at both ends; the completion message
  reports build time per phase.

**Validation** (live, in the dialog): errors disable OK; warnings don't.

- Errors: spoke >= rim thickness, odd count with alternate, honeycomb walls that
  collapse (h <= t/2) or zigzags no longer than thick, stem >= head, rod wall
  < 1 line, stem reaching into the hole, dovetail tip <= root, T head <= neck,
  dovetail sides converging in the rim, anchors within 2 mm of centre, rows
  that don't fit, spoke zone < 2 mm.
- Warnings/notes: members that **touch/overlap** (note: they merge), gaps
  **narrower than one line** (warning: unprintable sliver, fillets may fail),
  short or tiny cells, anchors overlapping or crowding at tips.
- Profile errors: crown radius not more than half the crown width; shoulders
  that would turn past vertical before the faces (the message gives the
  minimum radius); crown or groove wider than the tire; groove as wide as the
  ball; under 2 mm of spoke zone where the squeeze is deepest (for a groove,
  that is the zone at the given OD).
- Profile checks: cell checks re-run where the squeeze is deepest; gaps
  between neighbours are **followed through the whole squeeze**, because
  squeezing flattens bowed members and can open gaps as well as close them,
  and a sub-line gap at any height is reported with its heights
  (`at z = a and b mm`); slopes past 45 degrees from vertical warn on either
  shoulder. Warnings on profiled tires say where they apply (at the crown,
  the lands, the faces or the groove bottom).

**Records and regen:**

- Full settings JSON stored as a component attribute; readable summary in
  component Description (`AirlessTireGenerator 1.11: pattern=...; ...`).
- Selecting a generated tire (component, body, or right-click > Repeat) loads
  its settings; **Replace selected tire** rebuilds in the same parent and
  transform, deletes the old occurrence after success, single undo step.
- `migrate()` translates older settings (keep_outer -> keep_open with the
  Gothic inversion; square pegs -> round; missing stem width; a grooved OD
  stored by pre-release v1.12 at the lands -> the groove bottom).
- Names carry the profile: `Tire Honey N64 R2 A30 OD88 grooved D72 C30 norim
  open` (ball 72 mm, contact 30 mm), always with the OD as entered.
- Each tire's timeline items are collapsed into one **named timeline group**.

### Key decisions and why

| Decision | Why |
|---|---|
| Thickness in slicer lines | Clean wall loops, no gap fill, predictable printing |
| Bury leg ends mid-rim | Robust unions without fiddly trimming |
| One sketch per seed leg, then pattern (structure) | Selecting all profiles of a shared sketch filled arch interiors |
| Anchors drawn as all copies in one sketch (no body pattern) | Body-pattern copies couldn't be reliably collected |
| Join by "every body except the tire" | `feature.bodies` and entity tokens proved unreliable |
| Cutter ring | Fusion splits non-touching pieces into separate bodies; a ring makes one body and sizes the hub OD |
| Script -> add-in | Scripts unload after the dialog, so Repeat did nothing and no toolbar button was possible |
| Checks in validateInputs | Errors raised in Execute closed the dialog |
| Touching members = note, sub-line gap = warning | The old rule blocked valid designs (doubling arch count); real risk is unprintable gaps |
| "Keep open" label, Gothic inverted | Label should describe the result, consistent across patterns |
| Rename: Wheel -> Structured Tire -> Airless Tire Generator | "Airless" is more approachable, if less precise |
| Ponderbotics branding, pondersome account | Team credit to be added once they test and give feedback |
| `fusion/` subfolder | Room for future `onshape/` and standalone versions |
| No commits without approval; no AI attribution | Standing user rules |
| Profiles squeeze the 2D design radially; bore and inner rim fixed | Tire presses onto the hub (side plates keep alignment); spreads the deformation through the structure instead of only trimming the tread |
| Re-thicken members after mapping | Walls stay whole slicer lines at every height |
| Lay out at the largest diameter, only compress | One direction of deformation; the unsqueezed slice is the design as entered |
| Grooved OD = groove bottom | It is the working surface; A/B tests hold surface speed while varying the groove |
| Radii and widths as inputs, drops shown as results | Usual tire-profile terms; the ball is a radius anyway |
| Extrude flat zones, loft curved ones, split at corners | Exact geometry where flat; one loft would round off the groove-edge corner |
| Fuse each member's pieces before patterning | Splitting at the lands had tripled the bodies in the pattern and join |
| Lines and arcs wherever the geometry allows | Spline edges made a 47 MB STEP (16 min Bambu import); now 12.5 MB |
| Follow gaps through the whole squeeze | Squeezing flattens bowed members and can open gaps, not just close them |
| Steepness warning on both shoulders | Thin walls with open space either side overhang whichever way they lean |
| 3MF for slicing | Bambu Studio converts STEP geometry itself (slow); meshes import quickly |

### Fusion API lessons (hard-won)

- **Selecting all profiles** in a sketch with touching outlines includes the
  enclosed regions between them.
- **`ExtrudeFeature.bodies` can report only one body** for a multi-profile
  new-body extrude.
- **`entityToken` is not stable** between reads; don't use it to diff body sets.
- **Fusion won't keep disjoint lumps in one body.** Combine Join of
  non-touching bodies succeeds but leaves them separate.
- **InputChanged `args.inputs` is only the changed input's group** when the
  input is inside a group; lookups of other inputs return None. Use
  `Command.cast(args.firingEvent.sender).commandInputs`.
- **Spinner values past their max show "invalid expression"** with no
  explanation (honeycomb 128 cells vs max 120).
- **Right-click > Repeat clears the active selection** before commandCreated;
  capture `markingMenuDisplaying` `selectedEntities` instead.
- **Scripts terminate after the dialog**, so Repeat and toolbar buttons need an
  add-in.
- **Timeline**: one design timeline; activating a component doesn't separate
  it. Use `timeline.timelineGroups.add(start, end)` with `markerPosition`.
- **Variable shadowing**: reusing `g` for curve geometry clobbered the pattern
  result (TypeError on tread trim).
- Stop/Run reloads add-in code; the confirmation message shows the version that
  ran.
- **Sketch fitted splines are expensive downstream.** Edges built from them
  export to STEP as rational degree-5 B-splines of about 80 control points;
  4,096 such edges were 85% of a 47 MB file. Use lines and arcs wherever the
  geometry allows.
- **Bambu Studio converts STEP geometry itself.** That 47 MB file took about
  16 minutes to import, looking stalled at 20% with little CPU in use. A 3MF
  from right-click > **Save As Mesh** imports quickly (and Bambu Studio's own
  projects are 3MF).
- Worked first time for profiled tires: lofts through sketches on offset
  construction planes, revolves from XZ-plane sketches (drawn through
  `modelToSketchSpace`), and joining bodies that touch on identical faces.

---

## 5. Open issues

1. **Slicing ultra-fine honeycomb** (128 cells, 3 rows, 1-line walls, 88 mm OD,
   64 mm bore, 40 mm wide, open tread, 12 pegs). Bambu Studio warns of
   "floating regions" and shows white specks within the honeycomb; Arachne
   comes closest; Classic + detect thin walls drops whole spoke sections. Anchors
   and inner rim slice fine.
   - Established: Bambu's warning targets floating parts/cantilevers; the
     maintainer on Bambu issue #4997 advises checking G-code from below or
     layer by layer. The meaning of the white colour was **not** confirmed;
     check the preview legend in Line Type view.
   - Hypothesis (unproven): 1-line walls sit at the slicer's thin-wall
     threshold and drop out on some layers.
   - Proposed tests: step layers through a speck; regenerate with the
     generator's line width at 0.68 while slicing at 0.62. If that fixes it,
     add a "wall margin" setting.
   - Lesson from this session: research before explaining slicer behaviour.
2. **PEBA-Air speed-vs-foaming** coupon tests not yet run.
3. **Single-line-wall printability** generally (feeds into issue 1).
4. Untested in Fusion so far: fillets on dense structures, anchors + fillets on
   all patterns, **fillets on profiled tires** (junctions along lofted members
   need the new edge selection), and **crowned profiles** (only grooved has
   been built).
5. **Grooved flinger test print** in progress: `Tire Honey N64 R2 A30 OD88
   grooved D72 C30 norim open`. Whether that design is right depends on the
   parameters and the material, not the generator; results to come.
6. **Profiled build speed.** Not measured in detail yet (the completion message
   now reports per-phase times); the flat 128-cell honeycomb took about 4
   minutes. Most of the cost is expected in joining lofted (freeform) members.
   Untried ideas: fuse each repeating unit into one body before patterning (128
   bodies in the join instead of 1,664), or pattern features with Fusion's
   identical-compute option.
7. A profiled honeycomb's STEP is still 12.5 MB, mostly 1,280 seam curves where
   lofted members meet (computed by Fusion's kernel). 3MF is the route for
   slicing.
8. **A/B nuance:** the pattern is laid out at the lands, so with the groove
   bottom held constant the cells there shift slightly as the groove changes
   (the spoke zone depth there stays constant). Laying the pattern out at the
   groove bottom instead would make them identical; not needed so far.

## 6. Next steps (as discussed)

- Test print results for the grooved flinger; A/B groove depth and width at a
  constant groove-bottom OD.
- Build a crowned tire in Fusion; try fillets on a profiled tire.
- Resolve the honeycomb slicing issue (tests above), possibly add wall margin.
- Later profile options: parabolic or conformity-based easing of the groove
  (groove radius slightly larger than the ball starts contact in the middle;
  smaller touches both edges first and self-centres), a groove plus rounded
  shoulders, an off-centre groove, asymmetric profiles.
- Push the tread-profiles commit (the initial import is already on origin).
- README screenshots (`docs/images`).
- Possible: dev auto-reload (core module reloaded per run), split a Fusion-free
  core module for Onshape/standalone reuse (the profile maths is already pure
  Python), App Store later.
- Team credit in README once testing starts.

## 7. Where things are

- Repo: `D:\Documents\GitHub\airless-tire-generator` (origin
  `https://github.com/pondersome/airless-tire-generator.git`, branch `main`;
  commits: the initial import, pushed, then the tread profiles, not yet pushed).
- Fusion links the repo folder directly; no copy in `%APPDATA%\...\API\AddIns`.
- Bambu user filaments: `C:\Users\IronReign\AppData\Roaming\BambuStudio\user\3894606953\filament\`.
- Exports used to diagnose STEP size, in `Downloads`: `Tire Honey N64 R2 A30
  OD88 grooved D72 C30 norim open.step` (v1.13, 47.1 MB) and `... (1).step`
  (v1.14, 12.5 MB), plus the 3MF that was sliced.
- Session scratchpads are temporary and may be cleared. Session 1's held
  backups of every add-in version (`StructuredTireGenerator.v08.bak` ...
  `v16.bak`), the old script and add-in folders, PEBA profile backups and
  render images. Everything worth keeping from session 2 (the fake API, the
  dry run, the STEP report) moved into `tools/`.

---

## 8. Step by step

Each step is the user's input (lightly trimmed, wording kept) and a synopsis of
the response. Version numbers refer to the generator.

### Part A: PEBA-Air filament profiles

1. **User:** Can't find a JSON filament profile for Siraya Tech PEBA-Air. A
   MakerWorld project has definitions for different temperatures, but they're
   all TPU 85A with different temps and colours. Extract them into custom user
   filaments named PEBA-Air-nn, where nn is the effective Shore A at each temp.
   Wants persistent filament definitions, not the project geometry. Gave the
   user filament folder.
   **Response:** Extracted the five filament configs from the 3MF (they were H2C
   copies of PETG HF / TPU 90A / 95A / 95A HF / Generic TPU), found Siraya's
   temperature-hardness chart (95/81/76/74/70A), and wrote five presets
   inheriting from Bambu TPU 85A @BBL H2D (0.6/0.8 nozzles) with the project's
   temperatures, flows, fans, beds and retraction.

2. **User:** How do I push the profiles to the H2D so it has a good definition
   for loading, unloading, etc.?
   **Response:** The printer only knows slot info (type, colour, temp range, K);
   profiles sync via the cloud and are assigned to a slot in the Device tab or
   Handy. Use the external spool (no TPU in AMS); watch foaming ooze; recalibrate
   K per temperature.

3. **User:** Restarted Studio; check if they synced. They don't show up in
   Filament management.
   **Response:** They had synced (cloud setting_ids appeared). Diagnosed them as
   variants of Bambu TPU 85A without their own filament_id; flattened them into
   standalone presets with their own `P...` ids (prepared while Studio was
   running, installed after it was closed), marked for cloud update.

4. **User:** Studio is closed, go ahead.
   **Response:** Installed the flattened presets, fixed `updated_time` so local
   edits would beat the cloud's (cloud stamps ran ahead of local time).

5. **User:** They show in the nozzle dropdowns but not in Filament management.
   **Response:** Found no local data for that tab; suspected it lists cloud or
   wizard-made filaments. Asked whether INLAND/TINMORRY showed there.

6. **User:** Don't see INLAND either.
   **Response:** Concluded the tab doesn't list arbitrary user filaments;
   suggested re-saving to push sync.

7. **User:** TINMORRY does show up.
   **Response:** Compared files: INLAND and TINMORRY are structurally identical,
   so the tab must follow cloud registration from the Create Filament wizard.
   Suggested creating PEBA-Air via the wizard.

8. **User:** Created PEBA-Air with the wizard (it added TPU to the name, based
   on 85A); it shows up in Filament management.
   **Response:** Found the wizard parent (double space in "Siraya  Tech") and
   that Studio had re-pulled old cloud copies into `filament\`, duplicating the
   flattened ones. Proposed restructuring: shared settings in the wizard parent,
   five children inheriting from it, reusing cloud ids, removing duplicates.

9. **User:** Mix-up might be from upgrading Studio mid-conversation; there may be
   new default file locations. Drop the 0.8 nozzles. Proceed.
   **Response:** Confirmed the layout was unchanged (Studio 2.9.0.74); applied
   the restructure (parent 250 C / 0.82 default, children override temp, flow,
   colour, notes), backed everything up; left the wizard's 0.8 parent to delete
   in the UI.

10. **User:** Studio open; check sync. Only the Siraya parent shows in Filament
    management; could select it in Handy for the right extruder; earlier
    versions still show as custom filaments.
    **Response:** All six synced; the "earlier versions" are the children (same
    names, now inheriting). Assign the parent to the slot, pick children in the
    slicer, calibrate K per temperature.

11. **User:** So do the temperature profiles all share the same flow rate?
    **Response:** No, each child has its own flow ratio (1.00 to 0.66); the K
    value is what's shared via the filament id, so save named K results per
    temperature.

### Part B: from material to structure

12. **User:** Could one part have different hardnesses, e.g. a tire with a
    harder inner section and a thin, maximally soft surface for grip?
    **Response:** Yes with two nozzles at different temps (PEBA in both), via
    per-feature filament assignment or two-body parts; caveats on nozzle sizes,
    spools, foaming in thin sections.

13. **User:** Prefers the two-body approach, but the left nozzle isn't good for
    flexibles.
    **Response:** Options: rigid core left + PEBA tread right; single temp with
    structure; per-layer temperature switching by G-code (slow, oozy); separate
    prints assembled.

14. **User:** Has PC-GF for the rigid hub; the tire core was meant to interface
    via interlocking geometry or slicer settings. Previously printed a TPU tire
    with no walls, using rough gyroid as the contact surface. With PEBA wants
    stepped foaming: hub, core, tread.
    **Response:** Proposed speed-driven foaming at one temperature (per-part
    speeds) versus in-layer temperature switching by post-processing; suggested
    coupon tests and weighing coupons.

15. **User:** Does PEBA need a release agent on textured PEI like TPU?
    **Response:** Probably; glue stick, lower bed, cool fully; noted the
    profiles used 100 C bed. (General knowledge, flagged as such.)

16. **User:** Studio closed; lower the bed to 65.
    **Response:** Set all plate temps to 65 C on the parent, marked for sync;
    noted Studio uses the highest bed temp when PC-GF shares the plate.

17. **User:** Does Studio automatically move the prime tower on each load?
    **Response:** No; it's saved per plate but moves on Arrange, size growth,
    printer/nozzle change, or H2D reach limits.

18. **User:** Slicer interlocking works between PC-GF and TPU/PEBA, but going
    back to separate prints to mix and match. Can one surface print without
    walls (outer open gyroid for grip) and the inner with walls (to strengthen
    pin and socket interlocking)?
    **Response:** Yes: object wall loops 0 plus a cylinder modifier with 3-4
    walls over the hub zone; notes on the internal ring wall and custom modifier
    shapes.

19. **User:** Didn't know about modifiers. Any Fusion scripts that generate
    interlock patterns (T-slots, pin and slot, dovetails) from parameters,
    ideally on curved boundaries, at sketch or body level?
    **Response:** Nothing ready-made fit (Hirth joint, straight dovetail
    generators); described a native parametric Fusion workflow; offered a
    script.

20. **User:** Which infill patterns are radially symmetric? Concentric can't
    push against compression at part edges.
    **Response:** Only Archimedean chords / octagram spiral are centred, and
    weak radially; recommended in-plane isotropic triangle lattices or gyroid
    instead, and real spokes for radial behaviour.

21. **User:** Thinking of leaning away from infill toward structure, like the
    red TPU wheels on the team site.
    **Response:** The page described NinjaFlex + nylon Gothic arch wheels (from
    Monash rover wheels). Compared structures (Gothic arch, curved spoke,
    honeycomb, chevron), design rules (thickness = whole lines, fillets, tread
    band), and offered a Fusion generator.

### Part C: building the generator (script era, v0.1 to v0.9)

22. **User:** Start with the Gothic arches script; pattern type may become the
    first choice that informs the remaining parameters.
    **Response:** Wrote `WheelGenerator` (Scripts folder): dialog with pattern
    dropdown first, shared wheel group, Gothic group; thickness in lines;
    validation; fillets; settings memory. Tested geometry offline with stubs and
    PNG renders.

23. **User:** Two issues: the arch extrude includes the interiors (spokes
    filled in), and the real pattern has two interleaved rounds; add a checkbox
    to repeat the pattern offset by half an arch.
    **Response:** Interiors came from selecting every profile of a shared
    sketch; switched to one sketch per seed leg plus circular pattern. Added the
    interleave checkbox (default on).

24. **User:** Looks good; on to the curved spoke profile.
    **Response:** Added curved spokes (count, lines, lean, signed bulge, C/S
    shape, alternate). Relaxed the neighbour check for alternate mode so
    mirrored spokes can cross.

25. **User:** Now the honeycomb pattern.
    **Response:** Added polar honeycomb (cells, rows, wall lines, cell angle,
    auxetic when negative); default cells raised to 28 for the shallow zone;
    re-entrant collision check.

26. **User:** Can the chosen parameters be stored in the created component, at
    least for record keeping?
    **Response:** Stored full JSON as a component attribute and a readable
    Description; selecting a generated wheel preloads its settings.

27. **User:** Add the replace selected option.
    **Response:** Added Replace selected wheel: same parent and transform, delete
    old after success, single undo, disabled when a component is used more than
    once.

28. **User:** Replace works. Rename the script to Structured Tire Generator,
    rename the Wheel section to Tire, and support tread rim = 0 (no outer rim;
    the structure is the contact surface).
    **Response:** Renamed (new folder, legacy attribute group still read), made
    tread rim optional with overshoot plus a Tread trim cut, honeycomb layout
    stretched to the OD, fillets excluded at the trim.

29. **User:** TypeError on line 593: Circle3D object is not subscriptable.
    **Response:** Variable `g` shadowed by curve geometry in the rim-profile
    loop; renamed and captured the spoke thickness early.

30. **User:** Rim 0 removes the outer spoke segments: Gothic gets an open,
    gappy profile, honeycomb a closed surface with triangle bumps. Both are
    interesting; wants a toggle to preserve outer segments.
    (Interrupted to ask how to paste images; **Alt+V** works on Windows.)
    **Response (after the user's screenshot of the open Gothic tread):** legs of
    an arch met past the OD and were trimmed apart. Added the toggle: Gothic
    apex on the OD (closed), honeycomb keeps outer walls (open lugs).

31. **User:** Keep outer works, but rename to "keep open" (label based on
    results); invert the Gothic meaning accordingly.
    **Response:** Renamed to keep_open, inverted Gothic, added migration of saved
    and stored settings, names "norim open/closed".

32. **User:** Warnings like "Neighbouring arches come within 0.31 mm..." close
    the dialog on OK; doubling arch count hit this, and the restriction seems
    unreasonable unless it prevents an error.
    **Response:** Moved checks into validateInputs (dialog stays open, OK
    disabled only for real errors). Replaced the clearance rule: touching =
    note (members merge), sub-line gap = warning; honeycomb short walls became
    warnings.

### Part D: add-in era (v1.0 to v1.8)

33. **User:** Right-click shows "Repeat Structured Tire Generator" but it
    doesn't open the dialog; wants the tool in SOLID > CREATE like Spur Gear.
    **Response:** Converted to an add-in (stays loaded, button in
    SolidCreatePanel, SVG icons, runOnStartup); removed the script copy since it
    shared the command id.

34. **User:** Didn't need a restart, just enabling the add-in; works. Right-click
    Repeat doesn't detect the selected item, so no Replace option; the menu
    button is fine.
    **Response:** Repeat clears the active selection; captured the marking-menu
    selection (60 s window) as a fallback.

35. **User:** Add an anchors section generating pegs, T-slots and/or dovetails
    extending radially inward from the bore, with count and size per option.
    They'll be used as tools to carve the hub; hubs are external designs focused
    on axle and drive geometry.
    **Response:** Added anchors (full width, joined, not filleted, phase per type)
    plus a hidden hub cutter grown by a clearance; overlap/crowding checks.

36. **User:** Prefers the pegs as round tubes so they're easier to press into
    place.
    **Response:** (Misread) made radial round pins pointing at the axle, with an
    optional hole and rows across the width.

37. **User:** Misunderstood: pegs look like circles in the standard sketch
    orientation, connected to the bore by a rectangular stem like the T-slots;
    extruded, the tubes run through the width.
    **Response:** Rebuilt as keyhole pegs (head circle + stem, optional hole down
    the rod); removed the radial-pin version; migration for saved settings.

38. **User:** Does Fusion support bodies with separate parts? Each anchor shows
    as a separate body and the cutter is a single anchor that would need
    patterning.
    **Response:** (Incorrectly) said yes, multi-lump bodies. Diagnosed unstable
    entity tokens; drew all anchor copies in one sketch and extruded at once.

39. **User:** Still not working (screenshot: Tire, Hub cutter, Body166...).
    **Response:** Found `feature.bodies` reported only one body; switched to
    joining every body except the tire.

40. **User:** Still a bunch of individual anchors and a cutter with one inflated
    anchor.
    **Response:** Corrected the earlier claim: Fusion splits non-touching pieces
    into separate bodies. Added the cutter ring (bore - clearance to anchor
    roots), a leftover-body report, and the version in the confirmation.

41. **User:** Had fully restarted Fusion before the last feedback; problem
    remains. Design and component timelines look duplicated; suggested
    activating the new component; there should be one timeline entry per tire
    and regens shouldn't add entries. The cutter Combine looks valid (1 target,
    35 tools) but no combined body appears.
    **Response:** The screenshot matched pre-ring behaviour (non-touching tools
    stay separate). Added timeline grouping of each tire's items (activation
    wouldn't help; one design timeline).

42. **User:** v1.8 tested; the cutter is one body now. What are the options for
    publishing the add-in?
    **Response:** GitHub repo (recommended first), GitHub release with
    installer, Autodesk App Store (bundle, review), team-only sharing; tidy-up
    checklist.

### Part E: repo and polish (v1.9 to v1.11)

43. **User:** Renamed to airless-tire-generator (less precise but more
    approachable). Empty repo at `D:\Documents\GitHub\airless-tire-generator`
    in the pondersome account, branded Ponderbotics; team credit once they help.
    Put the add-in in a Fusion plugin folder (Onshape/standalone may follow).
    Tidy and migrate; no commits until approved.
    **Response:** Created `fusion/AirlessTireGenerator` (v1.9, Ponderbotics
    command id and attribute group, legacy groups readable, new manifest id),
    README, MIT LICENSE (Ponderbotics), .gitignore; removed the installed copy
    (backed up). Proposed the first commit message.

44. **User:** Add the test harness to a tools folder.
    **Response:** Added `tools/` (smoke_test, preview, fusionstub, harness,
    README); fixed a preview drawing-order bug. Proposed first commit message:
    "Initial import of Airless Tire Generator Fusion add-in" with a body
    describing the structures, anchors, cutter, validation, regen, timeline
    grouping and offline tools.

45. **User:** The keep open option isn't selectable (screenshot: disabled with
    tread rim 0).
    **Response:** InputChanged passed only the group's inputs, so refresh failed
    silently; now always uses the command's full inputs (v1.10). Also fixes the
    Resulting box not updating.

46. **User:** The add-in no longer shows in Utilities > Add-Ins; is it because
    it moved out of the standard location? The button is still there.
    **Response:** The old add-in was still loaded in memory with its folder gone;
    restart, then link the repo folder with +; offered a directory junction as
    an alternative.

47. **User:** The option is called "Script or add-in from device", and the + is
    not green in dark mode; update the README. It works. A very dense open
    honeycomb with 128 cells gives an invalid expression error.
    **Response:** Updated README install steps. The spinner max was 120; raised
    count limits to 360 (v1.11). Initially also blamed the geometry using
    default settings.

48. **User:** Was using 1-line walls on an 88 mm OD.
    **Response:** Re-ran with the user's saved settings: 128 cells is valid
    (zigzag 1.11 mm, "tiny" warning only); the cap alone caused the error.

49. **User:** Is there a shortcut to pull up add-ins to cycle faster?
    **Response:** Shift+S; offered dev auto-reload or a reload command.

50. **User:** Shift+S is good enough. Trouble slicing the ultra-fine honeycomb;
    Arachne comes closest. What do the white spots mean? (Screenshot with
    "floating regions" warning.)
    **Response:** Offered a hypothesis (single-line walls dropping out) with
    slicer settings to try.

51. **User:** Already tested classic thin wall; it dropped whole spoke sections.
    Anchors and inner rim are fine. Pointed out the answer was a hypothesis, not
    research.
    **Response:** Researched: Bambu's warning targets floating parts/cantilevers;
    issue #4997's maintainer says check G-code from below or layer by layer; the
    white colour is undocumented. Proposed a layer check and a line-width test
    (0.68 generator vs 0.62 slicer) to turn the hypothesis into evidence.

52. **User:** Come back to that later; generate this journey document.
    **Response:** This file.

### Part F: tread profiles (session 2, v1.12 to v1.14)

53. **User:** Migrated the conversation to this repo; read the specs folder to
    learn the project.
    **Response:** Read this file and the README and summarised. Noted the doc
    said nothing was committed, though `main` already had the initial import;
    saved the standing rules (approve commits, no AI attribution) to memory.

54. **User:** So far everything is 2D with strong radial symmetry plus a
    straight extrude. Can we extrude symmetrically along a path to develop a
    bulge, outward (soften the edges for turning on terrain without catching)
    or inward (ball-flinging flywheels that keep more surface contact)? This
    should be a plastic deformation of the whole pattern spread along the
    radius, not just stretching the outermost bits. Fusion operations, or
    rethink the generators?
    **Response:** Fusion's own operations don't fit: sweep with a guide rail
    scales the bore and the wall thicknesses, non-uniform scale is global, and
    a revolve cut only trims. Proposed mapping the member centrelines radially
    at each height (bore fixed, spoke zone scaled), re-thickening so walls stay
    whole lines, and lofting seed members through sections before patterning.

55. **User:** The bore stays straight: the tire is pressed onto the hub, with
    side plates for alignment under vibration. Inner and outer bulges will
    differ. Inward: start with a circular groove matching the ball for a
    target contact cross-section (parabolic might ease contact later). Don't
    assume a bulge spans the full width. Outward: consider the shoulder; tires
    have a more aggressive downturn from crown to shoulder (screenshot labelling
    crown, shoulder, sidewall), so a compound profile, still without solid
    sidewalls.
    **Response:** Prototyped the profile maths and the mapping in the
    scratchpad, with side half-section and slice renders. Proposed Flat /
    Crowned (crown width, crown radius, shoulder radius) / Grooved (ball
    diameter, contact width), the OD as the largest diameter with the pattern
    only compressed, and re-checking where the squeeze is deepest. Corrected an
    earlier claim: thin walls overhang whichever way they lean, so both
    shoulders are limited, not just one. Floated parabolic or conformity-based
    groove easing, a groove plus rounded shoulders, an off-centre groove.

56. **User:** Proceed.
    **Response:** Built v1.12: profile classes, radial map, squeezed checks,
    dialog group, `preview.py --z/--side`, smoke tests, and a recording fake of
    the Fusion API to dry-run `build()` (which also made section sketch names
    unique). Found that squeezing can open gaps as well as close them (Gothic
    legs flatten), so the gap checks now follow the whole squeeze and report
    the heights where a sliver appears.

57. **User:** The 128-cell honeycomb already takes about 4 minutes to build. How
    much worse will it be now?
    **Response:** Counted the operations with the fake: a groove with lands
    split every member into three bodies (4,992 in the join instead of 1,664).
    Fused each member's pieces before patterning and added per-phase build
    timing. Estimated 1.5 to 2.5 times the flat build, unmeasured: freeform
    surfaces join more slowly than planes and cylinders.

58. **User:** Do I have to restart Fusion to see the update?
    **Response:** No: Shift+S, Stop, Run; the dialog and message show the
    version.

59. **User:** OD as the maximum suits flat and crowned, but a groove's working
    surface is its bottom; A/B tests will hold the groove bottom constant for
    constant surface speed while varying engagement depth and width. An
    arithmetic build OD is enough; the build needn't change.
    **Response:** v1.13: Tire OD is the groove bottom and the lands are OD +
    2 x depth (`build_params`); names keep the OD as entered and add the
    contact width; the spoke-zone check applies at the groove bottom; warnings
    say where they apply; tires built with 1.12 migrate. Noted that the cells
    at the groove bottom shift slightly with groove depth, since the pattern is
    laid out at the lands.

60. **User:** Build time was acceptable, but the STEP export took a while and
    was 47 MB, and Bambu Studio sat at 20% importing with little CPU or memory
    use (a hex groove at half the previous resolution). Then: it finished after
    about 16 minutes.
    **Response:** Analysed the STEP: 85% of its points were in 5,376 B-spline
    edge curves, 4,096 of them lying across the tire at the faces and the
    land/groove boundaries, from members drawn as 21 to 31-point fitted
    splines. v1.14 draws exact lines and arcs where unsqueezed, keeps squeezed
    straight walls straight (bend under 0.01 mm), uses 9-point splines only for
    curved members, and needs fewer loft sections. Suggested 3MF for slicing.

61. **User:** I don't think Bambu understands 3MF?
    **Response:** It does: Bambu Studio's own projects are 3MF (the user's were
    written by Bambu Studio 2.09). Export with right-click > Save As Mesh > 3MF
    and add it with File > Import.

62. **User:** The STEP shrank (measured: 12.5 MB) and the 3MF imported
    quickly; results after the test print.
    **Response:** Listed what to watch: groove smoothness, cells at the groove
    bottom, the groove sides.

63. **User:** It seems to be printing; whether that design is right depends on
    the chosen parameters and material. Call it a major feature set with some
    optimisation for very complex results; propose the commit language.
    **Response:** Proposed the commit message.

64. **User:** Did we move the scratchpad work into tools?
    **Response:** No; moved it: the fake API replaced `tools/fusionstub`, plus
    `tools/dry_build.py` and `tools/step_report.py`, with README sections.
    `step_report.py` confirmed the fix on the two exports (the 4,096 curves
    lying across the tire became lines).

65. **User:** Update the journey doc, then commit.
    **Response:** This part, and the commit.
