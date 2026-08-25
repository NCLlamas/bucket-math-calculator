# Bucket Calculations — Specification

A language-agnostic definition of the cost-allocation feature. It takes a single
priced **item** plus a **policy** and splits the cost into two funding **buckets**:

- **`covered`** — the portion the policy funds (within its cap / benchmark).
- **`owed`** — the portion the individual **buyer** must pay (the excess), plus a
  fee on that portion.

It is a **pure allocation function**: no I/O, no persistence, no external calls. The
two buckets reconcile back to the input, with one deliberate exception — the
per-not-included-buyer fee is a genuine surcharge and is added on top. See O1.

---

## Terminology

| Term | Meaning |
|------|---------|
| **item** | The single priced thing being bought (one per calculation). |
| **item_cost** | Cost of the item's base component only. |
| **buyer_cost** | A per-**buyer** discretionary add-on cost. Named for the fact each buyer selects their own. This is a *cost dimension*, not a payer. |
| **total** | `item_cost` + all add-ons (buyer_costs + any other ancillary). `total ≥ item_cost`, `total ≥ Σ buyer_cost`. |
| **buyer** | One individual in the group. Every buyer is either *included* or *not included* by the policy. |
| **cap** | Per-buyer spend ceiling the policy funds. `0` is the sentinel for "no cap": the cap rule is **disabled**, so no spend is measured against a limit and the `CAP` violation cannot fire. It does **not** disable the policy's other rules. |
| **class** | A discrete tier of the item (e.g. a quality/service level). Classes are **ranked**; higher rank = higher tier. The set and its order are caller-supplied, not fixed by this spec. |
| **covered** | Output bucket: money the policy funds. |
| **owed** | Output bucket: money the buyer funds. |

---

## Types

| Type | Definition |
|------|------------|
| `Money` | Non-negative fixed-point decimal (2 dp). *(Current implementation uses float; a Decimal with explicit remainder handling is the hardening target.)* |
| `Rate` | Decimal in `[0, 1)`. |
| `Id` | Opaque identifier. |
| `Class` | Member of a ranked, finite set supplied by the caller. See [Class ranking](#class-ranking-external--supplied-by-the-caller). |

---

## 1. Input Structure

```
BucketCalculationInput
├── mode: "CAP" | "CLASS"
│
├── item:
│   ├── total:      Money
│   ├── item_cost:  Money
│   └── buyer_cost: Money        # aggregate add-on cost across all buyers
│
├── buyers: [ Buyer ]            # len ≥ 1
│   └── Buyer
│       ├── id:            Id
│       ├── not_included:  bool  # true ⇒ beyond the policy's included count
│       └── buyer_cost:    Money # this buyer's add-on cost
│
├── policy:
│   ├── cap:                    Money   # PER-BUYER; 0 == no cap (infinite — anything allowed)
│   ├── are_buyer_costs_allowed: bool
│   ├── buyer_not_included_fee: Money   # surcharge per not-included buyer
│   ├── included_buyer_count:   int ≥ 0
│   └── allowed_classes:        [Class] # empty == all classes allowed
│
├── upgrade_context:            # required iff mode == "CLASS"
│   ├── selected_class:   Class
│   └── alternate_classes: [ ClassOption { class: Class, cost: Money } ]  # cost is aggregate across buyers
│
└── fee_rate: Rate             # default 0.04; 0 ≤ rate < 1
```

### Constraints (must hold for a valid calculation)

| # | Invariant |
|---|-----------|
| C1 | All `Money` ≥ 0; all counts ≥ 0; `len(buyers) ≥ 1`. |
| C2 | `item_cost ≤ total` and `buyer_cost ≤ total`. |
| C3 | `Σ buyer.buyer_cost == item.buyer_cost`. |
| C4 | `cap ≥ 0`; `cap == 0` means "no cap" — the cap comparison is disabled. It does not make every spend in-policy; other policy rules still apply. |
| C4b | `allowed_classes` empty means "all classes allowed". |
| C5 | `0 ≤ fee_rate < 1`. |
| C6 | `upgrade_context` present **iff** `mode == "CLASS"`. |
| C7 | Every `alternate_classes[*].class`, `selected_class`, and member of `allowed_classes` is drawn from the configured class set and is therefore rankable (see [Class ranking](#class-ranking-external--supplied-by-the-caller)). |

`C4b` is a definition rather than a testable condition; every other clause is checked.

### Money tolerance

Every `Money` comparison — in the constraints above, in the output invariants, and
in reconciliation — uses an absolute tolerance of **±0.01**, one minor unit. `Money`
values normally arrive as sums of upstream components and carry accumulated
floating-point artifacts, so exact comparison produces spurious failures: an
`item_cost` of `800.0000000001` is not a violation of C2.

`Rate` is compared **exactly**. `fee_rate` is a configured constant with no
accumulation path, so `0 ≤ fee_rate < 1` is strict — `1.0` fails, `0.9999` passes.

Counts (`included_buyer_count`, `len(buyers)`) are integers and are compared exactly.

### Validation

The constraints are **enforced, not assumed.** Before any allocation work begins,
every checkable clause is evaluated. If any fails, the calculation **raises** and
returns no allocation.

```
InvalidInput
└── failures: [ ConstraintFailure { constraint: "C1".."C7", message: string } ]
```

| Rule | |
|------|--|
| **Mechanism** | Raise. Not a return value — `applicable: false` already means *"valid input, nothing to split"*, and the `violations` list carries end-user policy outcomes. Neither channel can express "the caller sent something malformed" without becoming ambiguous. |
| **Timing** | Up front, before any bucket is computed. A partially-computed allocation is never returned or observable. |
| **Granularity** | **All** failing clauses in one raise, not the first. A caller repairing a payload should see the whole list. |
| **Scope** | Uniform across every checkable clause. Severity is not a property of the clause — a bad `item_cost` is inert when `are_buyer_costs_allowed` is true and doubles the buyer's charge when it is false — so no clause can be safely exempted. |
| **Message** | Informational. `constraint` is the contract; wording is not specified. |

Validation failure is distinct from every success-shaped output. In particular it is
**not** `applicable: false`: a negative `total` and a negative `cap` both otherwise
sail through the algorithm and return `applicable: false, allocation: null`, which is
indistinguishable from a clean in-policy pass.

### Preconditions (external — outside this function)

- The feature is only invoked when bucketing is enabled for the context
  (e.g. the account is eligible). This function assumes it should run.

### Class ranking (external — supplied by the caller)

`CLASS` mode compares tiers, so it needs an ordering over `Class`. **This spec fixes
no class names and no ordering.** The class set is a property of the deployment — its
tiers, its vocabulary — so it is *configuration*, supplied once when the calculation
is constructed, not data passed per call.

An implementation must therefore be given:

```
rank(class) -> integer      # or any equivalent total ordering over the class set
```

Required properties:

| # | Property |
|---|----------|
| R1 | **Total over the configured set.** `rank()` is defined for every member of that set, and comparing two members never returns "unknown". |
| R2 | **Higher rank = higher tier.** `rank(a) < rank(b)` means `a` is the lower tier. |
| R3 | **Only the relative order is meaningful.** Absolute values carry no information; any order-preserving relabelling is equivalent. Ranks are never compared to `Money`, summed, or used in arithmetic. |
| R4 | **Stable within a calculation.** `rank()` returns the same answer for the same class throughout a single call. |
| R5 | **Ranks attach to class values, not to options.** Several `alternate_classes` entries may share a class — including the selected one. That is legal and is exactly why the tiebreak in Mode B is *"highest rank, then highest cost"*. |

Because `rank()` is a lookup, `Class` values must be comparable by equality: one
canonical spelling per tier, used consistently across `selected_class`,
`alternate_classes[*].class`, and `allowed_classes`. The caller chooses the form.

> **Worked example.** A deployment with four tiers might configure
> `{BRONZE: 1, SILVER: 2, GOLD: 3, PLATINUM: 4}`. `{BRONZE: 10, SILVER: 20, GOLD: 30,
> PLATINUM: 40}` is the same configuration by R3. A `selected_class` of `GOLD` makes
> `BRONZE`, `SILVER` and `GOLD` options eligible benchmarks and excludes `PLATINUM`,
> subject to the other two clauses of `eligible()`.

---

## 2. Output Structure

```
BucketCalculationOutput
├── applicable: bool            # false ⇒ no real split; allocation is null
│
├── allocation:                 # all Money ≥ 0
│   ├── covered.item:       Money
│   ├── covered.buyer_cost: Money
│   ├── owed.item:          Money
│   ├── owed.buyer_cost:    Money
│   ├── covered_buyer_count: int    # buyers the policy funds
│   └── fee_rate:           Rate
│
├── derived:                    # pure functions of allocation
│   ├── covered.total = round(covered.item + covered.buyer_cost, 2)
│   ├── owed.base     = owed.item + owed.buyer_cost
│   ├── owed.fee      = owed.base * fee_rate
│   └── owed.total    = round(owed.base + owed.fee, 2)
│
├── overage: Money              # total the buyer owes beyond policy (drives UX + violations)
│
└── violations: [ Violation { code, status, message } ]
```

### Violation codes

| Code | Status | Emitted when |
|------|--------|--------------|
| `CAP` | `REQUIRES_USER_CHOICE` | `overage > 0` **and** `cap > 0` |
| `NOT_INCLUDED` | `REQUIRES_USER_CHOICE` | `excluded_cost > 0` |
| `BUYER_COST_NOT_ALLOWED` | `REQUIRES_APPROVAL` | `are_buyer_costs_allowed == false` **and** `item.buyer_cost > 0` |
| `CLASS` | `REQUIRES_SPLIT_PAY` | CLASS mode resolved a benchmark and `owed_per > 0` |
| `CLASS` | `REQUIRES_APPROVAL` | CLASS mode found no benchmark, or `owed_per <= 0` |

`BUYER_COST_NOT_ALLOWED` is **mode-independent** and is emitted even when
`applicable == false`. A non-null `violations` list alongside a null `allocation`
is a valid, expected output.

### Invariants (must hold on every non-null allocation)

| # | Invariant |
|---|-----------|
| O1 | **Reconciliation:** `covered.item + owed.item + covered.buyer_cost + owed.buyer_cost == total + (n_excluded × buyer_not_included_fee)` (± 0.01), where `n_excluded = len(excluded)`. The target is **`total`** — the buckets always partition the whole input. `overage_basis` is never a reconciliation target. |
| O2 | No bucket field is negative. |
| O3 | `applicable == false` ⇒ `allocation == null` and `overage == 0`. Says nothing about `violations`, which may be non-empty. |

### Fee direction (important)

The fee is **added forward** when charging the buyer (`owed.total` above).
When *reconciling an external total that already bundles the fee*, back it out
instead — same rate, opposite direction:

```
fee_component = external_total * fee_rate / (1 + fee_rate)
```

---

## 3. Abstracted Logic

### Preamble (both modes)

```
N             = len(buyers)
item_per      = (total - buyer_cost) / N         # per-buyer base cost, add-ons excluded
overage_basis = total if are_buyer_costs_allowed else item_cost
total_per     = overage_basis / N                # per-buyer yardstick — OVERAGE ONLY
cap           = policy.cap
included      = [b for b in buyers if not b.not_included]
excluded      = [b for b in buyers if b.not_included]

covered.item = covered.buyer_cost = owed.item = owed.buyer_cost = 0
overage = 0

# Standing violation — a policy fact, independent of mode and of any allocation.
# Emitted on EVERY return path, including the not-applicable ones.
violations = []
if not are_buyer_costs_allowed and item.buyer_cost > 0:
    violations += { BUYER_COST_NOT_ALLOWED, REQUIRES_APPROVAL,
                    "<buyer_cost> add-on cost not allowed by policy" }
```

> **`overage_basis` selects the yardstick, not the allocation.** It decides which
> figure the cap is measured against when computing `overage` — nothing more. It
> never determines what lands in a bucket, and it is never a reconciliation target.
> The buckets are always built from `item_per`, `cap` and the per-buyer add-on, which
> together partition `total`. Reading it as "the base of the allocation" is the
> single easiest way to get O1 wrong.

---

### Mode A — `CAP`

**For each included buyer** (add-on `bc = buyer.buyer_cost`):

```
if cap > 0:                                    # cap == 0 ⇒ cap rule disabled; see the else branch
    if item_per > cap:                         # base alone exceeds cap
        covered.item      += cap
        owed.item         += item_per - cap
        owed.buyer_cost   += bc                 # buyer pays all add-ons
    else:                                       # base within cap
        covered.item      += item_per
        if are_buyer_costs_allowed:
            room = cap - item_per               # leftover cap room
            covered.buyer_cost += min(bc, room)
            owed.buyer_cost    += max(bc - room, 0)
        else:
            owed.buyer_cost    += bc

    this_overage = max(total_per - cap, 0)                if are_buyer_costs_allowed
                 = max(item_per - cap, 0) + bc            otherwise
    overage += round(this_overage, 2)

else:                                           # cap == 0 ⇒ the CAP comparison is disabled
    covered.item += item_per                    # no cap to exceed, so the base is funded
    if are_buyer_costs_allowed:
        covered.buyer_cost += bc
    else:
        owed.buyer_cost += bc
        overage         += bc               # disallowed add-on — an overage in its own right
```

> **`cap == 0` disables the cap comparison, not overage generation.** The sentinel
> makes the *cap rule* unenforceable: no spend is measured against a limit, so
> `max(... - cap, 0)` contributes nothing and the `CAP` violation cannot fire
> (it is gated on `cap > 0`). It does **not** switch off the other policy rules. An
> add-on the policy disallows is out of policy on its own terms, independent of any
> cap, so it still lands in `overage` — and still raises
> `BUYER_COST_NOT_ALLOWED`.
>
> The result is a state worth noting: `applicable == true` with a positive `overage`
> and **no `CAP` violation**, because the overage came from a different rule.

**For each not-included buyer** (add-on `bc`): buyer pays fully + the fee.

```
owed.item        += item_per + buyer_not_included_fee
owed.buyer_cost  += bc
excluded_cost    += item_per + buyer_not_included_fee + bc
```

**Finalize (order matters):**

```
if overage <= 0 and excluded_cost <= 0:         # nothing over policy → not a split
    applicable = false ; allocation = null

if overage > 0 and cap > 0:
    emit violation { CAP, REQUIRES_USER_CHOICE, "<overage> over limit" }
if excluded_cost > 0:
    emit violation { NOT_INCLUDED, REQUIRES_USER_CHOICE, "<n> not-included buyer(s)" }

overage += excluded_cost                         # excluded cost folded in last
```

---

### Mode B — `CLASS`

```
item_per = (total - buyer_cost) / N

# Choose a benchmark class cost to compare the selected class against.
eligible(opt) = rank(opt.class) ≤ rank(selected_class)
                AND (allowed_classes is empty OR opt.class ∈ allowed_classes)
                AND (cap == 0 OR opt.cost / N < cap)         # cap == 0 ⇒ infinite (always passes)

best = among eligible alternate_classes, the one with highest (rank, then cost)
       → best_per = best.cost / N   (or none)

resolve benchmark_per:
    best exists          → benchmark_per = best_per     reason = "difference from in-policy class"
    else cap > 0         → benchmark_per = cap          reason = "over cap"
    else (no best, cap 0)→ RETURN not applicable        violation { CLASS, REQUIRES_APPROVAL }

owed_per = item_per - benchmark_per
if owed_per <= 0: RETURN not applicable                 violation { CLASS, REQUIRES_APPROVAL }

for each included buyer (add-on bc):
    covered.item       += benchmark_per
    covered.buyer_cost += bc
    owed.item          += owed_per

for each not-included buyer (add-on bc):
    owed.item          += item_per + buyer_not_included_fee
    owed.buyer_cost    += bc

# In CLASS mode, add-ons are ALWAYS the buyer's cost — override any accumulation above.
if buyer_cost > 0:
    owed.buyer_cost    = buyer_cost
    covered.buyer_cost = 0

overage = round(owed.item, 2)
emit violation { CLASS, REQUIRES_SPLIT_PAY, "<owed.item> <reason>" }
```

---

### Post-step (mode-independent) — totals & fee

```
covered.total = round(covered.item + covered.buyer_cost, 2)
owed.base     = owed.item + owed.buyer_cost
owed.total    = round(owed.base * (1 + fee_rate), 2)   # fee charged forward
```

---

## 4. In one sentence

> Fill the policy's per-buyer **cap** room first (base cost, then add-ons where
> allowed), route every unit above the cap — plus the full cost and a fee for any
> **not-included** buyer — into the **owed** bucket, surcharge the owed bucket by
> `fee_rate`, and guarantee `covered + owed` reconciles to the input; **CLASS**
> mode differs only in that the cap is replaced by the best in-policy class
> **benchmark** and add-ons always fall to the buyer.

