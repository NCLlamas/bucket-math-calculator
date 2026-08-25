
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

