"""
Reference allocator — a direct transcription of bucket-calculations-spec.md §3.

This exists ONLY to derive the expected-output fixtures in cases/expected/ and to
let validate_cases.py self-check. It is deliberately literal: branch order,
round() placement and accumulation order mirror the pseudocode line for line,
including the spec's known quirks (see cases/README.md "Findings").

Not intended as production code.
"""

# One ranked class universe for the whole suite: TIER_* for the spec-derived cases,
# the cabin ladder for the ENG-1035 production cases.
CLASS_RANKS = {
    "TIER_1": 1, "TIER_2": 2, "TIER_3": 3, "TIER_4": 4,
    "BASIC": 1, "ECONOMY": 2, "PREMIUM_ECONOMY": 3, "BUSINESS": 4, "FIRST": 5,
}


def _m(x):
    """Normalise a money value to 2dp, killing float artifacts and -0.0."""
    v = round(float(x) + 0.0, 2)
    return 0.0 if v == 0 else v


def _rank(cls, ranks):
    return ranks[cls]


def allocate(inp, ranks=None):
    ranks = ranks or CLASS_RANKS

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
    basis = total if allowed else item_cost
    total_per = basis / n

    included = [b for b in buyers if not b["not_included"]]
    excluded = [b for b in buyers if b["not_included"]]

    c_item = c_bc = o_item = o_bc = 0.0
    overage = 0.0

    # G2 standing violation: a policy fact, independent of mode and of any
    # allocation. Emitted on every return path, including not-applicable ones.
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
                    # G3: cap == 0 is unlimited. The buyer still owes the add-on,
                    # but it is not overage against a cap that does not exist.
                    o_bc += bc

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
            "basis": _m(basis),
            "total": _m(total),
        },
    }
