# Ready-set boundary contracts and complete finite certificates

This document gives the mathematical argument implemented by the artifact.  It is
not a proof-assistant development and has not received independent peer review.
The executable checks are exhaustive only for the supplied finite abstract
instances.  Neither the argument nor the checks calibrate physical energy.

## 1. Finite ready-set machine

Fix a finite acyclic SSA graph whose nodes are listed in one topological order.
The list is a declaration format, not an execution schedule.  Node `j` has a
fresh output name, one or two ordered operand names, an uninterpreted unary or
binary operator, and a nonempty set of allowed modes.  Each node may execute
exactly once after all producer nodes of its operands have executed.  Distinct
ready nodes may therefore be chosen in any order.  There is no recomputation,
aliasing, in-place result, action overlap, or data-dependent control.

All values are immutable and share one logical declared tile type.  The fixed
instance additionally assigns each value a positive integer footprint `f(v)` in
abstract storage/transfer units.  This footprint may represent a statically known
representation size (for example, padding or compression); it is not a byte count
or a measured energy coefficient.  A resident value is stored once even when an
operator names it twice, while scratchpad-read traffic is charged once per operand
occurrence.  Inputs initially have valid copies in an unbounded home store.  A
freshly produced value has no valid home copy until a `STORE` action.  Mode `m`
has fully associative capacity `C_m` units.  A directed mode switch either retains
all scratchpad values or destroys all of them.  Banking, address placement,
fragmentation, DMA queues, leakage, timing, and conversion costs are outside this
machine and would require new state and events.

Let `Q` be the set of completed node indices.  Define

* `A(Q)` as the inputs together with outputs of nodes in `Q`;
* `N(Q)` as required graph outputs together with operands of nodes not in `Q`;
* `L(Q) = A(Q) ∩ N(Q)` as the currently produced values that may still matter.

A state is

    s = (Q, m, R, D),

where `D ⊆ R ⊆ L(Q)` and `F(R)=Σ_{v∈R} f(v) ≤ C_m`.  `R` records resident
value identities.  `D` records the resident values without a valid home copy.
Every live value not in `D` has a valid home copy, whether resident or absent;
the complementary home-validity set therefore need not be stored explicitly.  A completed-set mask,
not merely its cardinality, is required because different completed antichains
expose different ready nodes and live values.

The initial state is `(∅, 0, ∅, ∅)`.  A node is ready when it is not in `Q` and all
producer nodes of its operands are in `Q`.  A goal has every node completed and
no dirty required output.  Goal states are absorbing in the abstract plan
language.

## 2. Actions and event vectors

`LOAD(v)` requires `v ∈ L(Q) \ R` and `F(R)+f(v)≤C_m`.  It adds `v` to `R`
and charges `f(v)` home-read and `f(v)` scratchpad-write events.  The loaded copy
is clean.

`STORE(v)` requires `v ∈ D`.  It removes `v` from `D` without removing it from
`R`, charging `f(v)` scratchpad-read and `f(v)` home-write events.

`DROP(v)` requires `v ∈ R \ D`.  It removes `v` from `R` and has the empty event
vector.  This zero is an abstract omission of unmodeled physical effects, not a
claim of zero device energy.

`SWITCH(k)` requires `k ≠ m`.  A retaining edge preserves `(R,D)` and additionally
requires `F(R) ≤ C_k`.  A destructive edge requires `D = ∅` and replaces both
sets by empty sets.  The action charges the named directed configuration event.

`RUN(j)` requires node `j` to be ready, mode `m` to be allowed for that node, all
distinct operands to be resident, and `F(R)+f(o_j) ≤ C_m` before any last-use
values are released.  It charges one operator event, `f(v)` scratchpad-read
events for every operand occurrence `v`, and `f(o_j)` scratchpad-write events.
Let `Q' = Q ∪ {j}` and let `o_j` be the fresh output.  The successor is

    (Q', m, (R ∪ {o_j}) ∩ L(Q'), (D ∪ {o_j}) ∩ L(Q')).

The strict fresh-output footprint prevents an accidental in-place
interpretation.  Projection
onto `L(Q')` may discard a dirty last-use value without a store because that value
is neither a future operand nor a required output.

The event basis consists of home reads/writes, scratchpad reads/writes, operator
kind and mode, and directed mode switches. In the executable fragment each event
`e` has an ordered closed interval `[l_e,u_e]` with integer endpoints
`l_e,u_e in Z_{>=0}`. For path `P`, let `N_e(P)` be its event count and

    lower(P) = Σ_e N_e(P) l_e,
    upper(P) = Σ_e N_e(P) u_e.

The optimization objective is minimum `upper(P)` over legal source-to-goal paths.
The additive interval inequality can be stated over nonnegative reals, but the
current parser, checker labels, and format-completeness proof are intentionally
integer-valued. A one-unary-node, capacity-two, unit-footprint instance with zero
memory charges and operator interval `[1/2,1/2]` is outside the declared executable
domain and is rejected rather than evaluated with floating point.

## 3. Preservation and conditional cost composition

**Lemma 1 (state preservation).**  Every enabled action maps a well-formed state
to a well-formed state and never loses a live dirty value.

**Proof.** `LOAD` inserts a live, backed value and checks capacity.  `STORE` makes
a dirty value backed while preserving residence.  `DROP` removes only a backed
value.  A retaining switch checks destination capacity; a destructive switch has
no dirty value to lose.  For `RUN`, every operand is resident and the fresh-slot
guard protects weighted capacity at creation.  Intersecting with `L(Q')` removes only
values with no future use and no output obligation.  Any surviving fresh output
remains dirty.  No unproduced name enters `L(Q')` because of the intersection with
`A(Q')`.  These cases preserve `D ⊆ R ⊆ L(Q')` and the capacity bound. ∎

The lemma establishes name provenance and modeled storage obligations.  It does
not prove that a concrete operator implements a numerical function or that a
physical memory implements the abstract actions.

**Theorem 2 (conditional additive interval bound).**  Suppose every concrete
occurrence represented by an abstract event is charged exactly once and its cost
lies in the declared interval for that event.  Then a checked path `P` has modeled
cost in `[lower(P),upper(P)]`.  Two fragment witnesses compose by addition when
the first exit state equals the second entry state, including completed identities,
mode, resident identities, and dirty identities.

**Proof.** Sum the lower and upper inequality for each finite event occurrence and
group equal events.  Equal boundary states and the same fixed instance (including `f`) make the witness concatenation legal;
Lemma 1 preserves the storage preconditions.  No probability or independence
assumption is used. ∎

If the uncertainty set is exactly the Cartesian product of the declared event
intervals, with one constant coefficient per event kind, `upper(P)` is the robust
cost of fixed path `P`: all event counts are nonnegative and the all-upper vector
belongs to the box.  This remains an abstract robust objective, not a measured
worst-case joule result.

The certificate field named `lower` is `lower(P)` for the selected witness.  It is
not a global lower bound on every plan; the state labels have that separate role.

## 4. Boundary sufficiency and state-space size

**Theorem 3 (history erasure).**  Two legal histories ending in the same state
`(Q,m,R,D)` have exactly the same enabled finite action suffixes.  Matching suffixes
traverse the same states and have the same event vectors.  Consequently their
minimum upper continuation values agree, including infinity when no goal is
reachable.

**Proof.** Every guard, successor, and event vector is a function only of the fixed
instance and `(Q,m,R,D)`: readiness and liveness are functions of `Q`; memory and
switch guards use `m,R,D` and the fixed footprint map; `RUN` also uses the fixed
node declaration.  Induction
on suffix length yields identical transition trees and event vectors.  The finite
reachable graph and nonnegative weights ensure that a finite minimum is attained
whenever a goal is reachable. ∎

The theorem is deliberately model-relative.  A last address, bank assignment,
queue occupancy, clock history, or thermal state would invalidate it unless added
to the boundary.

A projection is *value-exact* on a represented state set when merged states have
the same minimum upper continuation value.  A pair with equal projection and
different exact labels refutes value exactness on that set.  It does not refute a
conservative overapproximation that knowingly sacrifices precision.

For a completed set `Q`, mode `m` admits at most

    Σ_{R⊆L(Q), F(R)≤C_m} 2^{|R|} ≤ 3^{|L(Q)|}

syntactically well-formed `(R,D)` pairs: select a capacity-feasible resident set,
then any dirty subset.  Summing over modes and all `2^n` completed masks is a
finite upper bound; only dependency-closed masks and a smaller subset of storage
states are reachable.  Static footprints do not require another dynamic boundary
field because `F(R)` and all transfer multiplicities are determined by resident
identities and the bound instance.  The executable state and edge ceilings are
resource guards.  Exceeding one is an error, never an infeasibility proof.

## 5. Complete finite certificate format

Let `G=(S,E)` be the complete source-reachable transition closure reconstructed by
the checker. Because all event endpoints are nonnegative integers, every edge
weight is a nonnegative integer. A label is either an element of `Z_{>=0}` or
`dead`. Goals must have
label zero.  The checker requires every outgoing successor of every listed state
to be listed.  For each edge `s --w--> t`:

* if `label(s)=dead`, then `label(t)=dead`;
* if both labels are finite, `label(s) ≤ w + label(t)`.

The checker binds the complete instance by canonical structural equality,
validates dependency closure and all storage invariants, reconstructs transitions
with a set representation independent of the producer's bit-mask code, and
requires the listed states to be exactly the states reachable from the source:
every successor is listed and every listed state is reached by graph traversal
from the source.

A *feasible certificate* additionally contains a legal source-to-goal trace,
its exact event-count vector, and its lower/upper path sums.  Its source label must
equal the trace upper sum.

An *infeasible certificate* contains no trace or cost claim.  Its source label
must be `dead`.

**Theorem 4 (feasible-certificate soundness).**  If a feasible certificate is
accepted, the supplied trace has minimum upper cost in the declared finite model.

**Proof.** Canonical instance binding and trace replay give a legal goal path `P`
with claimed cost `U(P)`.  Exact source-reachable closure implies that every and
only source-reachable state is represented, and every outgoing transition from it
is reconstructed.  A `dead` state cannot reach a goal:
along a hypothetical path the dead-successor rule would force the goal dead,
contradicting its required zero.  Therefore every state on any complete source
path has a finite label.  Telescoping the edge inequalities on arbitrary complete
path `P'` gives

    label(source) ≤ U(P') + label(goal) = U(P').

The accepted witness satisfies `U(P)=label(source)`, so `U(P)≤U(P')` for every
complete path. ∎

**Theorem 5 (infeasible-certificate soundness).**  If an infeasible certificate is
accepted, no legal source-to-goal path exists in the declared finite model.

**Proof.** The source is labeled dead.  Along every represented outgoing edge,
deadness propagates.  Exact source-reachable closure ensures that any finite
source path remains inside the represented set.  A hypothetical source-to-goal
path would therefore label
its goal dead, contradicting the goal-zero rule. ∎

**Theorem 6 (format completeness for finite nonnegative-integer-endpoint instances).** Every
declared finite nonnegative-integer-endpoint instance whose source closure fits the checker
ceilings has an accepted certificate of exactly one status: feasible if a goal is
reachable, otherwise infeasible.

**Proof.** List the complete source-reachable closure. Nonnegative-integer edge
weights make every finite shortest upper distance an element of `Z_{>=0}`. Label
each state that can reach a goal by that distance and every other state dead. If
the source is finite, choose a shortest source-to-goal path, breaking zero-cost
ties by decreasing remaining hop count; Bellman optimality and trace replay satisfy
the feasible schema. If the source is dead, no goal is reachable and the dead-
successor condition holds, satisfying the infeasible schema. A state cannot both
reach and fail to reach a goal, so the statuses are exclusive. This proof does not
establish completeness for arbitrary real-valued endpoints. ∎

The checker need not trust the producer's shortest-path implementation.  It does,
however, reconstruct and source-traverse the whole represented closure. This
closure/label pass takes O(|S|+|E|) state and edge visits, rather than providing a
succinct sublinear proof. A feasible trace is checked in a separate pass which
enumerates d(s_i) outgoing transitions at every action, including repeated states.
For trace length T, the combined enumeration count is
O(|S|+|E|+T+sum_i d(s_i)), or coarsely O(|S|+|E|+T(1+d_max)). Infeasible
certificates have no trace term. These counts exclude parsing, bit arithmetic,
and set/guard/dictionary costs; an accepted trace need not be simple.
Python, the checker source, and the supplied model remain trusted.

## 6. Static footprints and identity-sensitive continuation

**Proposition 7 (static-footprint lift).**  Replacing unit footprints by any fixed
positive integer map `f` preserves Lemma 1, Theorems 2--6, and the boundary tuple
`(Q,m,R,D)`, provided capacity guards and transfer event multiplicities use `F`
and `f` as defined above.

**Proof.**  The map is immutable instance data.  For a fixed state, it uniquely
determines occupied capacity, every memory-action guard, and every transfer-event
multiplicity.  The preservation proof replaces cardinality inequalities by their
weighted counterparts.  The composition, history-erasure, and certificate proofs
use only deterministic guards/successors, nonnegative edge weights, and exact
instance binding, all of which remain unchanged in form. ∎

Static footprints strengthen capacity and traffic accounting without enlarging the
dynamic state tuple, but they make count-only summaries even less informative.
In the frozen `footprint-identity` closure, two reachable states have completed
set `{0,1,3}`, mode one, one resident, and one dirty resident.  In one state the
resident/dirty value is `v0`, whose footprint is three, and the exact continuation
upper value is 56.  In the other it is `v3`, whose footprint is four, and the exact
continuation value is 106.  Equal resident and dirty counts therefore do not
determine either capacity debt or continuation value.

Even aggregate footprint totals do not generally replace identities: over the
frozen 166-certificate closures, projecting `(R,D)` to only their total units
creates 591 ambiguous groups with finite spreads up to 14.  This is finite
non-redundancy evidence, not a universal minimal-bit theorem.  It is consistent
with Theorem 3: exact identities plus the immutable footprint map determine the
future; counts or totals can merge values with different future uses and
persistence obligations.

## 7. Dirty identity cannot be replaced by a count

The frozen `dirty-identity` instance contains two first-stage values `v0,v1` and
two required outputs `v2=f(v0)`, `v3=g(v1)`.  Modes have capacities three and two;
the first two nodes require mode zero, the last two require mode one, and switching
retains storage.  Consider the reachable completed set `{0,1,2}` in mode zero with
resident set `{v1,v2}` and one dirty resident.

If `v1` is dirty and required output `v2` is clean, drop clean `v2`, switch, run the
last node, and store `v3`.  The upper cost is `0+9+5+8=22`.  If `v2` is dirty and
`v1` is clean, required output `v2` must first be stored before it can be dropped,
then the same suffix costs `8+0+9+5+8=30`.  Capacity two prevents keeping both
values while creating `v3`; `v1` may die after its last use, whereas output `v2`
must be backed.  The certificate closure contains both reachable states and exact
labels 22 and 30.  Equal completed set, mode, resident identities, and dirty count
therefore do not determine continuation value; dirty identity does.

This is an existential counterexample to exact count-only merging, not a claim
that every conservative count abstraction is unsound.

## 8. When dirty debt may be prepaid

**Theorem 8 (mandatory-persistence potential).**  Fix a continuation boundary
`(Q,m,R,D)`.  Assume every name initially in `D` must obtain a valid home copy
before termination, values are immutable, each such store has a fixed timing- and
mode-independent cost `s_v`, and storing needs no extra capacity or persistent
resource state.  Let `V_D` be the minimum continuation cost and `V_clean` the value
from the otherwise identical state with those names initially clean.  Then

    V_D = V_clean + Σ_{v∈D} s_v

in the extended nonnegative reals.

**Proof.** Store every initially dirty value immediately, then follow an optimal
clean-state continuation, proving `V_D ≤ V_clean + Σs_v`.  Conversely, every
complete dirty-state continuation must contain a first store for each initial
dirty name.  Starting from the clean state, delete those first stores.  Before a
deleted store, the transformed run differs only by already having the required
home copy, so all original actions remain legal; after it, the states agree for
that name.  Truncate if the clean run reaches the absorbing goal earlier.  This
removes exactly `Σs_v` plus possibly other nonnegative costs, proving the reverse
inequality and equivalence of feasibility. ∎

The hypotheses are sufficient, not necessary.  The dirty-identity counterexample
violates mandatory persistence for `v1`: it can die after its final use.  Mode-
dependent store costs, bandwidth coupling, or timing state also invalidate the
simple potential.

## 9. Independent ready-set normal-form oracle

The independent oracle applies to at most two modes, mode-independent memory-event
costs, and at most five nodes in the artifact.  It imports neither model,
planner, nor checker.  At each stage it enumerates every currently ready node,
every allowed execution mode, and every subset of optional old residents retained
through the boundary.  It stores discarded dirty values, loads missing distinct
operands just in time, runs the selected node in a fresh slot, projects dead names,
and finally stores dirty outputs.  It uses no memoization.

**Lemma 9 (ready-set stage normal form).**  Under the oracle restrictions, if a
complete plan exists, a minimum-upper-cost plan occurs among the oracle branches.

**Proof.** Take a minimum legal plan and retain its sequence of `RUN` actions.
That sequence is a topological ready-node order and is explicitly enumerated.
Between consecutive runs:

1. Remove a load/drop pair with no intervening use and delay every remaining load
to immediately before its next run.  The value is backed, delaying it reduces
occupancy, and destructive switches only make an earlier load useless.
2. Delay each store until the first following eviction, destructive switch, or
final persistence obligation.  Dirty values remain readable and survive retaining
switches.  If a value dies first, remove its store.  Fixed mode-independent store
cost and absence of timing state preserve cost and legality.
3. With two modes, remove switch excursions.  Between current and target execution
mode, any extra switch sequence either is empty or leaves and returns.  Clean
values may be dropped explicitly and dirty values stored at the same cost; all
configuration costs are nonnegative.  This step would fail with three modes when
a cheap indirect route can beat a direct edge.
4. Across a retaining boundary, keep every already resident required operand;
evicting and reloading it cannot reduce occupancy at the run or cost.  The only
remaining choice is which optional residents survive, subject to target capacity
and the fresh output slot.  Across a destructive boundary, all dirty residents
are stored and no resident survives.

Applying these transformations stage by stage yields a no-more-expensive branch
of exactly the form enumerated.  Conversely every oracle branch expands to a legal
action trace.  The minimum branch cost therefore equals the unrestricted optimum
under the stated restrictions. ∎

The oracle is exponential and its visit ceiling is explicit.  Agreement on the
frozen small cases is implementation evidence, not scalability evidence.

## 10. Schedule inclusion and relisting

**Proposition 10 (fixed-order inclusion).**  The legal traces that execute nodes in
the supplied list order are a subset of ready-set traces.  Hence the ready-set
optimum is no larger than the exact fixed-order baseline.

**Proof.** The supplied list is topological, so the next list node is ready after
the preceding prefix completes.  Every memory and switch action is unchanged.
Thus each fixed-order trace is a ready-set trace; minimization over a superset
cannot increase the value. ∎

**Proposition 11 (home-sealed inclusion).** Traces that make storage empty and
backed between runs are a subset of ready-set traces, so the ready-set optimum is
no larger than the home-sealed optimum. The shipped macro dynamic program computes
that restricted optimum only for at most two modes and rejects larger instances.
This restriction is necessary for the implementation: in the three-mode unary
regression with zero memory/operator charges, `cfg(0,2)=10`, and
`cfg(0,1)=cfg(1,2)=1`, a legal empty-boundary route costs 2 through mode 1 while a
direct-only macro transition costs 10. The full primitive-action semantics and
checker accept the cost-2 route.

**Proposition 12 (topological relisting invariance).**  Relisting incomparable
nodes while preserving each node's operands, output, operator, and mode permissions
does not change the ready-set optimum.

**Proof.** Map each completed-index set through the bijection induced by the
relisting and leave modes and value-name sets unchanged.  Readiness, liveness,
actions, event vectors, source, and goals are preserved.  The transition graphs
are isomorphic. ∎

**Proposition 13 (plan-inclusion monotonicity).**  Increasing a mode capacity, or
replacing a destructive switch by a same-cost retaining switch while retaining
free drops of clean values, cannot increase the optimum.

**Proof.** Every old trace remains legal.  Under increased capacity no guard is
weakened against it.  For a newly retaining edge, drop every clean value that the
old destructive edge would erase; the old edge required no dirty resident.  The
same successor and cost are obtained. ∎

These are model-level monotonicities.  A physical capacity increase or retention
mechanism may change coefficients, leakage, timing, or routing, which lies outside
the proposition.

## 11. Executable correspondence, exhaustive audit, and limits

The producer represents `Q,R,D` as integers; the checker independently represents
them as sets.  The frozen differential test enumerates every reachable state and
compares the full action, successor, and event-vector set of the two
implementations.  This greatly narrows accidental semantic drift but is not an
independent formal proof of either program.

The frozen validation uses 166 prespecified synthetic DAGs and stipulated
interval coefficients.  In addition, a separately generated exhaustive universe
contains all 7,290 two-node instances under the declared audit grammar: two
inputs; every unary argument and binary argument multiset available at declaration;
each node permitted in mode zero, mode one, or either; capacities two, three, or
four; destructive or retaining cross-mode switches; and three fixed footprint
assignments.  The producer, checker, and non-memoized oracle agree on feasibility
and exact feasible upper cost for every member.  This closes that explicit finite
universe only; it is neither a proof for larger graphs nor application coverage.

The supplied validation uses synthetic DAGs and stipulated interval coefficients.
It does not execute tensor arithmetic, bind a real compiler schedule, calibrate a
device, model banks or DMA overlap, or establish practical scalability.  Applying
the contract to hardware would require at least: a semantics-preserving lowering
from a concrete schedule; refinement of capacity, address, and retention behavior;
a complete event map; and calibrated coefficient evidence whose uncertainty set
matches the theorem's assumptions.
