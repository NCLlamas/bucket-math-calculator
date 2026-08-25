# Bucket Calculation — Validation Cases

Input/output fixtures for validating an implementation of
[`bucket-calculations-spec.md`](../bucket-calculations-spec.md).

## Layout

```
cases/
├── inputs/<case-id>.json     bare BucketCalculationInput — nothing else in the file
├── expected/<case-id>.json   expected BucketCalculationOutput for the same id
├── input-index.json          input side only: ordered ids + metadata + class ranks
└── manifest.json             linked view: id → input path, expected path, tags
```

**Inputs and expectations are joined by filename stem only.** Neither file
contains a pointer to the other, and neither carries a `case_id` field. So:

* To exercise a calculator with no expectations at hand, mount or copy
  `cases/inputs/` alone. Every file in it is a valid, complete, standalone input
  payload — glob the directory and pipe each file in. `input-index.json` gives
  you the ordered id list and descriptions if you want them, and it lives one
  level up so it never pollutes a "read every `*.json` in this dir" loop.
* To grade the results, join the calculator's output back to
  `cases/expected/<stem>.json`.
* `manifest.json` is the both-sides view for a test runner that wants one file.

### Class ranks

`Class` is a ranked set that the spec deliberately leaves outside the input
payload. This suite uses one universe covering both case groups:

* spec-derived cases: `TIER_1 < TIER_2 < TIER_3 < TIER_4`
* production cases: `BASIC < ECONOMY < PREMIUM_ECONOMY < BUSINESS < FIRST`

The authoritative map is published in both `input-index.json` and `manifest.json`
under `class_ranks`. See finding G6 on canonical form.

## Running

```bash
python3 tools/validate_cases.py
```

Self-checks the fixtures against `tools/reference_impl.py`, a literal
transcription of spec §3. Currently **36/36 passed** — every production case
reconciles with the spec exactly, following the G1–G3 resolutions below. Any
`FAIL` or `xfail` is a real regression.

```bash
python3 tools/validate_cases.py --cmd "docker run --rm -i bucket-calc"
```

Grades any command that reads one input JSON on stdin and writes one output
JSON on stdout. `--filter` narrows to a subset by substring — `--filter prod-` for
the production cases only, `--filter cap-` for the spec-derived CAP branches.

## Where expected outputs come from

Two provenances, both recorded per case in `manifest.json` as `expected_from`:

* **`spec reference`** (26 cases) — derived by `tools/generate_cases.py` from
  `tools/reference_impl.py`, so input and expectation cannot drift.
* **`production (ENG-1035)`** (10 cases) — transcribed from the ticket, never
  derived. The generator additionally runs the reference implementation over the
  same input and writes any difference into a `divergence_from_spec` block on the
  expected file. **Production is authoritative where they disagree.**

All 10 production cases now reconcile with the spec reference exactly, to the cent,
across all four buckets. Before the G1–G3 resolutions, 3 of them did not — that gap
is what drove the spec changes.

## Comparison rules

| Field | Rule |
|-------|------|
| Money | ±0.01 tolerance, never exact equality |
| `violations` | compare as a **set of `(code, status)`**; `message` wording is unspecified, so it is informational only |
| `applicable == false` | assert `allocation == null` **and** `overage == 0` (O3) |
| `reconciliation` | diagnostic block added by the generator — **not** part of the output contract |
| `assert_skip` | field names to skip. Production cases carry `["derived"]` because prod records no fee-inclusive totals (G5) |
| `divergence_from_spec` / `source` | provenance metadata, never asserted |

## Coverage

**36 cases.** Two groups, distinguished by the `provenance` field on every case:

### Spec-derived (26) — `provenance: spec:<section>`

Branch coverage of spec §3: 16 CAP, 10 CLASS. Every branch is hit, plus these
boundaries: `item_per == cap` exactly, `bc == room` exactly, `owed_per == 0`,
`fee_rate == 0`, `len(buyers) == 1`, the `cap == 0` sentinel on both add-on paths,
and a total that does not divide evenly across buyers.

### Production (10) — `provenance: ENG-1035:<n>`

Real Quest Prod checkouts from Linear ENG-1035, translated into the generic model.
Core 01–05 cover the common scenarios; Complex 06–11 cover the harder branches.

| Case | Mode | What it pins down |
|---|---|---|
| `prod-01-in-policy-no-violations` | CAP | Clean in-policy pass, no split |
| `prod-02-class-upgrade-split-pay` | CLASS | Benchmark is a cheaper fare in the **same** class |
| `prod-04-add-ons-not-allowed-no-cap` | CAP | Uncovered add-ons under an unlimited cap — drove **G2** and **G3** |
| `prod-05-not-included-buyer-split-pay` | CAP | Not-included buyer pays fare + fee |
| `prod-06-class-upgrade-requires-approval` | CLASS | No benchmark, no cap → approval (**G4** still open) |
| `prod-07-over-cap-split-pay` | CAP | Fare over cap → company covers cap, buyer covers excess |
| `prod-08-long-haul-cap-tier` | CAP | Resolved cap 1500 from the long tier |
| `prod-09-add-ons-allowed-partial-cap-room` | CAP | All four buckets non-trivial at once |
| `prod-10-covered-guests-multi-buyer` | CAP | Both buyers inside the covered count |
| `prod-11-stacked-add-ons-and-over-cap` | CAP | Two violations, overage sums both |

`prod-09` is the highest-value fixture in the suite: it is the only case where all
four buckets carry distinct non-trivial values (`covered.item` 687.52,
`covered.buyer_cost` 12.48, `owed.item` 0, `owed.buyer_cost` 172.40), and the spec
reference reproduces every one exactly. Any error in the `min`/`max` cap-room
arithmetic fails here.

Tags in `manifest.json` mark the interesting groups: `boundary`, `edge`,
`not-applicable`, `no-violations`, `reconciliation-defect`, `fee-creates-cost`,
`average-overage`, `violation-asymmetry`, `violation-without-allocation`,
`two-violations`, `no-prod-coverage`, `prod`, `core`, `complex`, and `four-buckets`.

### Two things production could not pin down

The spec's `mode` maps onto prod's `split_pay_required`, which the README notes is
**a manual per-case override** — in prod it comes from a `REQUIRES_SPLIT_PAY`
violation set at *fare selection*, not re-stored on the checkout intent. So CLASS
mode is only exercised by 2 of the 10 cases (02, 06), and both are single-buyer
with no add-ons. CLASS mode with multiple buyers, with add-ons, or with a
not-included buyer has **no production coverage** — F3, F4 and the CLASS half of G2
stay unverified against real data.

## Findings

Production settled some of the open spec questions and opened new ones. Every
finding below is anchored to a case you can run.

### Settled by production evidence

**F1 — Reconcile against `total`, not `basis`. RESOLVED.**
*Cases: `prod-04`, `prod-09`, `prod-11`, `cap-07`, `cap-09`, `class-10`*

Invariant O1 says the buckets sum to `basis`, and the preamble sets
`basis = item_cost` when `are_buyer_costs_allowed == false`. That is unsatisfiable:
the algorithm still routes add-ons into `owed.buyer_cost`, so the buckets sum to
`total`. Production agrees with `total` every time — `prod-11` splits
`700 + 117.38 + 22.56 = 839.94`, exactly `total`, while `basis` would be 817.38.
**Fix O1 to reconcile against `total` unconditionally** and keep `basis` only for
the `total_per` overage term where it is actually used.

**F2 — The not-included fee genuinely creates cost. INTENTIONAL.**
*Case: `prod-05`*

The preamble claims the function "never creates cost," but the not-included loop
adds `buyer_not_included_fee` to `owed.item`. Production does exactly the same:
`prod-05` splits `590.40 + 625.40 = 1215.80` against a `total` of 1180.80 — over by
precisely the 35.00 ticketing fee. So this is correct behaviour and the *invariant*
is what's wrong. **Restate O1 as `Σ buckets == total + (n_excluded × buyer_not_included_fee)`.**

### Resolved — gaps production exposed, now closed

All three changed `bucket-calculations-spec.md`, `tools/reference_impl.py`, or both.

**G1 — Split-pay availability. RESOLVED by narrowing scope.**

Production ran `prod-03` (over cap, split pay **off**) and `prod-07` (over cap,
split pay **on**) through the same branch and got different answers: 03 produced no
buckets at all and `REQUIRES_APPROVAL`, 07 produced a real split and
`REQUIRES_USER_CHOICE`. The generic input has no `is_split_pay_available` field, so
the spec could not express 03.

**Ruling: the system now assumes split pay is always available**, so that scenario
cannot arise. `prod-03` is dropped from the suite — it was the only fixture whose
expected output encoded the unavailable behaviour, and `prod-07` covers the same
over-cap branch. No input field was added.

Consequences to be aware of:

* `CAP` is now unconditionally `REQUIRES_USER_CHOICE`. `REQUIRES_APPROVAL` on a CAP
  violation has no remaining path and no fixture.
* Cases `prod-01`, `prod-04` and `prod-10` also ran with `split_pay_available=false`
  in production, but their outcomes do not depend on the flag — 01 and 10 have no
  overage at all — so they are kept.
* If split pay ever becomes conditional again, this is a spec change and not just a
  new fixture: `applicable` is currently doing double duty for "is there overage"
  and "can we split it," which `prod-03` showed are distinct.

**G2 — `BUYER_COST_NOT_ALLOWED` added.** *Cases: `prod-04`, `prod-11`, `cap-07`, `cap-09`, `class-10`*

Production emits `BUDGET_SEAT_COVERAGE` whenever the policy disallows add-ons and
the buyer bought some. The spec had no equivalent, so it emitted nothing for
`prod-04` and only the CAP violation for `prod-11`.

Added to §2 as:

| Code | Status | Emitted when |
|------|--------|--------------|
| `BUYER_COST_NOT_ALLOWED` | `REQUIRES_APPROVAL` | `are_buyer_costs_allowed == false` **and** `item.buyer_cost > 0` |

It is a **standing violation**: computed in the preamble, mode-independent, and
carried onto *every* return path including the not-applicable ones. `REQUIRES_APPROVAL`
is taken straight from production, which uses that status in both `prod-04`
(split pay off) and `prod-11` (split pay on) — so it does not vary with split pay.

This also resolves the oddity flagged two passes ago: `cap-09` was applicable with an
empty violations list. That was never a curiosity — it was this missing code.

Three spec-derived cases gained the violation as a result: `cap-07` and `class-10`
now emit two violations each, and `cap-09` emits one.

> **Note on scope.** Emitting it in CLASS mode is a judgement call, not a
> production-backed fact. In CLASS mode add-ons always fall to the buyer anyway, so
> `are_buyer_costs_allowed` is redundant there — but the policy fact is still true,
> so the standing violation fires. No production case combines CLASS mode with
> disallowed add-ons; `class-10` is the only coverage and it is spec-derived. Tagged
> `no-prod-coverage`.

**G3 — `cap == 0` no longer contributes to overage.** *Cases: `prod-04`, `cap-09`*

Confirmed: the gap was exactly the unlimited-cap reading. Spec §3 Mode A had
`overage += bc` in the `cap == 0` branch, but `cap == 0` means the cap is infinite —
**no spend can be over a limit that does not exist.** Production agrees: `prod-04`
reports `upgrades = 0.0` for precisely this configuration, and reports the uncovered
107.32 as a *violation* instead.

The line is removed. The buyer still owes the add-on (`owed.buyer_cost += bc`); it is
simply not overage. Because `overage` drives the "over limit" figure in the UI, the
old behaviour would have shown a traveler an over-limit amount against no limit.

The knock-on is the interesting part: with overage back to 0 and no excluded cost,
the finalize step returns `applicable = false, allocation = null` — while the G2
violation still fires. That is exactly `prod-04`'s production output, and it makes
**`allocation == null` with a non-empty `violations` list a valid, expected result**.
O3 already permitted this (it constrains `allocation` and `overage`, not `violations`);
the spec now says so explicitly. `cap-09` is the spec-derived twin of this shape.

Production also writes `price_cap: null` rather than `0` on the summary in this
configuration. The generic output has no `price_cap` echo field, so nothing to change
here — noted in case one is added later.

### Still open

Not part of the G1–G3 resolutions; still need a ruling.

**G4 — Output-side flag mutation is unmodelled.** *Case: `prod-06`*

When CLASS mode cannot find a benchmark, production clears the split summary **and
sets `split_pay_available = false` on the response**. The generic output has no field
for this, so a caller cannot learn that split pay was switched off. Note this sits
oddly beside the G1 ruling: if split pay is always available, it is worth confirming
whether this mutation still happens at all. `prod-06`'s expected output currently
asserts only the allocation and violation, not the flag.

**G5 — `fee_rate` has zero production coverage.**

None of the ENG-1035 cases records a fee or a fee-inclusive total;
`payment_summary_flight` has no such field. Per the spec appendix the 4% is applied
downstream (`booking_intent/flight/model.py`, `invoice_split_pay_helper.py`). The
production fixtures therefore carry `assert_skip: ["derived"]` — the whole `derived`
block, and with it the entire fee-forward path in §"Post-step", is verified **only**
by the spec-derived cases. If the fee belongs to this function, it needs its own
production sample.

**G6 — `Class` needs one canonical form.**

Production stores `allowed_cabin_classes` as display strings (`"Premium Economy"`,
`"Business Refundable"`) but keys fare options by snake_case cabin
(`"premium_economy"`). Membership tests silently fail across the two. Folded here to
a single ranked set — `BASIC < ECONOMY < PREMIUM_ECONOMY < BUSINESS < FIRST` — with
refundability dropped, since it is a fare attribute and not a class. The spec should
say which form is canonical.

Related: `prod-02` shows the benchmark can be a cheaper fare **in the same class** as
the selected one (economy 459.80 benchmarking economy 549.81). The spec's
`rank(opt) <= rank(selected)` permits this, but §3's `reason` string — "difference
from in-policy class" — describes a class change that did not happen.

**F3 — Overage uses the group average, not the buyer's own spend.** *Case: `cap-13`*

`this_overage` reads `total_per = basis / N`, an average, so with uneven add-ons a
buyer who bought nothing still accrues overage and `overage != owed.base`
(`cap-13`: 150 vs 200). **No production case can settle this** — every multi-buyer
prod case (`prod-05`, `prod-10`) has zero add-ons, so the average and the actual
coincide. Needs a ruling, or a new prod sample with uneven add-ons across buyers.

**F4 — CLASS mode emits no `NOT_INCLUDED` violation.** *Case: `class-09`*

CAP mode emits it whenever `excluded_cost > 0`; CLASS mode charges those buyers
identically but emits only the CLASS violation. **No production case combines CLASS
mode with a not-included buyer**, so this is unverified. Given `split_pay_required`
is a manual override in the fixtures, a real sample may be hard to source.

### Also worth noting (not defects)

* `cap-14` shows `overage` (99.99) and `owed.item` (100.00) differing by a cent
  because `round()` is applied per-buyer to overage but not to the `owed.item`
  accumulation. Correct per spec; tested so nobody "fixes" it.
* `prod-08` exercises long-haul tier selection, but tier resolution happens
  **upstream** of this function — the generic model just receives the resolved cap
  (1500). The case still guards the arithmetic; it does not guard tier choice.
* `prod-06`'s cap is pinned to the booking-time value (0), not the current policy
  row (500), which was edited after booking. ENG-1035 calls this out as policy
  drift. Any future re-derivation from prod must preserve the pin.

## Not covered

* **Invalid-input cases (C1–C7 violations).** The spec defines the constraints but
  not an error/rejection output shape, so there is nothing to assert against. Once
  that shape exists, these are worth adding:
  `Σ buyer.buyer_cost != item.buyer_cost` (C3), `item_cost > total` (C2),
  `fee_rate == 1` (C5), `upgrade_context` present in CAP mode (C6), empty `buyers` (C1).
* **Fee back-out direction.** Spec §2 defines
  `fee_component = external_total × rate / (1 + rate)` for reconciling an external
  total that already bundles the fee. Separate function, different inputs — needs
  its own fixture set. G5 makes this more urgent, not less.
* **A runnable GDS `revalidate` fixture.** ENG-1035 captures the engine-relevant
  *projection* of each input, not the raw upstream response (none is stored — see
  ENG-37). Capturing matching fixtures is tracked in ENG-1033.
* **Arrival/departure-window violations.** Produced by the *event* policy engine at
  search / fare selection, not by this allocator. Out of scope per ENG-1035.

## Adding more production cases

Append entries to `tools/case_table_prod.py` with `provenance="ENG-1035:<n>"` (or a
new ticket ref) and an `expected_override` holding the **transcribed** production
output. Then:

```bash
python3 tools/generate_cases.py
```

The generator writes the production output as the expectation, runs the spec
reference over the same input, and records any difference as `divergence_from_spec`.
It prints every divergence on stdout — treat each new one as a finding to
adjudicate, never as a fixture to regenerate. **There are currently zero
divergences**, so any output from that step is new information.

Removing a case from a table also deletes its fixture files, so a dropped case
cannot linger as an orphan (this is how `prod-03` was retired).

The domain glossary used for the translation is in the module docstring of
`tools/case_table_prod.py`.
