# Cross-Layer Energy Contracts

This standalone repository implements the finite, footprint-aware ready-set
machine studied in the companion manuscript.  It contains a certificate
producer, a representation-distinct checker, an independent small-instance
oracle, restricted-policy baselines, deterministic inputs, proofs, tests,
and archived results. The executable cost intervals have ordered nonnegative-
integer endpoints and all certificate costs/labels are exact integers. The costs
are stipulated abstract units; this is not a calibrated device-energy tool.

## Established model-level result

A state is `(completed-node identities, mode, resident identities, dirty resident
identities)`.  Any dependency-ready DAG node may execute once.  The fixed instance
assigns every value a positive integer storage/transfer footprint.  Capacity is
the sum of resident footprints; loads, stores, and scratchpad traffic are charged
per footprint unit.  Mode switches either retain all residents (subject to target
capacity) or destroy all residents after every dirty value has been backed.

`proofs/semantics.md` proves, for this declared finite machine:

* preservation of dependency, liveness, home-validity, and weighted-capacity
  invariants;
* conditional additive interval-cost composition and model-relative history
  erasure for the boundary state;
* soundness and format completeness of feasible and infeasible certificates for
  the declared nonnegative-integer endpoint domain;
* preservation of these results under fixed nonuniform value footprints;
* a two-mode ready-set normal form used by the independent oracle;
* a sufficient mandatory-persistence writeback potential; and
* exact fixed-order and at-most-two-mode home-sealed results, plus relisting,
  capacity, and retention inclusion results.

These are written mathematical arguments, not proof-assistant mechanizations or
independent peer review.

## Certificate trust boundary

The producer uses integer bit masks.  The checker imports neither the producer nor
the bit-mask model: it re-parses the full instance, represents completed/resident/
dirty identities as sets, replays the witness, independently reconstructs every
outgoing transition, checks Bellman lower-bound inequalities, and traverses the
listed graph from the source.  Acceptance requires the listed states to equal the
exact source-reachable closure; successor-closed but disconnected additions are
rejected.  Instance binding uses canonical structural equality.

A feasible certificate contains an attained source-to-goal trace and a matching
source lower bound.  An infeasible certificate labels the source `dead` and proves
that deadness is successor closed while every goal is zero.  Checking remains
linear in the explicitly listed closure; certificates are not claimed to be
succinct.

## Frozen evidence

The current producer stores each closure edge's successor, action and exact
upper weight, not its event dictionary. Selected trace events are computed
directly from the stored action, source mode and fixed footprint map; the upper
weight is checked before recounting. Alternative successors are not enumerated
again for the trace. Full closure, reverse distances, zero-cost hop ties,
certificate fields and the independent checker/oracle/baselines are unchanged.
Four portable regressions in `tests/test_trace_events.py` compare separate event
definitions and the small normal-form oracle, preserve zero-cost ties and ceiling
errors, check event-map lifetime, and require one successor pass per closure
state. Ordinary discovery runs 15 methods. These checks do not measure elapsed
time, peak bytes or physical energy. Archived performance diagnostics retain
their original source boundary; the full reproduction command is given below.

The prespecified validation batch contains **166 synthetic instances**: 158
feasible and eight infeasible.  It includes 13 nonuniform-footprint cases.  All
166 archived certificates are accepted by the standalone checker.  The
non-memoized oracle agrees on 90 cases of at most five nodes.  The two independent
transition reconstructions agree on all **13,570 reachable states and 46,110
edges**.  All **55** prespecified malformed-certificate/model attacks are rejected,
and both SSA renaming and topological relisting metamorphisms hold.

A separate exhaustive audit enumerates **all 7,290 two-node instances** in its
published grammar: inputs `x,w`; every unary argument and binary argument multiset
available at declaration; each node allowed in mode 0, mode 1, or either; capacity
2, 3, or 4; destructive or retaining cross-mode switches; and three fixed
footprint assignments.  It contains 3,204 feasible and 4,086 infeasible cases,
120,376 reachable states, and 320,796 edges.  Producer, checker, and independent
oracle agree for every member.  This closes only that explicit finite universe.

The ready-set extension is discriminating.  In `schedule-4-1-40`, the certified
ready-set optimum is 102 abstract units with run order `0,2,1,3,4`; the exact
fixed-list optimum is 182 and the home-sealed policy is 158.  Ten of twelve
schedule-sensitive fixtures improve strictly over fixed list order.  The original
destructive/retaining boundary pair is 52/38.

Identity matters in two distinct ways.  A reachable pair with the same completed
set, mode, resident identities, and dirty count has continuation values 22 and 30
solely because different resident values are dirty.  A nonuniform-footprint pair
with the same completed set, mode, resident count, and dirty count has continuation
values 56 and 106.  Across every archived closure, the full key creates 13,570 singleton groups, so
its zero-conflict row is a structural grouping sanity check rather than a direct
experimental validation of history erasure. Coarser projections genuinely merge
states and create:

| Projection | Ambiguous groups | Maximum finite spread |
|---|---:|---:|
| remove completed identities | 2,493 | 323 |
| retain only completed count | 482 | 105 |
| remove mode | 3,517 | 76 |
| retain only dirty count | 153 | 32 |
| remove all dirty state | 936 | 32 |
| retain only resident/dirty counts | 661 | 50 |
| retain only resident/dirty footprint totals | 591 | 14 |
| full boundary | 0 | 0 |

These are finite counterexamples to the stated coarse projections, not a universal
minimality theorem. Theorem 3, rather than the singleton full-key row, establishes
model-relative history erasure.

## Clean execution

The tested release environment is Linux x86_64 with CPython 3.13.5. The
top-level `verify.py`, `reproduce.py`, `run.py`, `pilot.py`, and `summarize.py`
drivers import the Unix-only standard-library `resource` module for CPU/RSS
observations. Full reproduction is unsupported on Windows; the standalone
standard-library unit tests, including the new bounded regressions, can run there.
Other full-campaign Unix/Python variants are untested.
No package installation, network access, GPU, model API, private data, external
solver, or service is required.

```sh
python -m unittest discover -s tests -v
python verify_bibliography.py
python verify.py
python reproduce.py --out reproduction-output
```

`verify_bibliography.py` checks the 67-row audit for complete fields, unique keys,
titles, stable locators, and pinned metadata for PipeRench, Glow, and Tiramisu. It
is an offline consistency gate, not a substitute for the recorded first-party
source inspection. `verify.py` checks all 166 archived certificates without
importing the producer and also invokes that bibliography audit.
`reproduce.py` requires a nonexistent output directory.  With one worker it:

1. runs ordinary unit-test discovery;
2. validates the complete bibliography audit;
3. checks that the archived input is exactly regenerated by the deterministic
   constructor;
4. reruns the five-case discrimination pilot without modifying frozen inputs;
5. runs the 166-case batch in two bounded chunks;
6. regenerates all summaries, projection analyses, CSV tables, and 166
   certificates;
7. reruns the 7,290-case exhaustive audit; and
8. compares every scientific JSON/CSV field and every certificate object against
   the archive.

Only wall time, CPU time, and peak RSS are excluded from deterministic equality.

The frozen-input gate compares exact UTF-8 bytes, including line endings. The
producer and checker require integer dimensions for the fixed logical tile type.
Memoized model queries belong to each parsed instance rather than a process-global
cache; the focused regressions check that completed instances are collectible and
that independently parsed graphs do not share cached readiness answers.

`scientific-checks.yml` runs the archived certificate gate and fresh reproduction
from the standalone artifact repository root on pushes to `main` or manual
dispatch. Its Ubuntu 24.04 job bounds the whole scientific command block to 300
seconds and 2 GiB of virtual memory, propagates failed gates, and uploads available
raw outputs even when a check fails. The existing material-integrity workflow
remains separate. Workflow configuration is not evidence of a successful remote run.

Manual bounded commands are:

```sh
python freeze_inputs.py --check
python run.py --out finite-results --start 0 --stop 64
python run.py --out finite-results --start 64 --stop 166
python summarize.py --out finite-results
python exhaustive_audit.py --out finite-results/exhaustive-audit.json
```

`pilot.py --out <directory>` exercises the 52/38 boundary pair, the schedule-sensitive
102/182/158 case, a fork-join case, the independent oracle, and the dirty-flush
negative control.

## Repository map

* `src/model.py` — validated bit-mask ready-set and weighted-footprint semantics.
* `src/planner.py` — reachable closure, shortest distances, and both certificate
  statuses.
* `src/checker.py` — independent set-based parser, semantics, trace, exact-closure,
  and certificate checks.
* `src/oracle.py` — non-memoized ready-node/mode/resident-subset normal-form
  enumeration.
* `src/baseline.py` — exact fixed-list policy and an exact at-most-two-mode
  home-sealed policy; the latter rejects larger mode sets.
* `src/cases.py`, `freeze_inputs.py` — deterministic validation construction.
* `exhaustive_audit.py` — complete enumeration of the declared two-node universe.
* `tests/semantic_crosscheck.py` — all-state/all-edge differential comparison.
* `tests/test_certificates.py` — 55 negative mutations and two metamorphisms.
* `tests/test_declared_domains.py` — rejects half-unit endpoints and checks the
  three-mode indirect-configuration counterexample plus home-sealed guard.
* `inputs/` — exact consumed model objects.
* `results/` — raw chunks, all certificates, tables, audits, and reproduction
  evidence.
* `proofs/semantics.md` — model, theorem statements, proofs, and assumptions.
* `claim_evidence_ledger.csv` — claim-to-proof/test/result traceability.
* `verify_bibliography.py`, `bibliography_audit.csv`, `external_resources.csv` — executable bibliography consistency check plus scholarly and official source audit; literature bytes are not redistributed.

Producer/checker ceilings are 120,000 represented states, 1,200,000 edges,
32 MiB parsed JSON, 20 nodes, 40 value names, three modes, value footprint at most
16, and mode capacity at most 32 units.  The oracle admits at most two modes, five
nodes, and five million recursive visits. The exact home-sealed macro baseline is
also restricted to at most two modes. A ceiling or domain failure is explicit,
never evidence of infeasibility.

## Scope boundary

Certificate acceptance is conditional on the supplied finite model.  Trusted
components include Python, the checker implementation, and the declared event,
footprint, and retention semantics.  Differential and exhaustive checks reduce
implementation risk but do not formally verify Python.

Concrete accelerator use would still require a semantics-preserving
schedule-to-instance lowering, address/bank/port/layout refinement, complete event
refinement, and calibrated coefficient evidence.  The artifact does not model
tensor values, functional operator correctness, banking, placement,
fragmentation, DMA, overlap, leakage, thermal history, queueing, or a real
compiler.  The 2018 thesis is used only at official-record/abstract depth because
its full bitstream was not successfully retrieved in this environment.
Independent novelty, proof, hardware, authorship, and submission review remain
external obligations.

The repository's original code and generated inputs are offered under `LICENSE`.
Cited literature is not redistributed.
