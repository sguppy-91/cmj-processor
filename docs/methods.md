# Methods: CMJ force-time analysis

This document describes every methodological decision in `cmj-processor`,
maps each decision to the code that implements it, and states why the
decision was made. It is written so a future student or colleague can
understand and audit the analysis without access to the original author,
and so a published methods section can be reproduced exactly by loading a
named config preset (`HD-raw`, `IJSSC2024`).

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
columns and UTF-8 BOMs are tolerated. This is the format the original
`CMJ_Analysis_Script.py` was written against.

### PASCO Capstone/SPARK (`readers/pasco.py`)

One file can contain several runs side by side, each with its own column
group suffixed `Run #N`, ending at different times (ragged rows). The
reader produces one `Trial` per run from the run's `Time (s)` and
`Fz (N)` columns, pairs them row-wise, drops rows where either is empty,
and records the run number in `Trial.meta["run"]`.

**PASCO's own calculated columns (weight, hangtime, mass, Jump Height)
are deliberately ignored.** Body mass comes from the analyst-selected
weighing window (section 2) and every metric from the pipeline. On real
data the disagreement is not subtle: PASCO's hangtime-based Jump Height
column reported ~78 cm on a trace our take-off-velocity method scores
at ~0.43 m (its hangtime column implies a 0.8 s flight, which is not
physiologically credible). If any legacy workflow trusted those
columns, reconcile before migrating.

## 2. Body mass and the weighing window (`processing/weighing.py`)

The analyst clicks the start of a quiet-standing period; the window runs
from the sample nearest that click for `weighing_duration_s` (1 s
default). Body weight (BW) is the window mean, SD the sample standard
deviation (ddof = 1), and mass = BW / g.

- A window shorter than `weighing_min_window_s` (0.5 s) is rejected —
  the click was too late in the file.
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
fourth-order at 65 Hz — the cutoff chosen by residual analysis in the
2024 IJSSC manuscript.

**Position in the pipeline is fixed and load-bearing**: when filtering is
enabled, the signal is filtered once, and BW and SD are computed from
the *filtered* signal, so the BW ± SD threshold and the data it is
applied to are consistent (`pipeline.py`). Filtering changes the
quiet-standing SD (the onset threshold), so its position relative to the
weighing window cannot be left implicit. Under `HD-raw` (no filter) this
is moot and the pipeline is the verbatim port of the reference script.

Two measured consequences, encoded in `tests/test_filtering.py`:

- **Noise attenuation is real but partial**: a fourth-order 65 Hz filter
  at 1 kHz leaves ~34% of white-noise amplitude (the sub-cutoff power
  fraction). Filtering reduces the onset SD; it does not sanitise noise.
- **Edge distortion exists and decays**: filtfilt's edge handling is an
  explicit config choice (`FilterSpec.edge_mode`: `'pad'` odd extension,
  default, or `'mirror'` even extension). On a trace that is not steady
  at the file edge, distortion reached ~6 N on the first samples and
  decayed to the noise floor within 50 ms. This matters because onset
  detection and the refined take-off threshold both operate near edges.

Per-platform defaults: HD plates are quiet enough that the reference
workflow used raw force (`HD-raw`); PASCO hardware is noisier, so a
filtered preset for PASCO data should be validated before use (see
Open items).

## 4. Movement onset (`processing/onset.py`)

Initial onset: the first sample after the weighing window beyond
BW ± `sd_multiplier` × SD (Owen et al., 2014). The direction of departure
is recorded (`rising` / `declining`) because a countermovement normally
leaves BW downward first — a `rising` onset flags an unusual trace worth
inspecting (one of the five runs in the PASCO validation file did this).

True onset is then refined by one of two methods (config:
`onset_method`):

- **`backtrack_ms`** (default, reference script): step back a fixed
  `onset_backtrack_s` (100 ms) from the initial onset. Chosen over a
  backward search because noise during the weighing period makes
  "last BW crossing" misidentification-prone.
- **`search_last_bw`** (2024 IJSSC manuscript): backward search from the
  BW ± 5 SD point to the last BW instance. **Not yet implemented** — the
  semantics need pinning against the manuscript before shipping; the
  pipeline raises `NotImplementedError` rather than guessing.

Whichever is used is recorded per trial in the output
(`onset_method` column), which also enables a sensitivity comparison of
the two as a standalone methodological check.

## 5. Integration (`processing/integration.py`)

From onset onward: net force = Fz − BW; acceleration = net force / mass;
velocity and displacement by trapezoidal integration of acceleration and
velocity respectively (McMahon et al., 2018). This is the reference
script's formulation, ported verbatim; parity on real Hawkin data is
exact to floating-point tolerance (see Validation).

## 6. Jump phases (`processing/phases.py`)

McMahon et al. (2018) phase identification, searched only up to the
coarse take-off so landing effects cannot contaminate the boundaries:

- **Unweighting ends** at minimum velocity.
- **Braking ends** at the first positive-velocity sample after the
  unweighting minimum.
- Propulsion runs from braking end to take-off.

## 7. Take-off and landing (`processing/takeoff.py`)

Two-stage detection, because a fixed threshold is exactly where plate
noise and drift bite:

1. **Coarse take-off** brackets the flight phase: the first sample below
   `takeoff_coarse_n` (10 N). This threshold is also used to find the
   landing (first sample above it after flight).
2. **Refined take-off** (default): from the middle 50% of the bracketed
   flight, mean + `sd_multiplier` × SD gives a data-driven threshold;
   take-off is the first sample below it after braking ends. This adapts
   to per-recording noise instead of assuming a fixed force level.

Fallbacks are deliberate and logged as warnings on the result and the
verification figure — never silent:

- No landing in the trace (truncated file): coarse take-off used.
- Refined threshold never crossed: coarse take-off used.

The manuscript's static threshold (`takeoff_method="fixed_n"`,
`takeoff_fixed_n=20 N`) is implemented as an alternative and recorded
per trial.

## 8. Metrics (`processing/metrics.py`)

- **Jump height** = v²_takeoff / (2g) + COM displacement at take-off
  (Chiu & Daehlin, 2020) — take-off velocity from the force integral,
  not flight time.
- **Total movement time** = onset to take-off.
- **Mean braking force** = mean net force over the braking phase.
- **Eccentric displacement** = COM displacement at braking end relative
  to onset (negative by construction).
- **Mass** = BW / g from the weighing window (section 2).

Metric keys currently use the reference script's terminology. Renaming
to the manuscript's terms (eccentric yielding / eccentric braking /
concentric mean forces, per-sub-phase) is planned with the next export
schema bump; the manuscript additionally reports time-to-take-off and
mean force across all three sub-phases, which the current metrics module
does not yet export. See Open items.

## 9. Analyst decisions and the audit trail (`app/decisions.py`, `export.py`)

Per trial the analyst makes an explicit **accept / adjust / discard**
decision at a verification figure showing force, thresholds, boundaries,
velocity, and displacement, with any fallback warnings rendered on the
figure.

- **Accept** — log and write.
- **Adjust** — either re-open the weighing-window selection or move a
  boundary (unweighting end, braking end, take-off) by clicking at its
  new time; affected metrics recompute and the trial is written with
  `adjusted = True` and the overrides in `boundary_overrides`.
- **Discard** — nothing is written.

Boundary overrides must respect phase ordering
(0 ≤ unweighting end ≤ braking end ≤ take-off); violations are rejected.

A row logs enough to replay the analysis exactly: the raw
`weighing_start_s`, the `adjusted` flag, overrides as JSON, onset
strategy and method, take-off method, config preset, plate type, source
file, run number, and warnings, under `schema_version = 1`. A decision
read back from the CSV and re-run reproduces the original metrics
exactly (`tests/test_decisions.py`).

Trial averaging (the manuscript averages five trials per session) is
deliberately **outside** the per-trial pipeline; it belongs at the
analysis level so the treatment of adjusted and discarded trials is an
explicit, documented choice rather than an accident of implementation.
It is not yet implemented.

## 10. Configuration (`config.py`)

Every constant lives in one frozen dataclass; `docs` map one-to-one onto
code. Named presets reproduce a methods section by name:

| Parameter | `HD-raw` (reference script) | `IJSSC2024` (manuscript) |
|---|---|---|
| gravity | 9.81 | 9.81 |
| sd_multiplier | 5 | 5 |
| weighing_duration_s | 1.0 | 1.0 |
| onset_method | `backtrack_ms` (100 ms) | `search_last_bw` |
| filter_spec | none (raw force) | 4th-order, 65 Hz, zero-lag |
| takeoff_method | `refined` (flight middle-50% + 5 SD) | `fixed_n` (20 N) |
| takeoff_coarse_n | 10 | 10 |

**Caveat**: loading `IJSSC2024` today raises `NotImplementedError` at
onset until `search_last_bw` is implemented (section 4). Filtering and
the fixed 20 N take-off are implemented and tested.

## 11. Validation

Three layers, each catching what the previous cannot:

1. **Parity with the reference implementation.** The pipeline reproduces
   `CMJ_Analysis_Script.py` exactly (to 1e-9 relative tolerance) on real
   Hawkin data: BW, SD, mass, onset indices and strategy, phase
   boundaries, take-off (refined and both fallback paths), flight
   statistics, and all metrics.
2. **Synthetic signals with known truth** (`tests/`): a half-sine
   impulse with closed-form velocity/displacement pins the integration;
   piecewise-linear traces with exact integer boundaries pin the phase
   and take-off logic including all fallbacks; noisy filter tests pin
   interior fidelity, quiet-standing SD reduction, and edge behaviour.
3. **Reader fixtures** (`tests/data/`): a real multi-run PASCO excerpt
   (including ragged rows) and a Hawkin-layout fixture, so export-format
   drift is caught by regression.

## Open items

Decisions the code currently defers, stated here so they are not
rediscovered the hard way:

1. `search_last_bw` onset — implement against the manuscript, then
   unpick the `IJSSC2024` preset.
2. Manuscript metric terminology and the three per-sub-phase mean forces
   — next export schema bump.
3. Trial averaging and the inclusion/exclusion rule for adjusted and
   discarded trials — analysis level, not pipeline.
4. Filtered preset for PASCO data — the 65 Hz cutoff was chosen by
   residual analysis on Hawkin hardware; PASCO noise characteristics
   differ and should be re-derived, not assumed.
5. No batch/CLI replay mode yet (per-session decision to defer).

## References

- Chiu, L. Z. F., & Daehlin, T. E. (2020). Comparing numerical methods
  to estimate vertical jump height using a force platform.
  *Measurement in Physical Education and Exercise Science*, 24(1),
  25–32.
- McMahon, J. J., Suchomel, T. J., Lake, J. P., & Comfort, P. (2018).
  Understanding the key phases of the countermovement jump force-time
  curve. *Strength & Conditioning Journal*, 40(4), 96–106.
- Owen, N. J., Watkins, J., Kilduff, L. P., Bevan, H. R., & Bennett,
  M. A. (2014). Development of a criterion method to determine peak
  mechanical power output in a countermovement jump. *Journal of
  Strength and Conditioning Research*, 28(6), 1552–1558.
- Guppy, S. et al. (2024). [2024 IJSSC deadlift-stability manuscript —
  full citation to be inserted from the manuscript's reference list.]
