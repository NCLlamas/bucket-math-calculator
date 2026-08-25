"""
The single source of truth for the validation suite.

Each entry defines one case: its id, human description, provenance, tags, and the
BucketCalculationInput payload. Expected outputs are DERIVED (tools/generate_cases.py)
so inputs and expectations can never drift apart.

provenance:
  "spec:<section>"  - branch coverage derived from bucket-calculations-spec.md
  "scenario:<n>"    - a composite scenario with a fixed expected output, defined in
                      case_table_scenarios.py
"""


def buyer(bid, bc=0.0, not_included=False):
    return {"id": bid, "not_included": not_included, "buyer_cost": bc}


def cap_input(total, item_cost, buyer_cost, buyers, cap, allowed,
              not_incl_fee=0.0, included_count=None, fee_rate=0.04,
              allowed_classes=None):
    if included_count is None:
        included_count = sum(1 for b in buyers if not b["not_included"])
    return {
        "mode": "CAP",
        "item": {"total": total, "item_cost": item_cost, "buyer_cost": buyer_cost},
        "buyers": buyers,
        "policy": {
            "cap": cap,
            "are_buyer_costs_allowed": allowed,
            "buyer_not_included_fee": not_incl_fee,
            "included_buyer_count": included_count,
            "allowed_classes": allowed_classes or [],
        },
        "fee_rate": fee_rate,
    }


def class_input(total, item_cost, buyer_cost, buyers, cap, allowed,
                selected, alternates, not_incl_fee=0.0, included_count=None,
                fee_rate=0.04, allowed_classes=None):
    inp = cap_input(total, item_cost, buyer_cost, buyers, cap, allowed,
                    not_incl_fee, included_count, fee_rate, allowed_classes)
    inp["mode"] = "CLASS"
    inp["upgrade_context"] = {
        "selected_class": selected,
        "alternate_classes": [{"class": c, "cost": v} for c, v in alternates],
    }
    return inp


CASES = [
    # ---------------------------------------------------------------- CAP mode
    dict(
        id="cap-01-within-cap-not-applicable",
        desc="Base cost per buyer sits under the cap and there are no add-ons: "
             "nothing is over policy, so there is no split at all.",
        provenance="spec:3.A finalize / applicable==false",
        tags=["cap", "not-applicable", "happy-path"],
        input=cap_input(1000, 1000, 0, [buyer("b1"), buyer("b2")], cap=800, allowed=True),
    ),
    dict(
        id="cap-02-base-exceeds-cap",
        desc="Base cost alone exceeds the cap. Cap room is fully consumed by the "
             "item; the excess plus fee falls to the buyer.",
        provenance="spec:3.A item_per > cap",
        tags=["cap", "over-cap", "core"],
        input=cap_input(1000, 1000, 0, [buyer("b1"), buyer("b2")], cap=400, allowed=True),
    ),
    dict(
        id="cap-03-exactly-at-cap",
        desc="Boundary: item_per == cap exactly. The comparison is strict (>), so "
             "this is in-policy and yields no split.",
        provenance="spec:3.A boundary item_per == cap",
        tags=["cap", "boundary", "not-applicable"],
        input=cap_input(800, 800, 0, [buyer("b1"), buyer("b2")], cap=400, allowed=True),
    ),
    dict(
        id="cap-04-addons-allowed-fit-in-room",
        desc="Add-ons are allowed and fit entirely inside the leftover cap room, "
             "so the policy funds them and nothing is owed.",
        provenance="spec:3.A room branch, bc <= room",
        tags=["cap", "add-ons", "not-applicable"],
        input=cap_input(900, 800, 100, [buyer("b1", 50), buyer("b2", 50)], cap=500, allowed=True),
    ),
    dict(
        id="cap-05-addon-exactly-fills-room",
        desc="Boundary: the add-on exactly equals the leftover cap room. min/max "
             "clamps must produce zero owed and zero overage.",
        provenance="spec:3.A boundary bc == room",
        tags=["cap", "add-ons", "boundary", "not-applicable"],
        input=cap_input(900, 800, 100, [buyer("b1", 50), buyer("b2", 50)], cap=450, allowed=True),
    ),
    dict(
        id="cap-06-addons-allowed-exceed-room",
        desc="Add-ons are allowed but overflow the leftover cap room. The overflow "
             "splits into owed.buyer_cost while the item stays fully covered.",
        provenance="spec:3.A room branch, bc > room",
        tags=["cap", "add-ons", "over-cap", "core"],
        input=cap_input(1000, 800, 200, [buyer("b1", 100), buyer("b2", 100)], cap=450, allowed=True),
    ),
    dict(
        id="cap-07-addons-not-allowed",
        desc="Add-ons are disallowed, so the full add-on cost is owed regardless of "
             "cap room, and overage uses the item-only formula. Emits both the CAP "
             "and the BUYER_COST_NOT_ALLOWED violation.",
        provenance="spec:3.A are_buyer_costs_allowed == false; standing violation",
        tags=["cap", "add-ons", "not-allowed", "core", "two-violations",
              "reconciliation-defect"],
        input=cap_input(1000, 800, 200, [buyer("b1", 100), buyer("b2", 100)], cap=450, allowed=False),
    ),
    dict(
        id="cap-08-no-cap-addons-allowed",
        desc="cap == 0 sentinel (infinite). Add-ons allowed, so the policy funds "
             "everything and there is no split.",
        provenance="spec:3.A cap == 0 branch, allowed",
        tags=["cap", "no-cap", "sentinel", "not-applicable"],
        input=cap_input(1000, 800, 200, [buyer("b1", 100), buyer("b2", 100)], cap=0, allowed=True),
    ),
    dict(
        id="cap-09-no-cap-addons-not-allowed",
        desc="cap == 0 with add-ons disallowed. The buyer owes the add-on, but cap 0 "
             "is unlimited so nothing is over it: overage stays 0 and there is no "
             "split. A BUYER_COST_NOT_ALLOWED violation is still emitted -- the case "
             "for `allocation == null` alongside a NON-empty violations list.",
        provenance="spec:3.A cap == 0 branch; standing violation; unlimited-cap rule",
        tags=["cap", "no-cap", "sentinel", "not-applicable",
              "violation-without-allocation", "add-ons", "not-allowed", "edge"],
        input=cap_input(1000, 800, 200, [buyer("b1", 100), buyer("b2", 100)], cap=0, allowed=False),
    ),
    dict(
        id="cap-10-not-included-buyer-only",
        desc="Every included buyer is in policy, but one buyer is beyond the "
             "included count. Only the NOT_INCLUDED violation fires and the "
             "not-included fee is added.",
        provenance="spec:3.A not-included loop",
        tags=["cap", "not-included", "core"],
        input=cap_input(1000, 1000, 0,
                        [buyer("b1"), buyer("b2", not_included=True)],
                        cap=600, allowed=True, not_incl_fee=25, included_count=1),
    ),
    dict(
        id="cap-11-overage-and-not-included",
        desc="Both failure modes at once: included buyers are over cap AND a third "
             "buyer is not included. Two violations; excluded cost is folded into "
             "overage last.",
        provenance="spec:3.A finalize ordering",
        tags=["cap", "over-cap", "not-included", "two-violations", "core", "fee-creates-cost"],
        input=cap_input(1500, 1500, 0,
                        [buyer("b1"), buyer("b2"), buyer("b3", not_included=True)],
                        cap=400, allowed=True, not_incl_fee=25, included_count=2),
    ),
    dict(
        id="cap-12-all-buyers-not-included",
        desc="included_buyer_count == 0. Nothing is covered, covered_buyer_count is "
             "0, and overage is entirely excluded cost.",
        provenance="spec:3.A all excluded",
        tags=["cap", "not-included", "zero-covered", "edge"],
        input=cap_input(1000, 1000, 0,
                        [buyer("b1", not_included=True), buyer("b2", not_included=True)],
                        cap=500, allowed=True, not_incl_fee=25, included_count=0),
    ),
    dict(
        id="cap-13-uneven-addons-average-overage",
        desc="Three buyers with different add-ons. Exercises the spec's use of the "
             "AVERAGE total_per for overage: the buyer with no add-on still accrues "
             "overage, so overage != owed.base.",
        provenance="spec:3.A this_overage uses total_per (average)",
        tags=["cap", "add-ons", "multi-buyer", "average-overage", "edge"],
        input=cap_input(1500, 1200, 300,
                        [buyer("b1", 0), buyer("b2", 100), buyer("b3", 200)],
                        cap=450, allowed=True),
    ),
    dict(
        id="cap-14-rounding-thirds",
        desc="Total does not divide evenly across 3 buyers. Per-buyer overage is "
             "rounded before accumulation while owed.item is not, so overage and "
             "owed.item legitimately differ by a cent.",
        provenance="spec:3.A round(this_overage, 2) placement",
        tags=["cap", "rounding", "multi-buyer", "edge"],
        input=cap_input(1000, 1000, 0,
                        [buyer("b1"), buyer("b2"), buyer("b3")],
                        cap=300, allowed=True),
    ),
    dict(
        id="cap-15-zero-fee-rate",
        desc="fee_rate == 0 (lower bound of Rate). owed.fee must be 0 and "
             "owed.total must equal owed.base exactly.",
        provenance="spec:C5 lower bound",
        tags=["cap", "fee", "boundary"],
        input=cap_input(1000, 1000, 0, [buyer("b1"), buyer("b2")],
                        cap=400, allowed=True, fee_rate=0.0),
    ),
    dict(
        id="cap-16-single-buyer",
        desc="Minimum group size (len(buyers) == 1). Per-buyer and aggregate figures "
             "collapse to the same numbers.",
        provenance="spec:C1 len(buyers) >= 1",
        tags=["cap", "single-buyer", "boundary"],
        input=cap_input(600, 500, 100, [buyer("b1", 100)], cap=450, allowed=True),
    ),

    # -------------------------------------------------------------- CLASS mode
    dict(
        id="class-01-benchmark-from-alternate",
        desc="A cheaper in-policy class exists below the selected class. Its "
             "per-buyer cost becomes the benchmark; the difference is owed.",
        provenance="spec:3.B best exists",
        tags=["class", "benchmark", "core"],
        input=class_input(2000, 2000, 0, [buyer("b1"), buyer("b2")],
                          cap=0, allowed=True, selected="TIER_3",
                          alternates=[("TIER_1", 800), ("TIER_2", 1200)]),
    ),
    dict(
        id="class-02-tie-rank-highest-cost-wins",
        desc="Two alternates share the top eligible rank. The tiebreak is highest "
             "cost, which yields the larger benchmark and the smaller owed amount.",
        provenance="spec:3.B best = highest (rank, then cost)",
        tags=["class", "benchmark", "tiebreak", "edge"],
        input=class_input(2000, 2000, 0, [buyer("b1"), buyer("b2")],
                          cap=0, allowed=True, selected="TIER_3",
                          alternates=[("TIER_2", 1200), ("TIER_2", 1400)]),
    ),
    dict(
        id="class-03-no-eligible-falls-back-to-cap",
        desc="The only alternate outranks the selected class, so no benchmark class "
             "is eligible. cap > 0 becomes the benchmark and the reason changes to "
             "'over cap'.",
        provenance="spec:3.B fallback benchmark_per = cap",
        tags=["class", "benchmark", "cap-fallback", "core"],
        input=class_input(2000, 2000, 0, [buyer("b1"), buyer("b2")],
                          cap=700, allowed=True, selected="TIER_3",
                          alternates=[("TIER_4", 3000)]),
    ),
    dict(
        id="class-04-no-eligible-no-cap-requires-approval",
        desc="No eligible alternate AND cap == 0, so there is no benchmark to "
             "compare against. Returns not-applicable with REQUIRES_APPROVAL.",
        provenance="spec:3.B no best and cap == 0",
        tags=["class", "not-applicable", "requires-approval", "core"],
        input=class_input(2000, 2000, 0, [buyer("b1"), buyer("b2")],
                          cap=0, allowed=True, selected="TIER_3",
                          alternates=[("TIER_4", 3000)]),
    ),
    dict(
        id="class-05-owed-per-nonpositive-requires-approval",
        desc="Boundary: the benchmark equals item_per so owed_per == 0. Non-positive "
             "owed_per short-circuits to not-applicable with REQUIRES_APPROVAL.",
        provenance="spec:3.B owed_per <= 0",
        tags=["class", "not-applicable", "requires-approval", "boundary"],
        input=class_input(1200, 1200, 0, [buyer("b1"), buyer("b2")],
                          cap=0, allowed=True, selected="TIER_2",
                          alternates=[("TIER_1", 1200)]),
    ),
    dict(
        id="class-06-filtered-by-allowed-classes",
        desc="allowed_classes restricts the benchmark pool. TIER_2 is cheaper and "
             "outranks TIER_1 but is not allowed, so the weaker TIER_1 benchmark is "
             "used and more is owed.",
        provenance="spec:3.B eligible() allowed_classes clause",
        tags=["class", "benchmark", "allowed-classes", "core"],
        input=class_input(2000, 2000, 0, [buyer("b1"), buyer("b2")],
                          cap=0, allowed=True, selected="TIER_3",
                          alternates=[("TIER_1", 600), ("TIER_2", 1200)],
                          allowed_classes=["TIER_1"]),
    ),
    dict(
        id="class-07-filtered-by-cap",
        desc="The cap also filters the benchmark pool: an alternate whose per-buyer "
             "cost is not strictly below the cap is ineligible, pushing the "
             "benchmark down to a cheaper class.",
        provenance="spec:3.B eligible() cap clause",
        tags=["class", "benchmark", "cap-filter", "edge"],
        input=class_input(2000, 2000, 0, [buyer("b1"), buyer("b2")],
                          cap=500, allowed=True, selected="TIER_3",
                          alternates=[("TIER_1", 500), ("TIER_2", 1200)]),
    ),
    dict(
        id="class-08-addons-always-owed",
        desc="CLASS mode overrides add-on handling: even with "
             "are_buyer_costs_allowed == true, the whole aggregate add-on cost is "
             "forced into owed.buyer_cost and covered.buyer_cost is zeroed.",
        provenance="spec:3.B add-on override",
        tags=["class", "add-ons", "override", "core"],
        input=class_input(2200, 2000, 200, [buyer("b1", 100), buyer("b2", 100)],
                          cap=0, allowed=True, selected="TIER_3",
                          alternates=[("TIER_2", 1200)]),
    ),
    dict(
        id="class-09-not-included-buyer-no-second-violation",
        desc="A not-included buyer in CLASS mode pays full cost plus the fee, but "
             "CLASS mode emits only the CLASS violation -- no NOT_INCLUDED "
             "violation, unlike CAP mode.",
        provenance="spec:3.B not-included loop + violation asymmetry",
        tags=["class", "not-included", "violation-asymmetry", "edge", "fee-creates-cost"],
        input=class_input(3000, 3000, 0,
                          [buyer("b1"), buyer("b2"), buyer("b3", not_included=True)],
                          cap=0, allowed=True, selected="TIER_3",
                          alternates=[("TIER_2", 1800)],
                          not_incl_fee=25, included_count=2),
    ),
    dict(
        id="class-10-addons-not-allowed-still-owed",
        desc="are_buyer_costs_allowed == false in CLASS mode. The override lands on "
             "the same result as the allowed case, but basis becomes item_cost, which "
             "surfaces the reconciliation ambiguity. Also the ONLY check anywhere "
             "that the BUYER_COST_NOT_ALLOWED violation is mode-independent, and it "
             "is derived rather than fixed -- so it confirms the spec, not correctness.",
        provenance="spec:3.B override with allowed == false; BUYER_COST_NOT_ALLOWED in CLASS mode",
        tags=["class", "add-ons", "not-allowed", "reconciliation-defect",
              "derived-only", "edge"],
        input=class_input(2200, 2000, 200, [buyer("b1", 100), buyer("b2", 100)],
                          cap=0, allowed=False, selected="TIER_3",
                          alternates=[("TIER_2", 1200)]),
    ),
]
