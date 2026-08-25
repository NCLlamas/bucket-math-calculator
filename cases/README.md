# Bucket Calculation — Validation Cases

Input/output fixtures for validating an implementation of
[`bucket-calculations-spec.md`](../bucket-calculations-spec.md). The spec is the only
context this suite assumes.

> ⚠️ **Grading artifact, not implementation input.** The
> [Spec coverage map](#spec-coverage-map) records a correct answer to a question the
> spec deliberately does not answer (**O-4**). Give an implementation under test the
> spec, and `cases/inputs/` if you want it self-testing — not this file.

## Layout

```
cases/
├── inputs/<case-id>.json     bare BucketCalculationInput — nothing else in the file
├── expected/<case-id>.json   expected BucketCalculationOutput for the same id
├── input-index.json          input side only: ordered ids + metadata + class ranks
└── manifest.json             linked view: id → input path, expected path, tags
```

Inputs and expectations are joined by **filename stem only**. Neither file points at
the other, and neither carries a `case_id` field.

* `cases/inputs/` is usable alone: every file is a complete, standalone input
  payload. `input-index.json` carries the ordered id list, descriptions and class
  ranks, and sits one level up so it never pollutes a "read every `*.json` in this
  dir" loop. The `invalid-*` inputs are malformed on purpose and must be rejected —
  filter them by prefix if you only want well-formed payloads.
* `cases/expected/<stem>.json` grades the result.
* `manifest.json` is the both-sides view for a runner that wants one file.

Cases are cited below by numeric prefix — `cap-13`, `scenario-08`. Each prefix
identifies exactly one case; the filename appends a descriptive slug
(`cap-13-uneven-addons-average-overage.json`).

### Class ranks

Spec §1 *Class ranking* defines `rank()` as caller-supplied configuration and fixes
no class names. This suite supplies the configuration, published under `class_ranks`
in both `input-index.json` and `manifest.json`:

* branch probes: `TIER_1 < TIER_2 < TIER_3 < TIER_4`
* composite scenarios: `BASIC < ECONOMY < PREMIUM_ECONOMY < BUSINESS < FIRST`

`class_ranks` is on the input side as well as the manifest, so a container fed only
`cases/inputs/` plus `input-index.json` can rank without out-of-band knowledge.

These are two disjoint sets published as one map. Per R1 a deployment configures a
single set, so no case mixes them; `generate_cases.py` refuses to emit a case that
does, or that names a class outside the map. The overlapping integers (`TIER_1` and
`BASIC` are both 1) are harmless under R3 — only relative order within a set matters.

## Running

```bash
python3 tools/validate_cases.py
```

Self-checks the fixtures against `tools/reference_impl.py`, a literal transcription
of spec §3. Currently **47/47 passed**. Any `FAIL` or `xfail` is a regression.

```bash
python3 tools/validate_cases.py --cmd "docker run --rm -i bucket-calc"
```

Grades any command that reads one input JSON on stdin and writes one output JSON on
stdout. `--filter` narrows by substring — `scenario-`, `cap-`, `invalid-`.

## Provenance

Recorded per case in `manifest.json` as `expected_from`.

| | Count | Expectation | What passing proves |
|---|---|---|---|
| `derived` | 26 | Computed from `reference_impl.py`, so input and expectation cannot drift apart | Self-consistency with the spec as written |
| `fixed` | 10 | Transcribed from an independently established ground truth, never computed | Correctness — a fixed expectation can contradict the spec |
| `constraint` | 11 | The set of C-clauses the input must fail, cross-checked against the reference at generation time | Malformed input is rejected rather than silently absorbed |

A derived fixture cannot catch a wrong spec: if the spec is wrong, the fixture is
wrong in the same direction and passes. Only `fixed` and `constraint` cases can
disagree with the spec.

A fixed expectation is only as good as the conditions under which its ground truth
was captured. When one contradicts the spec, rule out "captured under different
preconditions" before concluding the spec is wrong.

The generator runs the reference over every fixed case and writes any difference
into a `divergence_from_spec` block on the expected file. There are currently none.

## Comparison rules

| Field | Rule |
|-------|------|
| Money | ±0.01 tolerance, never exact equality |
| `violations` | compare as a **set of `(code, status)`**; `message` wording is unspecified, so it is informational only |
| `applicable == false` | assert `allocation == null` **and** `overage == 0` (O3). Says nothing about `violations`, which may be non-empty |
| `raises: true` | the input **must be rejected**. Compare the **set** of `failures` constraint ids; messages are informational |
| `assert_skip` | field names to skip for this case. The fixed scenarios carry `["derived"]` — see **O-2** |
| `reconciliation` | diagnostic block: `sum_of_buckets`, the O1 `target`, `overage_basis` and `total` side by side. **Not** part of the output contract |
| `note`, `divergence_from_spec`, `source` | metadata, never asserted |

A calculator signals rejection to `--cmd` by **exiting non-zero**. If it emits
`{"failures": [...]}` on stdout or stderr — entries as ids or as
`{"constraint": ...}` objects — the ids are compared; if it names none, the bare
rejection is accepted.

## Coverage

**47 cases** in three groups.

### Branch probes (26) — `provenance: spec:<section>`

16 CAP, 10 CLASS. Each isolates one path through spec §3. Every branch is hit, plus
these boundaries: `item_per == cap` exactly, `bc == room` exactly, `owed_per == 0`,
`fee_rate == 0`, `len(buyers) == 1`, the `cap == 0` sentinel on both add-on paths,
and a total that does not divide evenly across buyers.

### Composite scenarios (10) — `provenance: scenario:<n>`

8 CAP, 2 CLASS. Each combines several policy conditions at once.

| Case | Mode | What it pins down |
|---|---|---|
| `scenario-01-in-policy-no-violations` | CAP | Clean in-policy pass, no split |
| `scenario-02-class-benchmark-below-cap` | CLASS | Benchmark at the **same rank** as the selection |
| `scenario-03-add-ons-not-allowed-no-cap` | CAP | `cap == 0` + disallowed add-on → positive overage with **no `CAP` violation** |
| `scenario-04-not-included-buyer` | CAP | Not-included buyer pays share + fee; buckets exceed `total` by exactly that fee |
| `scenario-05-class-no-benchmark-requires-approval` | CLASS | No benchmark, no cap → approval |
| `scenario-06-over-cap` | CAP | Policy funds cap, buyer funds excess |
| `scenario-07-large-values-over-cap` | CAP | Small excess on a large base — precision guard |
| `scenario-08-add-ons-partial-cap-room` | CAP | All four buckets non-trivial at once |
| `scenario-09-multi-buyer-all-included` | CAP | Both buyers inside the included count |
| `scenario-10-stacked-add-ons-and-over-cap` | CAP | Two violations, overage sums both |

`scenario-08` is the highest-value fixture in the suite: the only case where all four
buckets carry distinct non-trivial values (`covered.item` 687.52,
`covered.buyer_cost` 12.48, `owed.item` 0, `owed.buyer_cost` 172.40). Any error in
the `min`/`max` cap-room arithmetic fails here.

CLASS mode is thinner than CAP: only 2 of the 10 scenarios exercise it, both
single-buyer with no add-ons. CLASS combined with multiple buyers, with add-ons, or
with a not-included buyer is covered by derived cases only.

### Constraint rejections (11) — `provenance: spec:C<n>`

Inputs that must be rejected, one or more failing clauses each. Each expected file's
`note` records what a caller receives if the clause is not checked.

| Case | Clauses | Damage it prevents |
|---|---|---|
| `invalid-01-no-buyers` | C1, C3 | `ZeroDivisionError` — a language fault, not a domain error |
| `invalid-02-negative-total` | C1, C2 | Reads as `applicable=false` — a clean in-policy pass |
| `invalid-03-item-cost-exceeds-total` | C2 | Inert with add-ons allowed; **doubles** the overage without |
| `invalid-04-add-on-aggregate-mismatch` | C3 | Buckets sum to 940 against a total of 1000 |
| `invalid-05-negative-cap` | C4 | Negative cap takes the **unlimited** branch |
| `invalid-06-fee-rate-as-percent` | C5 | `owed.total` 104.00 → **500.00**, every bucket still correct |
| `invalid-07-fee-rate-at-upper-bound` | C5 | Boundary: `Rate` is strict, so `1.0` fails |
| `invalid-08-class-context-in-cap-mode` | C6 | None — enforced because scope is uniform, not severity-ranked |
| `invalid-09-class-mode-without-context` | C6 | `KeyError` |
| `invalid-10-negative-buyer-cost` | C1, C3 | Negative `owed.buyer_cost`, violating O2 |
| `invalid-11-stacked-failures` | C2, C4, C5 | Three clauses at once — proves all-at-once reporting |

Two caveats when grading with these:

* **`invalid-01` and `invalid-09` are satisfiable by accident.** Both crash even
  without validation (`ZeroDivisionError`, `KeyError`), and a bare non-zero exit is
  accepted as a rejection. Against a calculator that skips validation entirely, 9 of
  the 11 fail but these 2 pass. They prove nothing on their own.
* **`invalid-03` shows why scope is uniform.** The identical bad `item_cost` is inert
  when `are_buyer_costs_allowed` is true and doubles the buyer's charge when it is
  false. Severity is not a property of the clause, so no clause can be exempted.

---

## Spec coverage map

What an implementer can take straight from the spec, what must be inferred, and what
the spec does not answer. Use this to separate *following stated rules* from *making
assumptions*.

| Tier | A mismatch means |
|------|------------------|
| **Explicit** | A reading failure. No assumption to credit, no context that would have helped. |
| **Implicit** | An assumption. The spec permits the reading; the question is whether the choice was recognised as one. |
| **Open** | A judgement call the spec does not license. Expected — what matters is whether the gap was surfaced. |

### Explicit — stated outright

Directly transcribable. No interpretation required and no defensible reason to
differ.

| # | Element | Where | Pinned by |
|---|---------|-------|-----------|
| E-1 | `item_per`, `overage_basis`, `total_per` derivations; included/excluded partition | §3 preamble | every case |
| E-2 | CAP branch tree: `cap > 0`, `item_per > cap`, `room`, the `min`/`max` clamps | §3 Mode A | `cap-02`…`cap-06`, `scenario-08` |
| E-3 | Both `this_overage` formulas — average-based when add-ons allowed, item-based otherwise | §3 Mode A | `cap-06`, `cap-07`, `scenario-10` |
| E-4 | `cap == 0` disables the **cap comparison only**; other policy rules still generate overage, so a disallowed add-on is still owed *and* still overage | Terminology, C4, §3 Mode A | `cap-08` (allowed → nothing owed), `cap-09` / `scenario-03` (disallowed → overage) |
| E-5 | Not-included buyers pay `item_per + fee`; `excluded_cost` accumulation | §3 Mode A | `cap-10`…`cap-12`, `scenario-04` |
| E-6 | Finalize **ordering** — not-applicable check, then violations, then `overage += excluded_cost` last | §3 Mode A (marked "order matters") | `cap-11`, `cap-12` |
| E-7 | Violation gates: `CAP` needs `overage > 0` **and** `cap > 0`; `NOT_INCLUDED` needs `excluded_cost > 0` | §2 table, §3 finalize | `cap-09`, `cap-12` |
| E-8 | `BUYER_COST_NOT_ALLOWED` — condition, `REQUIRES_APPROVAL` status, mode-independent | §2 table, §3 preamble | `scenario-03`, `scenario-10`, `cap-07`, `cap-09` |
| E-9 | Violations survive a not-applicable return: `allocation == null` with a non-empty `violations` list is valid | §2, O3 | `class-04`, `class-05`, `scenario-05` |
| E-10 | CLASS `eligible()` — all three clauses (rank, `allowed_classes`, cap) | §3 Mode B | `class-06`, `class-07` |
| E-11 | `rank()` is caller-supplied configuration, total over the configured set, order-only, stable, and attaches to class values not options (R1–R5) | §1 Class ranking | `class-02`, `scenario-02`; enforced by `generate_cases.py` |
| E-12 | CLASS `best` = highest rank, then highest cost | §3 Mode B | `class-02`, `scenario-02` |
| E-13 | Three-way benchmark resolution and the two `reason` strings | §3 Mode B | `class-01`, `class-03`, `class-04` |
| E-14 | CLASS `owed_per <= 0` → not applicable, `REQUIRES_APPROVAL` | §3 Mode B | `class-05` |
| E-15 | CLASS add-on override — always owed, `covered.buyer_cost` zeroed | §3 Mode B | `class-08`, `class-10` |
| E-16 | Post-step totals; fee charged **forward** | §3 Post-step | `cap-15`, all derived cases |
| E-17 | Fee **back-out** formula for reconciling an externally-bundled total | §2 | *not covered — see below* |
| E-18 | C1–C7 as stated conditions; O2 non-negativity; O3 shape when not applicable | §1, §2 | all cases |
| E-19 | Validation is the function's job: it **raises**, up front, with **all** failing clauses at once, uniformly across C1–C7 | §1 Validation | the 11 `invalid-*` cases |
| E-20 | Every `Money` comparison carries ±0.01; `Rate` is strict; counts exact | §1 Money tolerance | `invalid-04`, `invalid-07` |
| E-21 | O1 reconciles to `total + (n_excluded × buyer_not_included_fee)`; `overage_basis` is a yardstick, never a bucket or a reconciliation target | §2 O1, §3 preamble | all 47; enforced at generation |

### Implicit — inferable, but a choice was made

The spec does not say, but a careful reading yields a defensible answer. Each row has
a plausible alternative that produces different output. **These are the rows where an
implementation reveals its assumptions** — check whether the choice was made
deliberately and written down, or made silently.

| # | Question the spec leaves unanswered | Defensible reading | Plausible-but-wrong alternative | Pinned by |
|---|---|---|---|---|
| I-1 | What `covered_buyer_count` counts | `len(included)` | buyers actually funded *within cap* — differs whenever an included buyer is over cap | `scenario-04` (1 of 2), `cap-11` |
| I-2 | Whether `round()` belongs anywhere beyond the four stated sites | No — leave everything else unrounded | Rounding `owed.item` too, which "fixes" a cent gap that is intentional | `cap-14` (`overage` 99.99 vs `owed.item` 100.00) |
| I-3 | float or Decimal | float — the spec notes float is current and Decimal is the *hardening target*, i.e. not yet | Decimal, which changes last-cent results | `cap-14`, `scenario-07` |
| I-4 | Whether `violations` list order is significant | No — treat as a set | Asserting a fixed order | `scenario-10` (two violations) |
| I-5 | Money formatting inside `message` strings | Unspecified; do not assert | Inventing a format and asserting it | all violation cases |
| I-6 | CLASS `covered.buyer_cost += bc` before the override | Dead code whenever `buyer_cost == 0`, since C3 forces every `bc` to 0 — safe to simplify | Treating it as load-bearing | `class-08` |
| I-7 | Whether CLASS mode emits `NOT_INCLUDED` | No — the pseudocode is silent | Adding it "helpfully"; reads like an omission | `class-09` (**derived only**) |
| I-8 | Whether `alternate_classes` may hold entries at the selected rank, or duplicates | Yes — `rank(opt) <= rank(selected)` permits both | Assuming strictly lower rank, which discards the correct benchmark | `class-02`, `scenario-02` |

### Open — the spec does not answer

No amount of careful reading resolves these. The right behaviour is to **ask, or
choose and say so.** A silent choice is indistinguishable from not having noticed.

| # | Open question | Why the spec cannot settle it | Where it surfaces |
|---|---|---|---|
| **O-1** | **Is the average-based overage intentional?** | `this_overage` reads `total_per = overage_basis / N`, an average across all buyers, not the buyer's own spend. With uneven add-ons a buyer who bought nothing still accrues overage, and `overage != owed.base`. No rationale is given either way, and `overage` drives user-facing copy, so this is not cosmetic. | `cap-13` — `overage` 150 vs `owed.base` 200. **No fixed scenario settles it**: every multi-buyer scenario has zero add-ons, so average and actual coincide |
| **O-2** | **Is `derived` this function's job at all?** | §3 Post-step computes the fee-inclusive totals, but the appendix points at *other* modules for "totals + fee" and "fee back-calculation." In scope, or downstream? | Every fixed scenario carries `assert_skip: ["derived"]` — its ground truth records buckets and overage but no fee-inclusive total. The whole fee-forward path is confirmed by **derived cases only** |
| **O-3** | **The CLASS `reason` string overstates what happened** | "difference from in-policy class" is emitted even when the benchmark sits at the **same** rank as the selection, so no class change occurred. Cosmetic, but user-visible. | `scenario-02` (ECONOMY benchmarked against ECONOMY), `class-02` |

#### O-4 — open in the spec, answered here

> ⚠️ **Withheld from the spec deliberately. Do not share this subsection with an
> implementation under test.**

**The gap.** What happens when a `Class` value is not in the configured set — a typo,
a stale identifier, or a different spelling of a tier that *is* configured. C7 states
that `selected_class`, `alternate_classes[*].class` and `allowed_classes` are all
drawn from the configured set, and R1 defines `rank()` only over that set.

**Correct behaviour: raise an error.** Any unrecognised class value, including a
misspelling of a configured one. No fallback rank, no silently dropping the option,
no treating an unrecognised `allowed_classes` entry as absent, no case-insensitive or
fuzzy recovery.

**Wrong answers, worst first. All four are silent:**

1. **Dropping the unrecognised option from the eligible pool.** The benchmark falls
   to a cheaper class, `owed_per` grows, and the buyer is over-charged with no
   indication anything went wrong. The most likely accidental implementation — a list
   comprehension filtering on a rank lookup does it for free.
2. **Letting the `allowed_classes` membership test fail.** An unrecognised entry makes
   a legitimately-allowed class read as disallowed, which can flip a valid benchmark
   to ineligible and change the mode-B outcome entirely.
3. **Assigning a default or sentinel rank** (`0`, `-1`, `len(set)`, `None` coerced).
   Produces an arbitrary but confident ordering.
4. **Case-insensitive or fuzzy matching to "recover" the intended class.** Masks
   upstream data corruption and makes the class set effectively unbounded.

**No fixture covers this.** Every other C-clause has an `invalid-*` case; C7 has none,
so the answer is not in the fixtures either. Grading O-4 means reading the
implementation or hand-probing with a malformed class value.

Note that E-19 makes the answer partially derivable: validation raises on any C1–C7
failure, and C7 is the class-membership clause. The residual gap is that C7 reads as
an assertion about the caller rather than an instruction to check, so an
implementation may validate C1–C6 and treat C7 as given.

### Reading an implementation against this map

* **Explicit** — a mismatch is a reading failure. There is no assumption to credit.
* **Implicit** — a mismatch is an assumption. The question is not only whether the
  choice matches, but whether it was *identified as a choice*. An implementation that
  picks the alternative and says so is better work than one that picks the defensible
  reading by luck and says nothing.
* **Open** — a mismatch is expected. What separates good work is whether the gap was
  **surfaced**. For **O-4**, grade on reasoning rather than compliance: raising
  because the author considered malformed input is the signal; raising because a dict
  lookup happened to throw is not, and the difference shows in whether the behaviour
  is deliberate, tested, or mentioned at all.

A green suite bounds what it proves. Passing every `derived` case demonstrates
self-consistency with the spec, not correctness. Passing every `invalid-*` case is
weaker than it looks, since two of the eleven are satisfied by an accidental crash.
And no fixture reaches **O-4** at all.

## Not covered

* **A C7 rejection case.** Every other clause has one. C7 is omitted so the fixtures
  do not give away the **O-4** answer.
* **The fee back-out direction (E-17).** §2 defines
  `fee_component = external_total × rate / (1 + rate)` for reconciling an external
  total that already bundles the fee. A separate function taking different inputs; it
  needs its own fixture set. **O-2** makes this more urgent, not less.
* **CLASS mode with multiple buyers, add-ons, or a not-included buyer.** Derived cases
  only (`class-08`, `class-09`, `class-10`) — self-consistent, unverified.
