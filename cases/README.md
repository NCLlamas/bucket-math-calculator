# Bucket Calculation — Validation Cases

Input/output fixtures for validating an implementation of
[`bucket-calculations-spec.md`](../bucket-calculations-spec.md).

The spec is the only context this suite assumes. Nothing here refers to any
external system, ticket, or upstream implementation.

## Layout

```
cases/
├── inputs/<case-id>.json     bare BucketCalculationInput — nothing else in the file
├── expected/<case-id>.json   expected BucketCalculationOutput for the same id
├── input-index.json          input side only: ordered ids + metadata + class ranks
└── manifest.json             linked view: id → input path, expected path, tags
```

**Inputs and expectations are joined by filename stem only.** Neither file contains
a pointer to the other, and neither carries a `case_id` field. So:

* To exercise a calculator with no expectations at hand, mount or copy
  `cases/inputs/` alone. Every file in it is a valid, complete, standalone input
  payload — glob the directory and pipe each file in. `input-index.json` gives you
  the ordered id list and descriptions if you want them, and it lives one level up
  so it never pollutes a "read every `*.json` in this dir" loop.
* To grade the results, join the calculator's output back to
  `cases/expected/<stem>.json`.
* `manifest.json` is the both-sides view for a test runner that wants one file.

### Class ranks

`Class` is a ranked set that the spec deliberately leaves outside the input payload,
and never defines (see open item **O-1**). This suite supplies one universe covering
both case groups:

* branch probes: `TIER_1 < TIER_2 < TIER_3 < TIER_4`
* composite scenarios: `BASIC < ECONOMY < PREMIUM_ECONOMY < BUSINESS < FIRST`

The authoritative map is published in both `input-index.json` and `manifest.json`
under `class_ranks`.

## Running

```bash
python3 tools/validate_cases.py
```

Self-checks the fixtures against `tools/reference_impl.py`, a literal transcription
of spec §3. Currently **36/36 passed**. Any `FAIL` or `xfail` is a regression.

```bash
python3 tools/validate_cases.py --cmd "docker run --rm -i bucket-calc"
```

Grades any command that reads one input JSON on stdin and writes one output JSON on
stdout. `--filter` narrows by substring — `--filter scenario-` for the composite
scenarios, `--filter cap-` for the CAP branch probes.

## Where expected outputs come from

Two provenances, recorded per case in `manifest.json` as `expected_from`:

* **`derived`** (26 cases) — computed by `tools/generate_cases.py` from
  `tools/reference_impl.py`, so input and expectation cannot drift apart.
* **`fixed`** (10 cases) — transcribed from an independently established ground
  truth, never computed. Defined in `tools/case_table_scenarios.py`.

**The distinction matters more than it looks.** A derived fixture can only confirm
what the spec already says: if the spec is wrong, the fixture is wrong in the same
direction and passes anyway. A fixed fixture can *disagree* with the spec, and when
it does the fixture wins and the spec has a defect.

This is not hypothetical. An earlier round of this suite ran **26/26 green on the
derived cases while three of them encoded the wrong answer** — `cap-09` had the wrong
`applicable`, the wrong `overage`, and a missing violation. Nothing in the derived
set could have caught it. Only the fixed scenarios broke the tie, which is what
drove the corresponding spec corrections.

The generator runs the reference implementation over every fixed case too, and
writes any difference into a `divergence_from_spec` block on the expected file. There
are currently none.

### Citation convention

Cases are cited below by numeric prefix — `cap-13`, `scenario-08`. Each prefix
identifies exactly one case; the fixture filename appends a descriptive slug
(`cap-13-uneven-addons-average-overage.json`). `manifest.json` lists every full id.

## Comparison rules

| Field | Rule |
|-------|------|
| Money | ±0.01 tolerance, never exact equality |
| `violations` | compare as a **set of `(code, status)`**; `message` wording is unspecified, so it is informational only |
| `applicable == false` | assert `allocation == null` **and** `overage == 0` (O3). Says nothing about `violations`, which may be non-empty |
| `assert_skip` | field names to skip for this case. The fixed scenarios carry `["derived"]` — see open item **O-5** |
| `reconciliation` | diagnostic block added by the generator — **not** part of the output contract. See **O-2** |
| `divergence_from_spec` | provenance metadata, never asserted |

## Coverage

**36 cases**, in two groups distinguished by the `provenance` field.

### Branch probes (26) — `provenance: spec:<section>`

16 CAP, 10 CLASS. Each isolates one path through spec §3. Every branch is hit, plus
these boundaries: `item_per == cap` exactly, `bc == room` exactly, `owed_per == 0`,
`fee_rate == 0`, `len(buyers) == 1`, the `cap == 0` sentinel on both add-on paths,
and a total that does not divide evenly across buyers.

### Composite scenarios (10) — `provenance: scenario:<n>`

8 CAP, 2 CLASS. Each combines several policy conditions at once, with a fixed
expected output.

| Case | Mode | What it pins down |
|---|---|---|
| `scenario-01-in-policy-no-violations` | CAP | Clean in-policy pass, no split |
| `scenario-02-class-benchmark-below-cap` | CLASS | Benchmark at the **same rank** as the selection |
| `scenario-03-add-ons-not-allowed-no-cap` | CAP | Unlimited cap + disallowed add-on → violation with **no allocation** |
| `scenario-04-not-included-buyer` | CAP | Not-included buyer pays share + fee; buckets exceed `total` |
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

CLASS mode is thinner than CAP by design of the source material: only 2 of the 10
scenarios exercise it, both single-buyer with no add-ons. CLASS combined with
multiple buyers, with add-ons, or with a not-included buyer is covered **only** by
derived cases — so those paths are confirmed self-consistent, not confirmed correct.

---

## Spec coverage map — explicit, implicit, and open

What an implementer can take straight from the spec, what they must infer, and what
the spec cannot tell them at all. Use this to separate *following stated rules* from
*making assumptions*: a wrong answer in the first tier is a reading failure, a choice
in the second tier is an assumption, and a choice in the third tier is a judgement
call the spec does not license.

### Explicit — stated outright

Directly transcribable. No interpretation required, and no defensible reason to
differ. Getting one of these wrong means the spec was not read carefully.

| # | Element | Where | Pinned by |
|---|---------|-------|-----------|
| E-1 | `item_per`, `basis`, `total_per` derivations; included/excluded partition | §3 preamble | every case |
| E-2 | CAP branch tree: `cap > 0`, `item_per > cap`, `room`, the `min`/`max` clamps | §3 Mode A | `cap-02`…`cap-06`, `scenario-08` |
| E-3 | Both `this_overage` formulas — average-based when add-ons allowed, item-based otherwise | §3 Mode A | `cap-06`, `cap-07`, `scenario-10` |
| E-4 | `cap == 0` is unlimited and contributes **nothing** to overage | Terminology, C4, §3 Mode A | `cap-08`, `cap-09`, `scenario-03` |
| E-5 | Not-included buyers pay `item_per + fee`; `excluded_cost` accumulation | §3 Mode A | `cap-10`…`cap-12`, `scenario-04` |
| E-6 | Finalize **ordering** — not-applicable check, then violations, then `overage += excluded_cost` last | §3 Mode A (marked "order matters") | `cap-11`, `cap-12` |
| E-7 | Violation gates: `CAP` needs `overage > 0` **and** `cap > 0`; `NOT_INCLUDED` needs `excluded_cost > 0` | §2 table, §3 finalize | `cap-09`, `cap-12` |
| E-8 | `BUYER_COST_NOT_ALLOWED` — condition, `REQUIRES_APPROVAL` status, mode-independent, emitted even when not applicable | §2 table, §3 preamble | `scenario-03`, `scenario-10`, `cap-07`, `cap-09` |
| E-9 | CLASS `eligible()` — all three clauses (rank, `allowed_classes`, cap) | §3 Mode B | `class-06`, `class-07` |
| E-10 | CLASS `best` = highest rank, then highest cost | §3 Mode B | `class-02`, `scenario-02` |
| E-11 | Three-way benchmark resolution and the two `reason` strings | §3 Mode B | `class-01`, `class-03`, `class-04` |
| E-12 | CLASS `owed_per <= 0` → not applicable, `REQUIRES_APPROVAL` | §3 Mode B | `class-05` |
| E-13 | CLASS add-on override — always owed, `covered.buyer_cost` zeroed | §3 Mode B | `class-08`, `class-10` |
| E-14 | Post-step totals; fee charged **forward** | §3 Post-step | `cap-15`, all derived cases |
| E-15 | Fee **back-out** formula for reconciling an externally-bundled total | §2 | *not covered — see below* |
| E-16 | C1–C7 as stated conditions; O2 non-negativity; O3 shape when not applicable | §1, §2 | all cases |
| E-17 | `fee_rate` default 0.04, `Rate` in `[0,1)`, `Money` 2 dp | §1, Types | `cap-15` |

### Implicit — inferable, but a choice was made

The spec does not say, but a careful reading yields a defensible answer. Each row
has a plausible alternative that produces different output. **These are the rows
where an implementation reveals its assumptions** — check whether the choice was
made deliberately and written down, or made silently.

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
| I-9 | Whether this function validates C1–C7 or trusts its caller | Either is defensible; the spec calls them conditions, not a validation step | Silently proceeding on invalid input | *not covered — see O-7* |

### Open — the spec cannot answer

No amount of careful reading resolves these. The right behaviour is to **ask, or
choose and say so.** A silent choice here is the strongest signal in the suite,
because it is indistinguishable from not having noticed.

| # | Open question | Why the spec cannot settle it | Where it surfaces |
|---|---|---|---|
| **O-1** | **The class rank ordering itself** | C7 says classes are "rankable" and the terminology table says higher rank = higher tier, but the ordered set is never given. `rank()` is literally unwritable. A hard blocker, not a judgement call. | Every CLASS case. This suite supplies a map in `manifest.json` → `class_ranks` |
| **O-2** | **Does O1 reconcile against `basis` or `total`?** | O1 says `basis`. But `basis = item_cost` when add-ons are disallowed, while the algorithm still routes add-ons into `owed.buyer_cost` — so the buckets sum to `total`. **O1 is unsatisfiable as written.** An implementer who codes it as a runtime assertion ships something that fails on valid input. | `cap-07`, `cap-09`, `class-10`, `scenario-03`, `scenario-10`. The `reconciliation` block records `sum_of_buckets`, `basis` and `total` side by side so the conflict is visible |
| **O-3** | **"Never creates cost" vs the not-included fee, which creates cost** | The preamble states the function never creates cost. The not-included loop adds `buyer_not_included_fee` to `owed.item`, so the buckets exceed the input by `n_excluded × fee`. Both cannot be true. | `scenario-04` — buckets total 1215.80 against a `total` of 1180.80, over by exactly the 35.00 fee |
| **O-4** | **Is the average-based overage intentional?** | `this_overage` reads `total_per = basis / N`, an average across all buyers, not the buyer's own spend. With uneven add-ons a buyer who bought nothing still accrues overage, and `overage != owed.base`. No rationale is given either way, and since `overage` drives user-facing copy this is not cosmetic. | `cap-13` — `overage` 150 vs `owed.base` 200. **No fixed scenario settles it**: every multi-buyer scenario has zero add-ons, so average and actual coincide |
| **O-5** | **Is `derived` this function's job at all?** | §3 Post-step computes the fee-inclusive totals, but the appendix points at *other* modules for "totals + fee" and "fee back-calculation." In scope, or downstream? | Every fixed scenario carries `assert_skip: ["derived"]` — its ground truth records buckets and overage but no fee-inclusive total. The whole fee-forward path is therefore confirmed by **derived cases only** |
| **O-6** | **What is the canonical form of a `Class` identifier?** | Never stated. `allowed_classes` membership and `alternate_classes[*].class` must agree on one spelling, and nothing says which. Real inputs can carry two incompatible forms in one record, in which case membership tests fail silently rather than erroring. | `class-06` (membership filtering), `scenario-02`, `scenario-05` |
| **O-7** | **What does the function return on a C1–C7 violation?** | §1 defines the constraints; §2 defines only the success shape. Raise? Return `applicable: false`? A third shape? Unanswerable. | *Nothing — no fixture can be written until the shape exists* |
| **O-8** | **The CLASS `reason` string overstates what happened** | "difference from in-policy class" is emitted even when the benchmark sits at the **same** rank as the selection, so no class change occurred. Cosmetic, but user-visible. | `scenario-02` (ECONOMY benchmarked against ECONOMY), `class-02` |

### Reading an implementation against this map

* **Explicit tier** — a mismatch is a reading failure. There is no assumption to
  credit and no context that would have helped.
* **Implicit tier** — a mismatch is an assumption. The question is not only whether
  the choice matches, but whether it was *identified as a choice*. An implementation
  that picks the alternative and says so is better work than one that picks the
  defensible reading by luck and says nothing.
* **Open tier** — a mismatch is expected. What separates good work is whether the
  gap was **surfaced**. Silently picking a side reads identically to never having
  seen the problem, and O-2 in particular will make an implementation crash or
  silently misreport depending on which side is taken.

One asymmetry worth holding onto: an implementation that satisfies every **derived**
case has demonstrated self-consistency with the spec, not correctness. Only the
**fixed** scenarios can contradict the spec, and O-2 through O-8 are exactly the
places where the spec is contradictory, silent, or self-undermining.

---

## Not covered

* **Invalid-input cases (C1–C7 violations).** Blocked on **O-7** — the spec defines
  the constraints but no error shape, so there is nothing to assert against. Once a
  shape exists, these are worth adding: `Σ buyer.buyer_cost != item.buyer_cost` (C3),
  `item_cost > total` (C2), `fee_rate == 1` (C5), `upgrade_context` present in CAP
  mode (C6), empty `buyers` (C1).
* **The fee back-out direction (E-15).** Spec §2 defines
  `fee_component = external_total × rate / (1 + rate)` for reconciling an external
  total that already bundles the fee. That is a separate function taking different
  inputs, so it needs its own fixture set. **O-5** makes this more urgent, not less.
* **CLASS mode with multiple buyers, add-ons, or a not-included buyer.** Derived
  cases only (`class-08`, `class-09`, `class-10`) — self-consistent, unverified.

## Adding cases

**A branch probe** (derived expectation) goes in `tools/case_table.py` with
`provenance="spec:<section>"`. **A composite scenario** (fixed expectation) goes in
`tools/case_table_scenarios.py` with `provenance="scenario:<n>"` and an
`expected_override` holding the transcribed ground truth. Then:

```bash
python3 tools/generate_cases.py
```

For a fixed case the generator writes the ground truth as the expectation, runs the
spec reference over the same input, and records any difference as
`divergence_from_spec`. It prints every divergence on stdout — **treat each new one
as a finding to adjudicate, never as a fixture to regenerate.** There are currently
zero, so any output from that step is new information.

Removing a case from either table also deletes its fixture files, so a retired case
cannot linger as an orphan.
