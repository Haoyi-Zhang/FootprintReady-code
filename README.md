# Footprint-aware ready-set boundary contracts

A standalone research artifact for the finite reconfigurable-datapath machine
in the companion manuscript: a certificate producer, representation-distinct
checker, small-instance oracle, restricted-policy baselines, deterministic
inputs, handwritten proofs, tests, and archived results.

The state records completed-node identities, mode, resident identities and
dirty resident identities. Value footprints determine storage/transfer costs;
cost intervals have nonnegative integer endpoints. Costs are stipulated abstract
units, not calibrated device energy. The model and theorem assumptions are in
`proofs/semantics.md`.

## Setup and portable checks

Use Python's standard library; no package installation, network, external
solver, private data, GPU or model API is required. Run from the repository root:

```sh
python -B -m unittest discover -s tests -v
python -B verify_bibliography.py
python -B freeze_inputs.py --check
```

The current unit suite has 15 methods, including certificate mutations,
metamorphisms, exact frozen-byte checks, declared-domain boundaries and selected
trace-event regressions. These checks work on Windows as well as Unix.
`verify_bibliography.py` checks the supplied 67-row source audit offline; it is
not a live source lookup or a substitute for its recorded reading depth.
`freeze_inputs.py --check` compares exact UTF-8 bytes, including line endings;
omit `--check` only when deliberately regenerating the frozen input.

## Archived certificates and full reproduction

The tested full-release environment is Linux x86_64, CPython 3.13.5.
`verify.py`, `reproduce.py`, `run.py`, `pilot.py` and `summarize.py`
import the Unix-only `resource` module for CPU/RSS observations. Their full
campaign is unsupported on Windows; other Unix/Python variants are untested.

```sh
python -B verify.py
python -B reproduce.py --out reproduction-output
```

`verify.py` independently checks all 166 archived certificates and the
bibliography audit without importing the producer. Certificate acceptance binds
the parsed instance by canonical structural equality. The checker re-parses
identity sets, replays the witness, reconstructs transitions, checks Bellman
labels, and requires the listed states to equal the source-reachable closure.

`reproduce.py` requires a nonexistent output directory and uses one worker. It
runs unit tests and the bibliography/frozen-input gates, the discrimination
pilot, the 166-case batch in two chunks, summary/projection analyses and the
7,290-case exhaustive audit. It compares scientific JSON/CSV fields and all
certificate objects with the archive. Only wall time, CPU time and peak RSS are
excluded from equality. Fresh outputs and a reproduction log/report go in the
chosen directory, leaving frozen inputs and archived results intact. Each child
command has a 60-second timeout.

The scientific-checks workflow uses Ubuntu 24.04 and Python 3.13, bounds the
scientific command block to 300 seconds and 2 GiB virtual memory, and uploads
available raw outputs even after failure. Material-integrity checks are separate.

For manual chunks on the supported Unix environment, select a separate output
directory and run serially:

```sh
python freeze_inputs.py --check
python run.py --out finite-results --start 0 --stop 64
python run.py --out finite-results --start 64 --stop 166
python summarize.py --out finite-results
python exhaustive_audit.py --out finite-results/exhaustive-audit.json
```

The two slices must cover all 166 indices without overlap before summarizing.
`pilot.py --out <directory>` runs the boundary, schedule, fork-join,
footprint-identity and dirty-flush controls.

## Inputs, results and implementation map

`inputs/validation-cases.json` is the consumed deterministic batch: 166
synthetic instances (158 feasible, eight infeasible), including 13 nonuniform
footprint cases. Individual input files provide the worked pilot examples.
`src/cases.py` and `freeze_inputs.py` define and serialize the batch.

`results/` retains raw chunks, all 166 certificates, pilot certificates,
JSON/CSV summaries, semantic-differential and mutation records, exhaustive
enumeration results, resource accounting and clean reproduction logs.
`post_freeze_independence_audit.json` retains historical seed/coverage observations;
its bookkeeping is separate from the deterministic certificate checks.
The finite differential check covers 13,570 reachable states and 46,110 edges;
the small oracle agrees on 90 cases. All 55 prescribed certificate/model
mutations are rejected. The exhaustive two-node grammar, its 7,290 instances
and explicit domain are defined in `exhaustive_audit.py`.

`src/model.py` defines validated bit-mask semantics; `src/planner.py` produces
closures and certificates. `src/checker.py` imports neither module.
`src/oracle.py` uses non-memoized ready-node/mode/resident-subset enumeration;
`src/baseline.py` implements fixed-list and at-most-two-mode home-sealed
policies. `analyze_abstractions.py` measures the stated coarse projections;
the zero-conflict full-key row is a singleton-grouping sanity check, not a
direct experimental proof of history erasure.

`claim_evidence_ledger.csv` links claims to proof/test/result consumers.
`bibliography_audit.csv`, `external_resources.csv` and `licenses/` retain
source attribution and access boundaries. Cited literature is not redistributed.

## Conditions and limits

Producer/checker ceilings are 120,000 states, 1,200,000 edges, 32 MiB parsed
JSON, 20 nodes, 40 value names, three modes, footprint at most 16 and mode
capacity at most 32 units. The oracle allows at most two modes, five nodes and
five million recursive visits. The exact home-sealed baseline also requires
at most two modes. A ceiling/domain error is not evidence of infeasibility.

The checker trusts Python and the declared event, footprint and retention
semantics. Handwritten proofs and finite differential/exhaustive checks do not
formally verify Python. The model does not establish tensor/operator functional
correctness, banking, placement, fragmentation, DMA, overlap, leakage, thermal
history, queueing, hardware-energy accuracy or industrial scalability.
Concrete accelerator use needs semantics-preserving lowering/refinement and
calibrated coefficients. The thesis source recorded at official-record/abstract
depth was not successfully retrieved in full.

Original code and generated inputs are licensed under `LICENSE`; upstream
literature rights remain with their owners.
