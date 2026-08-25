# Bucket Calculation — Validation Cases

Input/output fixtures for validating an implementation of
[`bucket-calculations-spec.md`](../bucket-calculations-spec.md).

The spec is the only context this suite assumes. Nothing here refers to any
external system, ticket, or upstream implementation.

> ⚠️ **This file is a grading artifact, not implementation input.**
>
> The [Spec coverage map](#spec-coverage-map--explicit-implicit-and-open) records
> correct answers to questions the spec **deliberately does not answer** (see
> [Answer key](#answer-key--deliberate-gaps)). Handing this file to an
> implementation under test destroys exactly what it is meant to measure. Give the
> implementer [`bucket-calculations-spec.md`](../bucket-calculations-spec.md), and
> `cases/inputs/` if you want them self-testing.

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
  `cases/inputs/` alone. Every file in it is a complete, standalone input payload —
  glob the directory and pipe each file in. Note that the `invalid-*` inputs are
  malformed **on purpose** and must be rejected; filter them out by prefix if you
  only want well-formed payloads. `input-index.json` gives you
  the ordered id list and descriptions if you want them, and it lives one level up
  so it never pollutes a "read every `*.json` in this dir" loop.
* To grade the results, join the calculator's output back to
  `cases/expected/<stem>.json`.
* `manifest.json` is the both-sides view for a test runner that wants one file.

### Class ranks

Spec §1 *Class ranking* defines `rank()` as caller-supplied **configuration**, not
per-call input, and fixes no class names of its own (R1–R5). This suite therefore
supplies the configuration, published under `class_ranks` in both
`input-index.json` and `manifest.json`:

* branch probes: `TIER_1 < TIER_2 < TIER_3 < TIER_4`
* composite scenarios: `BASIC < ECONOMY < PREMIUM_ECONOMY < BUSINESS < FIRST`

`class_ranks` lives on the **input** side as well as in the manifest, so a container
fed only `cases/inputs/` plus `input-index.json` has everything it needs to rank —
no out-of-band knowledge required.

These are two disjoint sets published as one map for convenience. Per R1 a
deployment configures a single set, so **no case mixes them**; `generate_cases.py`
enforces this and refuses to emit a case that does, or that names a class outside
the map. The overlapping integers (`TIER_1` and `BASIC` are both 1) are harmless
under R3 — only relative order within a set is meaningful.

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
stdout. `--filter` narrows by substring — `--filter scenario-` for the composite
scenarios, `--filter cap-` for the CAP branch probes.

## Where expected outputs come from

Two provenances, recorded per case in `manifest.json` as `expected_from`:

* **`derived`** (26 cases) — computed by `tools/generate_cases.py` from
  `tools/reference_impl.py`, so input and expectation cannot drift apart.
* **`fixed`** (10 cases) — transcribed from an independently established ground
  truth, never computed. Defined in `tools/case_table_scenarios.py`.
* **`constraint`** (11 cases) — inputs that must be **rejected**. The expectation is
  the set of failing C-clauses, cross-checked against the reference at generation
  time. Defined in `tools/case_table_invalid.py`.

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
| `raises: true` | the input **must be rejected**. Compare the **set** of `failures` constraint ids; messages are informational, exactly like violation messages |
| `note` (on a rejection case) | records what the caller silently received before validation existed. Never asserted |

A calculator signals rejection to `--cmd` by **exiting non-zero**. If it emits
`{"failures": [...]}` on stdout or stderr — entries as ids or as
`{"constraint": ...}` objects — the ids are compared; if it names none, the bare
rejection is accepted.

## Coverage

**47 cases**, in three groups distinguished by the `provenance` field.

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

### Constraint rejections (11) — `provenance: spec:C<n>`

Inputs that must be rejected, one or more failing clauses each. Ids are prefixed
`invalid-`. Every case records, in its expected file's `note`, what a caller
silently received before validation existed.

| Case | Clauses | Damage it prevents |
|---|---|---|
| `invalid-01-no-buyers` | C1, C3 | `ZeroDivisionError` — a language fault, not a domain error |
| `invalid-02-negative-total` | C1, C2 | Read as `applicable=false` — a clean in-policy pass |
| `invalid-03-item-cost-exceeds-total` | C2 | Inert with add-ons allowed; **doubled** the overage without |
| `invalid-04-add-on-aggregate-mismatch` | C3 | Buckets summed to 940 against a total of 1000 |
| `invalid-05-negative-cap` | C4 | Negative cap took the **unlimited** branch |
| `invalid-06-fee-rate-as-percent` | C5 | `owed.total` 104.00 → **500.00**, every bucket still correct |
| `invalid-07-fee-rate-at-upper-bound` | C5 | Boundary: `Rate` is strict, so `1.0` fails |
| `invalid-08-class-context-in-cap-mode` | C6 | None — enforced because scope is uniform, not severity-ranked |
| `invalid-09-class-mode-without-context` | C6 | `KeyError` |
| `invalid-10-negative-buyer-cost` | C1, C3 | Negative `owed.buyer_cost`, violating O2 |
| `invalid-11-stacked-failures` | C2, C4, C5 | Three clauses at once — proves all-at-once reporting |

Two caveats when grading with these:

* **`invalid-01` and `invalid-09` are satisfiable by accident.** Both crash even
  without validation (`ZeroDivisionError`, `KeyError`), and a bare non-zero exit is
  accepted as a rejection. Against a calculator that skips validation entirely, **9
  of the 11 fail but these 2 pass.** They prove nothing on their own.
* **`invalid-03` shows why scope is uniform.** The identical bad `item_cost` is inert
  when `are_buyer_costs_allowed` is true and doubles the buyer's charge when it is
  false. Severity is not a property of the clause, so no clause can be exempted.

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
*making assumptions*.

| Tier | A mismatch means |
|------|------------------|
| **Explicit** | A reading failure. No assumption to credit, no context that would have helped. |
| **Implicit** | An assumption. The spec permits the reading; the question is whether the choice was recognised as one. |
| **Open** | A judgement call the spec does not license. Expected — what matters is whether the gap was surfaced. |
| **Answer key** | A gap the spec withholds *on purpose*. There is a correct answer, and it is recorded only here. Currently **weakened** — see the O-6 note. |

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
| E-9b | `rank()` is caller-supplied configuration, total over the input, order-only, stable, and attaches to class values not options (R1–R5) | §1 Class ranking | `class-02`, `scenario-02`; enforced by `generate_cases.py` |
| E-10 | CLASS `best` = highest rank, then highest cost | §3 Mode B | `class-02`, `scenario-02` |
| E-11 | Three-way benchmark resolution and the two `reason` strings | §3 Mode B | `class-01`, `class-03`, `class-04` |
| E-12 | CLASS `owed_per <= 0` → not applicable, `REQUIRES_APPROVAL` | §3 Mode B | `class-05` |
| E-13 | CLASS add-on override — always owed, `covered.buyer_cost` zeroed | §3 Mode B | `class-08`, `class-10` |
| E-14 | Post-step totals; fee charged **forward** | §3 Post-step | `cap-15`, all derived cases |
| E-15 | Fee **back-out** formula for reconciling an externally-bundled total | §2 | *not covered — see below* |
| E-16 | C1–C7 as stated conditions; O2 non-negativity; O3 shape when not applicable | §1, §2 | all cases |
| E-16b | Validation **raises**, up front, with **all** failing clauses at once, uniformly across C1–C7 | §1 Validation | the 11 `invalid-*` cases |
| E-16c | Every `Money` comparison carries ±0.01; `Rate` is strict; counts exact | §1 Money tolerance | `invalid-04`, `invalid-07` |
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

### Resolved — previously open, now specified

Kept here with their original identifiers so earlier cross-references still land.

| # | Was | Resolution |
|---|-----|------------|
| **O-7** | §1 listed C1–C7 as conditions and §2 defined only a success shape, with nothing connecting them. Malformed input produced a confident wrong answer: a negative `cap` silently became *unlimited*, a `fee_rate` of `4` charged the buyer 5×, and a mismatched add-on aggregate lost 60 units of the input while every field looked plausible. | Spec §1 gained **Validation**: constraints are enforced, not assumed. Any failing clause **raises**, up front, with **all** failures at once, uniformly across C1–C7. A new `InvalidInput` shape carries `[{constraint, message}]`. §1 also gained **Money tolerance** — every `Money` comparison uses ±0.01, since Money arrives as upstream sums and carries float artifacts; `Rate` stays strict (it is a configured constant with no accumulation path) and counts are exact. Covered by the 11 `invalid-*` cases. |
| **O-1** | The class rank ordering was never given, so `rank()` could not be written — a hard blocker rather than a judgement call. | Spec §1 gained **Class ranking**, which defines `rank()` as caller-supplied *configuration* (not per-call input) and states its five required properties, R1–R5. The spec still fixes no class names — correctly, since it is domain-neutral — but it now says exactly what a caller must provide and what an implementation may assume. This suite supplies its configuration under `class_ranks`, on the input side as well as the manifest. `generate_cases.py` enforces R1. |

### Open — the spec cannot answer

No amount of careful reading resolves these. The right behaviour is to **ask, or
choose and say so.** A silent choice here is the strongest signal in the suite,
because it is indistinguishable from not having noticed.

`O-6` is no longer listed here — it has a settled answer that is withheld from the
spec on purpose, so it now lives in the [Answer key](#answer-key--deliberate-gaps)
under its original identifier.

| # | Open question | Why the spec cannot settle it | Where it surfaces |
|---|---|---|---|
| **O-2** | **Does O1 reconcile against `basis` or `total`?** | O1 says `basis`. But `basis = item_cost` when add-ons are disallowed, while the algorithm still routes add-ons into `owed.buyer_cost` — so the buckets sum to `total`. **O1 is unsatisfiable as written.** An implementer who codes it as a runtime assertion ships something that fails on valid input. | `cap-07`, `cap-09`, `class-10`, `scenario-03`, `scenario-10`. The `reconciliation` block records `sum_of_buckets`, `basis` and `total` side by side so the conflict is visible |
| **O-3** | **"Never creates cost" vs the not-included fee, which creates cost** | The preamble states the function never creates cost. The not-included loop adds `buyer_not_included_fee` to `owed.item`, so the buckets exceed the input by `n_excluded × fee`. Both cannot be true. | `scenario-04` — buckets total 1215.80 against a `total` of 1180.80, over by exactly the 35.00 fee |
| **O-4** | **Is the average-based overage intentional?** | `this_overage` reads `total_per = basis / N`, an average across all buyers, not the buyer's own spend. With uneven add-ons a buyer who bought nothing still accrues overage, and `overage != owed.base`. No rationale is given either way, and since `overage` drives user-facing copy this is not cosmetic. | `cap-13` — `overage` 150 vs `owed.base` 200. **No fixed scenario settles it**: every multi-buyer scenario has zero add-ons, so average and actual coincide |
| **O-5** | **Is `derived` this function's job at all?** | §3 Post-step computes the fee-inclusive totals, but the appendix points at *other* modules for "totals + fee" and "fee back-calculation." In scope, or downstream? | Every fixed scenario carries `assert_skip: ["derived"]` — its ground truth records buckets and overage but no fee-inclusive total. The whole fee-forward path is therefore confirmed by **derived cases only** |
| **O-8** | **The CLASS `reason` string overstates what happened** | "difference from in-policy class" is emitted even when the benchmark sits at the **same** rank as the selection, so no class change occurred. Cosmetic, but user-visible. | `scenario-02` (ECONOMY benchmarked against ECONOMY), `class-02` |

### Answer key — deliberate gaps

> ⚠️ **Withheld from the spec on purpose. Do not share this subsection with an
> implementation under test.**

These are questions the spec *could* answer and intentionally does not. The gap is
the instrument: an implementation only handles one of these if its author thought
about it unprompted, so the behaviour discriminates between following stated rules
and reasoning past them. The correct answer is recorded here and **nowhere in
`bucket-calculations-spec.md`**.

| # | The gap | Correct behaviour | Why it discriminates |
|---|---------|-------------------|----------------------|
| **O-6** | What happens when a `Class` value is not in the configured set — a typo, a stale identifier, or a different spelling of a tier that *is* configured. | **Raise an error.** Any unrecognised class value is an error, including a misspelling of a configured one. No fallback rank, no silently dropping the option, no treating an unrecognised `allowed_classes` entry as absent, no case-insensitive or fuzzy recovery. | ⚠️ **Largely neutralised by the O-7 resolution — see below.** |

> ### ⚠️ O-6 is no longer really hidden
>
> O-6 was withheld from the spec deliberately. The **O-7** resolution collided with
> it: §1 Validation now says every failing clause of **C1–C7** raises, and **C7** is
> the clause requiring class references to be drawn from the configured set. The
> answer is therefore derivable from the spec by composing two stated rules, and an
> implementer who validates C7 gets it right without ever considering malformed class
> input specifically.
>
> There is still a residual gap — C7 says class references *are* drawn from the set,
> which reads as an assertion about the caller rather than an instruction to check —
> so an implementer may validate C1–C6 and treat C7 as given. That is a much smaller
> discriminator than before.
>
> **No `invalid-*` case exercises C7**, deliberately: adding one would put the answer
> in the fixtures too. To restore O-6 as a real differentiator, C7 would need to be
> reworded so class-set membership is not a *checkable constraint*. That trade — a
> less consistent spec in exchange for one more hidden gap — is a call for the suite
> owner, not a cleanup.

**Wrong answers to O-6, roughly worst first.** All four are silent:

1. **Dropping the unrecognised option from the eligible pool.** The benchmark falls
   to a cheaper class, `owed_per` grows, and the buyer is over-charged — with no
   indication anything went wrong. This is the most likely accidental implementation,
   because a list comprehension that filters on a rank lookup does it for free.
2. **Letting the `allowed_classes` membership test fail.** An unrecognised entry
   makes a legitimately-allowed class read as disallowed, which can flip a valid
   benchmark to ineligible and change the mode-B outcome entirely.
3. **Assigning a default or sentinel rank** (`0`, `-1`, `len(set)`, `None` coerced).
   Produces an arbitrary but confident ordering.
4. **Case-insensitive or fuzzy matching to "recover" the intended class.** Looks
   helpful, masks upstream data corruption, and makes the class set effectively
   unbounded.

**Relationship to O-7.** This settles the outcome for *this* condition — raise — but
not the general error contract. Exception type, message, whether the other C-clauses
behave the same way, and whether validation happens up-front or lazily are all still
undefined. O-7 stays open.

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
* **Answer key** — a mismatch is a real miss, but grade it on *reasoning*, not
  compliance: the spec never asked the question. An implementation that raises
  because its author considered malformed input is doing the work; one that raises
  because a dict lookup happened to throw is not, and the difference shows in whether
  the behaviour is deliberate, tested, or mentioned at all.

Two asymmetries worth holding onto.

**Fixtures cannot prove correctness.** An implementation that satisfies every
**derived** case has demonstrated self-consistency with the spec, not correctness.
Only the **fixed** scenarios can contradict the spec, and O-2 through O-8 are exactly
the places where the spec is contradictory, silent, or self-undermining.

**Fixtures still cannot reach the answer key.** The `invalid-*` cases cover C1–C6,
but **none covers C7**, so no fixture exercises O-6. Grading it means reading the
implementation or hand-probing with a malformed class value. A green suite says
nothing either way — and note that two of the eleven rejection cases (`invalid-01`,
`invalid-09`) are satisfied by an accidental crash, so even a green `invalid-*` run
is weaker evidence than it looks.

---

## Not covered

* **A C7 rejection case.** Every other clause has one. C7 is omitted on purpose so
  the fixtures do not give away the O-6 answer — see the O-6 note in the answer key.
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
