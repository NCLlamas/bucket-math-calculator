"""
Reference allocator — a direct transcription of bucket-calculations-spec.md §3.

This exists ONLY to derive the expected-output fixtures in cases/expected/ and to
let validate_cases.py self-check. It is deliberately literal: branch order,
round() placement and accumulation order mirror the pseudocode line for line,
including the spec's known quirks (see cases/README.md "Findings").

Not intended as an implementation to ship.
"""

# One ranked class universe for the whole suite: TIER_* for the branch probes,
# the second ladder for the composite scenarios.
CLASS_RANKS = {
    "TIER_1": 1, "TIER_2": 2, "TIER_3": 3, "TIER_4": 4,
    "BASIC": 1, "ECONOMY": 2, "PREMIUM_ECONOMY": 3, "BUSINESS": 4, "FIRST": 5,
}


EPSILON = 0.01   # spec §1 Money tolerance: one minor unit


class InvalidInput(Exception):
    """Raised when one or more input constraints fail. Carries every failure."""

    def __init__(self, failures):
        self.failures = failures                      # [(constraint, message)]
        ids = ", ".join(sorted({c for c, _ in failures}))
        super().__init__(f"{len(failures)} constraint failure(s): {ids}")

    @property
    def constraints(self):
        return sorted({c for c, _ in self.failures})


def validate(inp, ranks=None):
    """Evaluate every checkable clause of C1-C7. Raise with ALL failures, or return.

    Money comparisons carry the +/-0.01 tolerance; Rate is strict; counts are exact.
    """
    ranks = ranks or CLASS_RANKS
    f = []

    def money_ok(v):
        return isinstance(v, (int, float)) and float(v) >= -EPSILON

    item = inp["item"]
    buyers = inp["buyers"]
    policy = inp["policy"]
    total = float(item["total"])
    item_cost = float(item["item_cost"])
    agg_bc = float(item["buyer_cost"])

    # --- C1: non-negative money and counts, at least one buyer
    for label, v in (("item.total", total), ("item.item_cost", item_cost),
                     ("item.buyer_cost", agg_bc),
                     ("policy.buyer_not_included_fee", float(policy["buyer_not_included_fee"]))):
        if not money_ok(v):
            f.append(("C1", f"{label} must be >= 0, got {v}"))
    for b in buyers:
        if not money_ok(float(b["buyer_cost"])):
            f.append(("C1", f"buyer {b['id']}.buyer_cost must be >= 0, got {b['buyer_cost']}"))
    if int(policy["included_buyer_count"]) < 0:
        f.append(("C1", f"policy.included_buyer_count must be >= 0, "
                        f"got {policy['included_buyer_count']}"))
    if len(buyers) < 1:
        f.append(("C1", "buyers must contain at least one entry"))

    # --- C2: components cannot exceed the total
    if item_cost > total + EPSILON:
        f.append(("C2", f"item_cost {item_cost} exceeds total {total}"))
    if agg_bc > total + EPSILON:
        f.append(("C2", f"item.buyer_cost {agg_bc} exceeds total {total}"))

    # --- C3: per-buyer add-ons must sum to the aggregate
    summed = sum(float(b["buyer_cost"]) for b in buyers)
    if abs(summed - agg_bc) > EPSILON:
        f.append(("C3", f"sum of buyer.buyer_cost {summed} != item.buyer_cost {agg_bc}"))

    # --- C4: cap non-negative (0 is the unlimited sentinel)
    cap = float(policy["cap"])
    if not money_ok(cap):
        f.append(("C4", f"policy.cap must be >= 0, got {cap}"))

    # --- C5: Rate strictly in [0, 1)
    rate = float(inp["fee_rate"])
    if not (0 <= rate < 1):
        f.append(("C5", f"fee_rate must satisfy 0 <= rate < 1, got {rate}"))

    # --- C6: upgrade_context present iff CLASS
    mode = inp.get("mode")
    if mode not in ("CAP", "CLASS"):
        f.append(("C6", f"mode must be CAP or CLASS, got {mode!r}"))
    else:
        has_ctx = "upgrade_context" in inp and inp["upgrade_context"] is not None
        if mode == "CLASS" and not has_ctx:
            f.append(("C6", "mode is CLASS but upgrade_context is absent"))
        if mode == "CAP" and has_ctx:
            f.append(("C6", "mode is CAP but upgrade_context is present"))

    # --- C7: every class reference is drawn from the configured set
    referenced = list(policy["allowed_classes"])
    ctx = inp.get("upgrade_context")
    if ctx:
        referenced.append(ctx["selected_class"])
        referenced += [o["class"] for o in ctx["alternate_classes"]]
        for o in ctx["alternate_classes"]:
            if not money_ok(float(o["cost"])):
                f.append(("C1", f"alternate_classes cost must be >= 0, got {o['cost']}"))
    for c in referenced:
        if c not in ranks:
            f.append(("C7", f"class {c!r} is not in the configured class set"))

    if f:
        raise InvalidInput(f)


def _m(x):
    """Normalise a money value to 2dp, killing float artifacts and -0.0."""
    v = round(float(x) + 0.0, 2)
    return 0.0 if v == 0 else v


def _rank(cls, ranks):
    return ranks[cls]


def allocate(inp, ranks=None):
    ranks = ranks or CLASS_RANKS
    validate(inp, ranks)

    mode = inp["mode"]
    item = inp["item"]
    buyers = inp["buyers"]
    policy = inp["policy"]
    fee_rate = float(inp["fee_rate"])

    total = float(item["total"])
    item_cost = float(item["item_cost"])
    agg_buyer_cost = float(item["buyer_cost"])

    cap = float(policy["cap"])
    allowed = bool(policy["are_buyer_costs_allowed"])
    not_incl_fee = float(policy["buyer_not_included_fee"])
    allowed_classes = policy["allowed_classes"]

    # --- Preamble ------------------------------------------------------------
    n = len(buyers)
    item_per = (total - agg_buyer_cost) / n
    # Yardstick for the overage comparison ONLY — never a bucket or a
    # reconciliation target. Buckets always partition `total`.
    overage_basis = total if allowed else item_cost
    total_per = overage_basis / n

    included = [b for b in buyers if not b["not_included"]]
    excluded = [b for b in buyers if b["not_included"]]

    c_item = c_bc = o_item = o_bc = 0.0
    overage = 0.0

    # Standing violation: a policy fact, independent of mode and of any allocation.
    # Emitted on every return path, including the not-applicable ones.
    standing = []
    if not allowed and agg_buyer_cost > 0:
        standing.append(("BUYER_COST_NOT_ALLOWED", "REQUIRES_APPROVAL",
                         f"{_m(agg_buyer_cost):.2f} add-on cost not allowed by policy"))
    violations = list(standing)

    if mode == "CAP":
        for b in included:
            bc = float(b["buyer_cost"])
            if cap > 0:
                if item_per > cap:
                    c_item += cap
                    o_item += item_per - cap
                    o_bc += bc
                else:
                    c_item += item_per
                    if allowed:
                        room = cap - item_per
                        c_bc += min(bc, room)
                        o_bc += max(bc - room, 0)
                    else:
                        o_bc += bc

                if allowed:
                    this_overage = max(total_per - cap, 0)
                else:
                    this_overage = max(item_per - cap, 0) + bc
                overage += round(this_overage, 2)
            else:
                c_item += item_per
                if allowed:
                    c_bc += bc
                else:
                    # cap == 0 disables the CAP comparison only. A disallowed add-on
                    # is out of policy on its own terms, so it is still overage.
                    o_bc += bc
                    overage += bc

        excluded_cost = 0.0
        for b in excluded:
            bc = float(b["buyer_cost"])
            o_item += item_per + not_incl_fee
            o_bc += bc
            excluded_cost += item_per + not_incl_fee + bc

        if overage <= 0 and excluded_cost <= 0:
            return {
                "applicable": False,
                "allocation": None,
                "derived": None,
                "overage": 0.0,
                "violations": list(standing),
            }

        if overage > 0 and cap > 0:
            violations.append(("CAP", "REQUIRES_USER_CHOICE",
                               f"{_m(overage):.2f} over limit"))
        if excluded_cost > 0:
            violations.append(("NOT_INCLUDED", "REQUIRES_USER_CHOICE",
                               f"{len(excluded)} not-included buyer(s)"))

        overage += excluded_cost

    elif mode == "CLASS":
        ctx = inp["upgrade_context"]
        selected = ctx["selected_class"]
        alternates = ctx["alternate_classes"]

        def eligible(opt):
            if _rank(opt["class"], ranks) > _rank(selected, ranks):
                return False
            if allowed_classes and opt["class"] not in allowed_classes:
                return False
            if cap != 0 and not (float(opt["cost"]) / n < cap):
                return False
            return True

        pool = [o for o in alternates if eligible(o)]
        best = max(pool, key=lambda o: (_rank(o["class"], ranks), float(o["cost"]))) if pool else None

        if best is not None:
            benchmark_per = float(best["cost"]) / n
            reason = "difference from in-policy class"
        elif cap > 0:
            benchmark_per = cap
            reason = "over cap"
        else:
            return {
                "applicable": False,
                "allocation": None,
                "derived": None,
                "overage": 0.0,
                "violations": standing + [("CLASS", "REQUIRES_APPROVAL",
                                           "no in-policy benchmark available")],
            }

        owed_per = item_per - benchmark_per
        if owed_per <= 0:
            return {
                "applicable": False,
                "allocation": None,
                "derived": None,
                "overage": 0.0,
                "violations": standing + [("CLASS", "REQUIRES_APPROVAL",
                                           "selected class is within policy")],
            }

        for b in included:
            c_item += benchmark_per
            c_bc += float(b["buyer_cost"])
            o_item += owed_per

        for b in excluded:
            o_item += item_per + not_incl_fee
            o_bc += float(b["buyer_cost"])

        # In CLASS mode add-ons are ALWAYS the buyer's cost.
        if agg_buyer_cost > 0:
            o_bc = agg_buyer_cost
            c_bc = 0.0

        overage = round(o_item, 2)
        violations.append(("CLASS", "REQUIRES_SPLIT_PAY", f"{_m(o_item):.2f} {reason}"))

    else:
        raise ValueError(f"unknown mode {mode!r}")

    # --- Post-step -----------------------------------------------------------
    covered_total = round(c_item + c_bc, 2)
    owed_base = o_item + o_bc
    owed_fee = owed_base * fee_rate
    owed_total = round(owed_base * (1 + fee_rate), 2)

    return {
        "applicable": True,
        "allocation": {
            "covered": {"item": _m(c_item), "buyer_cost": _m(c_bc)},
            "owed": {"item": _m(o_item), "buyer_cost": _m(o_bc)},
            "covered_buyer_count": len(included),
            "fee_rate": fee_rate,
        },
        "derived": {
            "covered": {"total": _m(covered_total)},
            "owed": {"base": _m(owed_base), "fee": _m(owed_fee), "total": _m(owed_total)},
        },
        "overage": _m(overage),
        "violations": violations,
        "_reconciliation": {
            "sum_of_buckets": _m(c_item + o_item + c_bc + o_bc),
            "target": _m(total + len(excluded) * not_incl_fee),
            "overage_basis": _m(overage_basis),
            "total": _m(total),
        },
    }
