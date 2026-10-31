# Methods: CMJ force-time analysis

This document describes every methodological decision in `cmj-processor`,
maps each decision to the code that implements it, and states why the
decision was made. It is written so a future student or colleague can
understand and audit the analysis without access to the original author,
and so a published methods section can be reproduced exactly by loading a
named config preset (`raw`, `bw_search`).

Where a decision is still unresolved, this document says so explicitly
rather than papering over it.

## Overview

```
raw export ──readers──> Trial ──pipeline──> AnalysisResult ──export──> results CSV
                          ^                     |
                          |                     v
                    analyst decision (weighing window, boundary overrides)
```

- **Readers** (`src/cmj/readers/`) convert vendor exports into one
  normalised `Trial` per recording: a time vector (s), a combined vertical
  force vector (N), the plate type, the sampling rate, and metadata
  (`src/cmj/model.py`).
- **Pipeline** (`src/cmj/processing/`, `src/cmj/pipeline.py`) is a pure
  function: `run_pipeline(trial, config, weighing_start_s)`. No I/O, no
  GUI.
- **Decisions** (`src/cmj/app/decisions.py`) hold the analyst's manual
  inputs and are logged verbatim in the results CSV.
- **Export** (`src/cmj/export.py`) writes one row per analysed trial.

The manual inspection steps are a design feature, not friction: every
boundary the analyst controls is an explicit, logged decision, which is
far easier to audit than buried spreadsheet formulas.

## 1. Data ingestion (readers)

### Common rules

- **Sampling rate is derived from the data** — the median of `diff(t)` —
  never trusted from export metadata. Runs inside one file can differ in
  rate (PASCO does), and metadata is unreliable across vendors
  (`readers/base.py: sampling_rate`).
- Auto-detection sniffs the header and dispatches to the matching vendor
  reader; `plate_type=` forces a specific reader when a new export
  variant must be tested (`readers/__init__.py: read_csv_any`).
- Unrecognised files fail loudly with the header that was found.

### Hawkin Dynamics (`readers/hawkin.py`)

One trial per file. The analysis uses `Time (s)` and `Combined (N)`;
`Left (N)` and `Right (N)` are present in exports but not used. Extra
columns and UTF-8 BOMs are tolerated.

### PASCO Capstone (`readers/pasco.py`)

When exporting from PASCO Capstone, one file can contain several runs side by side, each with its own column
group suffixed `Run #N`, ending at different times (ragged rows). The
reader produces one `Trial` per run from the run's `Time (s)` and
`Fz (N)` columns, pairs them row-wise, drops rows where either is empty,
and records the run number in `Trial.meta["run"]`.

**Columns calculated within PASCO Capstone (weight, hangtime, mass, Jump Height etc)
are deliberately ignored.** Body mass comes from the analyst-selected
weighing window (section 2) and every metric from the pipeline. 

## 2. Body mass and the weighing window (`processing/weighing.py`)

The analyst clicks the start of a quiet-standing period; the window runs
from the sample nearest that click for `weighing_duration_s` (1 s
default). Body weight (BW) is the window mean, SD the sample standard
deviation (ddof = 1), and mass = BW / g.

- A window shorter than `weighing_min_window_s` (0.5 s) is rejected. 
  The start of the weighing period was selected too late into the trial
   and needs to be re-selected.
- **The logged decision is the raw click time**, never the snapped
  sample time or any derived onset value. A batch reprocess after a
  methods tweak (different filter, different onset rule) therefore
  replays the analyst's decision honestly. The click is logged at
  microsecond precision so it round-trips exactly through CSV text
  (`export.py: result_row`).

Why manual: a weighing window over a fidgety period silently shifts BW,
SD, and therefore the onset threshold. A human looking at the trace is
the cheapest reliable detector of a bad window, and a logged decision is
auditable in a way a heuristic is not.

## 3. Filtering (`processing/filtering.py`)

An optional zero-lag (filtfilt) low-pass Butterworth filter, default
fourth-order at 50 Hz (Harry et al., 2022).
When filtering is enabled, the signal is filtered once, and BW and SD are computed from
the *filtered* signal, so the BW ± SD threshold and the data it is
applied to are consistent (`pipeline.py`). Filtering changes the
quiet-standing SD (the onset threshold), so its position relative to the
weighing window cannot be left implicit. Under `raw` (no filter) this
is moot.

Two measured consequences, encoded in `tests/test_filtering.py`:
- **Noise attenuation is real but partial**: a fourth-order 50 Hz filter
  at 1 kHz leaves ~33% of white-noise amplitude (the sub-cutoff power
  fraction). Filtering reduces the onset SD; it does not sanitise noise.
- **Edge distortion exists and decays**: filtfilt's edge handling is an
  explicit config choice (`FilterSpec.edge_mode`: `'pad'` odd extension,
  default, or `'mirror'` even extension). On a trace that is not steady
  at the file edge, distortion reached ~6 N on the first samples and
  decayed to the noise floor within ~60 ms. This matters because onset
  detection and the refined take-off threshold both operate near edges.

Per-platform defaults: HD plates are quiet enough that the reference
workflow used raw force (`raw`); PASCO hardware is often noisier, so a
filtered preset for PASCO data should be validated before use (see
Open items).

## 4. Movement onset (`processing/onset.py`)

The BW ± 5 SD search is bounded by the shape of the force-time curve
itself, so the propulsion phase and the landing spike can never be mistaken for onset:
1. **Coarse take-off** brackets the jump: the first sample below
   `takeoff_coarse_n` (10 N) after the weighing window.
2. The **peak force** between the end of the weighing window and the
   coarse take-off bounds the jump (it falls in the propulsion phase).
3. The **minimum force** between the weighing window and the peak
   bounds the BW ± `sd_multiplier` × SD search window.

Within [weighing end, dip minimum], the initial onset is the first
sample beyond the threshold (Owen et al., 2014). The direction of
departure is recorded (`rising` / `declining`): a countermovement
normally leaves BW downward first, but a **pre-movement rise**, triggered by the the
athlete shifting weight before the countermovement, is a legitimate
`rising` onset found inside the bounded window, which is why the
threshold is BW ± 5 SD and not BW − 5 SD alone. A countermovement too
gradual to cross either threshold inside the window raises `OnsetError`
(loud, analyst-visible) instead of latching onto the later propulsion
rise. This is considered the failure mode of an unbounded search.

The initial onset is the **first sample beyond** the BW ± 5 SD threshold (a
threshold crossing, not a nearest match); the declining search runs
weighing end → dip minimum, and the rising search also runs weighing
end → dip minimum (provably identical to searching out to the window
maximum for a first crossing: any BW + 5 SD crossing lies at or before
the window maximum); and a threshold never crossed raises `OnsetError`
instead of silently falling back to the sample nearest the dip
minimum. Where this happens, the analyst should decide whether to re-weigh
or manually adjust the state threshold.

**Manual onset placement.** When detection raises `OnsetError`, the
inspector offers three paths: place the onset manually (click-to-place,
same interaction as the weighing window), re-weigh, or discard. A manual
onset is logged as the raw click time (`onset_start_s`, schema v2),
recorded with `onset_method = "manual"`, and marked with a warning on
the result and the verification figure; a replayed decision reproduces
the trial exactly. A manual onset does not survive a re-weigh — new BW
and SD thresholds make the placement stale, so re-weighing clears it.

True onset is then refined by one of two methods (config:
`onset_method`):

- **`backtrack_ms`** (default): step back a fixed
  `onset_backtrack_s` (100 ms) from the initial onset. Chosen over a
  backward search because noise during the weighing period makes
  "last BW crossing" misidentification-prone.
- **`search_last_bw`** (Street et al., 2001): backward search from the
  BW ± 5 SD point to the last instance where the force-time curve crosses
  through BW. **Not yet implemented**; the pipeline raises `NotImplementedError`
   rather than guessing.

Whichever is used is recorded per trial in the output
(`onset_method` column), which also enables a sensitivity comparison of
the two as a standalone methodological check.

## 5. Integration (`processing/integration.py`)

From onset onward: net force = Fz − BW; acceleration = net force / mass;
velocity and displacement by trapezoidal integration of acceleration and
velocity respectively (McMahon et al., 2018).

## 6. Jump phases (`processing/phases.py`)

Two phase-identification taxonomies, selected by `phase_method` and
searched only up to the coarse take-off so landing effects cannot
contaminate the boundaries:

**`mcmahon` (default; McMahon et al., 2018)**

- **Unweighting ends** at minimum velocity.
- **Braking ends** at the first positive-velocity sample after the
  unweighting minimum.
- Propulsion runs from braking end to take-off.

**`harry` (Harry, Barker & Paquette, 2020)**

The countermovement is split at the force minimum rather than at
minimum velocity, matching where the summed lower-limb joint power
 turns negative and positive.

- **Unloading ends** at the local minimum vertical force (the
  onset of negative JP_SUM): body weight is unloaded into the
  countermovement by this point.
- The **eccentric phase** runs from unloading end to the first
  positive-velocity sample and, per the paper's recommendation,
   divides at minimum COM velocity into:
  - **yielding** (unloading end → minimum velocity): eccentric
    actions while the COM still accelerates downward;
  - **braking** (minimum velocity → first positive velocity):
    eccentric actions while the COM decelerates downward.
- The **concentric phase** runs from braking end to take-off.

The two event detection procedures share the minimum-velocity and first-positive-
velocity instants (`unweighting_end`/`braking_end` under `mcmahon`;
`yielding_end`/`braking_end` under `harry`), so the metrics' braking
interval spans the same samples under both; `harry` adds the
`unloading_end` boundary. The boundary-override system, the
verification figure, and the decision log follow whichever boundary
set the active method produces. A velocity minimum at onset (no
countermovement before take-off) raises `PhaseError` under `harry`,
since the unloading search window would be empty.

## 7. Take-off and landing (`processing/takeoff.py`)

Take-off is identified in three stages per Lake et al. (2018):

1. **Coarse take-off** brackets the flight phase: the first sample
   below `takeoff_coarse_n` (10 N), and the **next sample above it**
   closes the bracket (the landing; `find_landing`).
2. **Flight statistics window**: `takeoff_flight_trim_s` (30 ms) is
   trimmed from each end of the bracketed flight, and the window's
   mean + `sd_multiplier` × SD gives a data-driven threshold. This
   adapts to per-recording noise instead of assuming a fixed force
   level.
3. **Refined take-off** (default): the first sample below the
   threshold after braking ends.

The static threshold alternative (`takeoff_method="fixed_n"`,
`takeoff_fixed_n=20 N`) is implemented and recorded per trial.

**Known limitation:** The bracket is closed by
the *next* sample above the coarse threshold, so a plate ring-down
transient above 10 N in early flight terminates the bracket just as
the landing would. Lake et al. (2018) specify no ring-down guards and
matching the published method exactly is a known trade-off.

Fallbacks are deliberate and logged as warnings on the result and the
verification figure:

- No landing in the trace (truncated file): coarse take-off used.
- Bracketed flight too short for a statistics window: coarse take-off
  used.
- Refined threshold never crossed: coarse take-off used.

## 8. Metrics (`processing/metrics.py`)

- **Jump height** = v²_takeoff / (2g) + COM displacement at take-off
  (Chiu & Daehlin, 2020) — take-off velocity from the force integral,
  not flight time.
- **Total movement time** = onset to take-off.
- **Mean braking force** = mean net force over the braking phase.
- **Eccentric displacement** = COM displacement at braking end relative
  to onset (negative by construction).
- **Mass** = BW / g from the weighing window (section 2).

Metric keys currently use provisional terminology. Renaming to match the terminology of
McMahon et al. (2018) and Harry et al. (2020) is planned with a later export schema bump;
the manuscript additionally reports time-to-take-off and mean force
across all three sub-phases, which the current metrics module does not
yet export. See Open items.

## 9. Analyst decisions and the audit trail (`app/decisions.py`, `export.py`)

Per trial the analyst makes an explicit **accept / adjust / discard**
decision at a verification figure showing force, thresholds, boundaries,
velocity, and displacement, with any fallback warnings rendered on the
figure.

- **Accept** — log and write.
- **Adjust** — re-open the weighing-window selection, place the onset
  manually (only offered when onset detection failed), or move a
  boundary (unweighting end, braking end, take-off) by clicking at its
  new time; affected metrics recompute and the trial is written with
  `adjusted = True`, the manual onset time in `onset_start_s`, and any
  overrides in `boundary_overrides`.
- **Discard** — nothing is written.

Boundary overrides must respect phase ordering
(0 ≤ unweighting end ≤ braking end ≤ take-off); violations are rejected.

A row logs enough to replay the analysis exactly: the raw
`weighing_start_s`, the manual onset click time `onset_start_s` (empty
when the onset was detected), the `adjusted` flag, overrides as JSON,
onset strategy and method, take-off method, config preset, plate type,
source file, run number, and warnings, under `schema_version = 2`.
When the GUI combines a named preset with a non-default phase method,
the logged `config_preset` is `preset/phase_method` (e.g.
`raw/harry`), so the taxonomy that produced the boundaries is
identifiable from the log. A
decision read back from the CSV and re-run reproduces the original
metrics exactly (`tests/test_decisions.py`,
`tests/test_manual_onset.py`). `append_result` verifies an existing
results file carries the schema v2 header before appending — a
mismatched (e.g. v1) file raises `ExportError` instead of silently
misaligning columns; rename or migrate such files before appending.

## 10. Configuration (`config.py`)

Every constant lives in one frozen dataclass; `docs` map one-to-one onto
code. Named presets reproduce a methods section by name:

| Parameter | `raw` | `bw_search` (backward search) |
|---|---|---|
| gravity | 9.81 | 9.81 |
| sd_multiplier | 5 | 5 |
| weighing_duration_s | 1.0 | 1.0 |
| onset_method | `backtrack_ms` (100 ms) | `search_last_bw` |
| filter_spec | none (raw force) | 4th-order, 50 Hz, zero-lag (Harry et al., 2022) |
| takeoff_method | `refined` (Lake et al., 2018) | `fixed_n` (20 N) |
| phase_method | `mcmahon` (unweighting at min velocity) | `mcmahon` |
| takeoff_coarse_n | 10 | 10 |
| takeoff_flight_trim_s | 0.030 | 0.030 |

**Caveat**: loading `bw_search` today raises `NotImplementedError` at
onset until `search_last_bw` is implemented (section 4). Filtering and
the fixed 20 N take-off are implemented and tested.


## Open items

Decisions the code currently defers, stated here so they are not
rediscovered the hard way:

1. `search_last_bw` onset — implement against Street et al. (2001), then
   unpick the `bw_search` preset.
2. Manuscript metric terminology and the three per-sub-phase mean forces
   — a later export schema bump (v2 was taken by `onset_start_s`).
3. Filtered preset for PASCO data — the 50 Hz cutoff follows Harry et
   al. (2022); PASCO noise characteristics differ
   and should be re-derived, not assumed.
## References

- Chiu, L. Z. F., & Daehlin, T. E. (2020). Comparing numerical methods
  to estimate vertical jump height using a force platform.
  *Measurement in Physical Education and Exercise Science*, 24(1),
  25–32.
- Harry, J. R., Barker, L. A., & Paquette, M. R. (2020). A joint power
  approach to define countermovement jump phases using force platforms.
  *Medicine & Science in Sports & Exercise*, 52(5), 993–1000.
- Harry, J. R., Blinch, J., Barker, L. A., Krzyszkowsk, J., & Chowning,
  L. (2022). Low-pass filter effects on metrics of countermovement
  vertical jump performance. *Journal of Strength and Conditioning
  Research*, 36(5), 1459–1467.
- Lake, J., Mundy, P., Comfort, P., McMahon, J. J., Suchomel, T. J., &
  Carden, P. (2018). Concurrent validity of a portable force plate
  using vertical jump force–time characteristics. *Journal of Applied
  Biomechanics*, 34(5), 410–413.
- McMahon, J. J., Suchomel, T. J., Lake, J. P., & Comfort, P. (2018).
  Understanding the key phases of the countermovement jump force-time
  curve. *Strength & Conditioning Journal*, 40(4), 96–106.
- Owen, N. J., Watkins, J., Kilduff, L. P., Bevan, H. R., & Bennett,
  M. A. (2014). Development of a criterion method to determine peak
  mechanical power output in a countermovement jump. *Journal of
  Strength and Conditioning Research*, 28(6), 1552–1558.
- Street, G., McMillan, S., Board, W., & Rasmussen, M. (2001). Sources of
  error in determining countermovement jump height with the impulse
  method. *Journal of Applied Biomechanics*, 17(1), 43–54.
