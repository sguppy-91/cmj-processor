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

## Development
This software was developed with assistance from AI coding tools, including
the GLM-5.3 (Z.ai, China; hosted by Mistral AI) large language model and the 
Mistral Vibe CLI coding agent (version 2.25.8).

AI assistance was used for software design discussion, code generation and 
refactoring, test development, documentation, and debugging. The analytical 
methods, methodological decisions, project requirements, and overall software 
architecture were specified and reviewed by the project author. AI-generated code 
was reviewed, tested, and revised as part of the development process.

The author remains responsible for the scientific methods implemented by the 
software and for the correctness and interpretation of the outputs.
