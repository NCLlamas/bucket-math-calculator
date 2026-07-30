# Bucket Calculations — Specification

A language-agnostic definition of the cost-allocation feature. It takes a single
priced **item** plus a **policy** and splits the cost into two funding **buckets**:

- **`covered`** — the portion the policy funds (within its cap / benchmark).
- **`owed`** — the portion the individual **buyer** must pay (the excess), plus a
  fee on that portion.

It is a **pure allocation function**: it never creates cost. The two buckets must
always reconcile back to the input. No I/O, no persistence, no external calls.

---

## Terminology

| Term | Meaning |
|------|---------|
| **item** | The single priced thing being bought (one per calculation). |
| **item_cost** | Cost of the item's base component only. |
| **buyer_cost** | A per-**buyer** discretionary add-on cost. Named for the fact each buyer selects their own. This is a *cost dimension*, not a payer. |
| **total** | `item_cost` + all add-ons (buyer_costs + any other ancillary). `total ≥ item_cost`, `total ≥ Σ buyer_cost`. |
| **buyer** | One individual in the group. Every buyer is either *included* or *not included* by the policy. |
| **cap** | Per-buyer spend ceiling the policy funds. `0` is the sentinel for "no cap" — the cap is treated as **infinite** (any spend is allowed / in-policy). |
| **class** | A discrete tier of the item (e.g. a quality/service level). Classes are **ranked**; higher rank = higher tier. |
| **covered** | Output bucket: money the policy funds. |
| **owed** | Output bucket: money the buyer funds. |

---

## Types

| Type | Definition |
|------|------------|
| `Money` | Non-negative fixed-point decimal (2 dp). *(Current implementation uses float; a Decimal with explicit remainder handling is the hardening target.)* |
| `Rate` | Decimal in `[0, 1)`. |
| `Id` | Opaque identifier. |
| `Class` | Member of a ranked, finite set. |

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
| C3 | `Σ buyer.buyer_cost == item.buyer_cost` (± 0.01). |
| C4 | `cap ≥ 0`; `cap == 0` means "no cap" (treated as infinite — any spend is in-policy). |
| C4b | `allowed_classes` empty means "all classes allowed". |
| C5 | `0 ≤ fee_rate < 1`. |
| C6 | `upgrade_context` present **iff** `mode == "CLASS"`. |
| C7 | Every `alternate_classes[*].class` is rankable against `selected_class`. |

### Preconditions (external — outside this function)

- The feature is only invoked when bucketing is enabled for the context
  (e.g. the account is eligible). This function assumes it should run.

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

### Invariants (must hold on every non-null allocation)

| # | Invariant |
|---|-----------|
| O1 | **Reconciliation:** `covered.item + owed.item + covered.buyer_cost + owed.buyer_cost == basis` (± 0.01), where `basis` is defined in the preamble. |
| O2 | No bucket field is negative. |
| O3 | `applicable == false` ⇒ `allocation == null` and `overage == 0`. |

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
N            = len(buyers)
item_per     = (total - buyer_cost) / N          # per-buyer base cost, add-ons excluded
basis        = total     if are_buyer_costs_allowed else item_cost
total_per    = basis / N                          # per-buyer total incl. allowed add-ons
cap          = policy.cap
included     = [b for b in buyers if not b.not_included]
excluded     = [b for b in buyers if b.not_included]

covered.item = covered.buyer_cost = owed.item = owed.buyer_cost = 0
overage = 0
```

---

### Mode A — `CAP`

**For each included buyer** (add-on `bc = buyer.buyer_cost`):

```
if cap > 0:                                    # cap == 0 ⇒ infinite: policy funds the full base
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

else:                                           # no enforceable cap → policy funds base
    covered.item += item_per
    if are_buyer_costs_allowed:
        covered.buyer_cost += bc
    else:
        owed.buyer_cost += bc
        overage         += bc
```

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

---

## Appendix — Concrete instantiation (flight travel)

The generic model maps onto the flight split-pay feature as follows:

| Generic | Flight domain |
|---------|---------------|
| item | A flight booking |
| item_cost | Airfare only |
| buyer_cost | Paid-seat cost |
| total | Airfare + all ancillaries |
| buyer | Passenger / traveler |
| not_included | Traveler beyond the policy's covered-guest count |
| cap | Per-passenger price cap |
| are_buyer_costs_allowed | Paid seats allowed by policy |
| buyer_not_included_fee | Per-additional-traveler ticketing fee |
| class / class rank | Cabin class / cabin hierarchy |
| covered bucket | Company (org wallet) |
| owed bucket | Traveler (personal card) |
| fee_rate | Payment processing fee (default 4%) |
| overage | "Over limit" upgrade amount shown to the traveler |

**Source of truth for the current implementation:**
`src/engine/policy/flight/base/strategy.py` (allocation core),
`src/data/itinerary/booking_intent/flight/model.py` (totals + fee),
`src/services/invoices/invoice_split_pay_helper.py` (fee back-calculation),
`src/core/finance/reconciliation.py` (reconciliation invariant).
