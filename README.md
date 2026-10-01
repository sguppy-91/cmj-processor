# cmj-processor

Plate-agnostic countermovement jump (CMJ) force-time analysis.

Processes force-time curves from multiple force plate systems (Hawkin
Dynamics, PASCO) through one normalised `Trial` data model and one pure
analysis pipeline, with an analyst-in-the-loop interactive workflow.

## Status

Under development. Step one (package skeleton, data model, Hawkin Dynamics
reader, analysis core ported from `CMJ_Analysis_Script.py`) is complete;
interactive layer, PASCO reader, CLI batch mode, and export schema follow.

## Install

```bash
pip install -e .
```

## Usage

Not yet wired to a GUI/CLI. Library use:

```python
from cmj import CMJConfig, read_csv_any, run_pipeline

trial = read_csv_any("jump.csv")[0]
result = run_pipeline(trial, CMJConfig.preset("HD-raw"), weighing_start_s=1.2)
print(result.metrics)
```

Launch the interactive workflow (file selection, weighing-window
inspection, accept/adjust/discard verification gate):

```bash
cmj-gui
```

Or double-click `scripts/launch-cmj-gui.command` (a copy can live
anywhere - the Desktop is a good spot).

## Methods

The full methodological write-up, mapped one-to-one onto the code, is in
[docs/methods.md](docs/methods.md).

## Methodological Basis and References
The analytical procedures implemented in this software were informed by the following methodological literature:

- Chiu, L. Z. F., & Daehlin, T. E. (2020). Comparing numerical methods
  to estimate vertical jump height using a force platform.
  *Measurement in Physical Education and Exercise Science*, *24*(1),
  25–32.
- Harry, J. R., Blinch, J., Barker, L. A., Krzyszkowski, J., & Chowning,
  L. (2022). Low-pass filter effects on metrics of countermovement
  vertical jump performance. *Journal of Strength and Conditioning
  Research*, *36*(5), 1459–1467.
- McMahon, J. J., Suchomel, T. J., Lake, J. P., & Comfort, P. (2018).
  Understanding the key phases of the countermovement jump force-time
  curve. *Strength & Conditioning Journal*, *40*(4), 96–106.
- Owen, N. J., Watkins, J., Kilduff, L. P., Bevan, H. R., & Bennett,
  M. A. (2014). Development of a criterion method to determine peak
  mechanical power output in a countermovement jump. *Journal of
  Strength and Conditioning Research*, *28*(6), 1552–1558.
- Street, G., McMillan, S., Board, W., Rasmussen, M., & Heneghan, J. M. (2001). Sources of
  error in determining countermovement jump height with the impulse
  method. *Journal of Applied Biomechanics*, *17*(1), 43–54.

## Acknowledgments

The development of this software was supported by a NSCA Foundation Young
Investigator Grant.

## Development
This software was developed with assistance from the GLM 5.3 large language model (Z.ai, China; hosted by Mistral AI, France)

AI assistance was used for software design discussion, code generation and 
refactoring, test development, documentation, and debugging. The analytical 
methods, methodological decisions, project requirements, and overall software 
architecture were specified and reviewed by the project author. AI-generated code 
was reviewed, tested, and revised as part of the development process.

The author remains responsible for the scientific methods implemented by the 
software and for the correctness and interpretation of the outputs.
