"""
Composite scenarios with independently-established expected outputs.

These differ from `case_table.py` in kind, not just in content:

* `case_table.py` cases are **branch probes**. Each isolates one path through
  spec §3, and its expected output is DERIVED from `reference_impl.py`. They prove
  an implementation is self-consistent with the spec as written.
* The cases here are **whole scenarios**, each combining several policy conditions
  at once. Their expected outputs are FIXED — transcribed from an independently
  established ground truth, never derived. They prove an implementation is correct,
  which is a different claim.

That distinction is the point. A derived fixture can only ever confirm what the
spec already says; if the spec is wrong, the fixture is wrong in the same direction
and passes anyway. A fixed fixture can disagree with the spec, and when it does the
fixture wins and the spec has a defect.

The generator runs `reference_impl.py` over each input here as well, and writes any
difference into a `divergence_from_spec` block on the expected file. There are
currently none — earlier rounds surfaced three, and all three were resolved by
correcting the spec. See cases/README.md.

Every value below is stated in the generic vocabulary of the spec. Nothing in this
file, or in the fixtures it emits, refers to any external system.
"""

from case_table import buyer, cap_input, class_input

# Ranked class set used by these scenarios, alongside the TIER_* set the branch
# probes use. Published in cases/manifest.json under `class_ranks`.
SCENARIO_CLASS_RANKS = {
    "BASIC": 1,
    "ECONOMY": 2,
    "PREMIUM_ECONOMY": 3,
    "BUSINESS": 4,
    "FIRST": 5,
}

# The ground truth records allocation buckets and overage but no fee-inclusive
# totals, so `derived` is not asserted for these cases (see README, open item O-5).
# The real rate is still carried on the input.
FEE = 0.04
NOT_INCLUDED_FEE = 35.0


def _alloc(c_item, c_bc, o_item, o_bc, n_covered):
    return {
        "covered": {"item": c_item, "buyer_cost": c_bc},
        "owed": {"item": o_item, "buyer_cost": o_bc},
        "covered_buyer_count": n_covered,
        "fee_rate": FEE,
    }


def _out(applicable, overage, violations, allocation=None):
    return {
        "applicable": applicable,
        "allocation": allocation,
        "derived": None,
        "overage": overage,
        "violations": violations,
        "assert_skip": ["derived"],
    }


CASES = [
    dict(
        id="scenario-01-in-policy-no-violations",
        desc="Single buyer, item cost 505.40 comfortably under the 650 cap, no "
             "add-ons. The clean baseline: nothing is over policy, so there is no "
             "split and no violation.",
        provenance="scenario:01",
        tags=["scenario", "cap", "not-applicable", "happy-path"],
        input=cap_input(505.40, 505.40, 0.0, [buyer("b1")],
                        cap=650.0, allowed=True, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE, allowed_classes=["ECONOMY"]),
        expected_override=_out(False, 0.0, []),
    ),
    dict(
        id="scenario-02-class-benchmark-below-cap",
        desc="Selected class costs 549.81 while the best in-policy alternate costs "
             "459.80; the 90.01 difference is owed. Note the benchmark is a cheaper "
             "option at the SAME rank as the selection, not a lower rank.",
        provenance="scenario:02",
        tags=["scenario", "class", "benchmark", "same-rank-benchmark"],
        input=class_input(549.81, 549.81, 0.0, [buyer("b1")],
                          cap=500.0, allowed=True, selected="ECONOMY",
                          alternates=[("ECONOMY", 459.80),
                                      ("PREMIUM_ECONOMY", 587.80),
                                      ("PREMIUM_ECONOMY", 648.80),
                                      ("FIRST", 651.80),
                                      ("FIRST", 925.40)],
                          not_incl_fee=NOT_INCLUDED_FEE, included_count=1, fee_rate=FEE,
                          allowed_classes=["BASIC", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS"]),
        expected_override=_out(
            True, 90.01,
            [{"code": "CLASS", "status": "REQUIRES_SPLIT_PAY",
              "message": "90.01 difference from in-policy class"}],
            _alloc(459.80, 0.0, 90.01, 0.0, 1)),
    ),
    dict(
        id="scenario-03-add-ons-not-allowed-no-cap",
        desc="cap == 0 with add-ons disallowed and 107.32 of add-on cost bought. The "
             "cap sentinel disables the CAP comparison only — the disallowed add-on is "
             "still out of policy on its own terms, so it is owed AND counts as "
             "overage. The case for a positive overage with NO `CAP` violation, since "
             "that violation is gated on `cap > 0`.",
        provenance="scenario:03",
        tags=["scenario", "cap", "no-cap", "sentinel", "add-ons", "not-allowed",
              "overage-without-cap-violation", "core"],
        input=cap_input(835.71, 728.39, 107.32, [buyer("b1", 107.32)],
                        cap=0.0, allowed=False, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE, allowed_classes=["ECONOMY"]),
        expected_override=_out(
            True, 107.32,
            [{"code": "BUYER_COST_NOT_ALLOWED", "status": "REQUIRES_APPROVAL",
              "message": "107.32 add-on cost not allowed by policy"}],
            _alloc(728.39, 0.0, 0.0, 107.32, 1)),
    ),
    dict(
        id="scenario-04-not-included-buyer",
        desc="Two buyers, one beyond the included count. The included buyer is within "
             "cap so the policy funds it; the not-included buyer's full share plus the "
             "35.00 not-included fee shifts to the owed bucket. Buckets exceed `total` "
             "by exactly that fee.",
        provenance="scenario:04",
        tags=["scenario", "cap", "not-included", "fee-creates-cost", "core"],
        input=cap_input(1180.80, 1180.80, 0.0,
                        [buyer("b1"), buyer("b2", not_included=True)],
                        cap=600.0, allowed=False, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE, allowed_classes=["ECONOMY"]),
        expected_override=_out(
            True, 625.40,
            [{"code": "NOT_INCLUDED", "status": "REQUIRES_USER_CHOICE",
              "message": "1 not-included buyer(s)"}],
            _alloc(590.40, 0.0, 625.40, 0.0, 1)),
    ),
    dict(
        id="scenario-05-class-no-benchmark-requires-approval",
        desc="CLASS mode where the selected class is outside `allowed_classes`, the "
             "only alternate shares its rank so is equally disallowed, and cap == 0. "
             "No benchmark can be resolved, so the calculation is not applicable and "
             "routes to approval.",
        provenance="scenario:05",
        tags=["scenario", "class", "not-applicable", "requires-approval"],
        input=class_input(451.76, 451.76, 0.0, [buyer("b1")],
                          cap=0.0, allowed=False, selected="FIRST",
                          alternates=[("FIRST", 2654.51)],
                          not_incl_fee=NOT_INCLUDED_FEE, included_count=1, fee_rate=FEE,
                          allowed_classes=["BASIC", "ECONOMY"]),
        expected_override=_out(
            False, 0.0,
            [{"code": "CLASS", "status": "REQUIRES_APPROVAL",
              "message": "no in-policy benchmark available"}]),
    ),
    dict(
        id="scenario-06-over-cap",
        desc="Item cost 848.80 against a 700 cap. The policy funds the cap, the buyer "
             "owes the 148.80 excess.",
        provenance="scenario:06",
        tags=["scenario", "cap", "over-cap", "core"],
        input=cap_input(848.80, 848.80, 0.0, [buyer("b1")],
                        cap=700.0, allowed=False, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(
            True, 148.80,
            [{"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "148.80 over limit"}],
            _alloc(700.0, 0.0, 148.80, 0.0, 1)),
    ),
    dict(
        id="scenario-07-large-values-over-cap",
        desc="Same branch as scenario-06 at an order of magnitude larger: cap 1500, "
             "item cost 1588.03, overage 88.03. Guards against precision loss where "
             "a small excess sits on top of a large base.",
        provenance="scenario:07",
        tags=["scenario", "cap", "over-cap", "precision"],
        input=cap_input(1588.03, 1588.03, 0.0, [buyer("b1")],
                        cap=1500.0, allowed=False, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["BASIC", "ECONOMY"]),
        expected_override=_out(
            True, 88.03,
            [{"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "88.03 over limit"}],
            _alloc(1500.0, 0.0, 88.03, 0.0, 1)),
    ),
    dict(
        id="scenario-08-add-ons-partial-cap-room",
        desc="Add-ons allowed and partly covered by leftover cap room. Item cost "
             "687.52 under the 700 cap leaves 12.48 of room, applied to the 184.88 "
             "add-on; the buyer covers the remaining 172.40. The only case where all "
             "four buckets carry distinct non-trivial values at once.",
        provenance="scenario:08",
        tags=["scenario", "cap", "add-ons", "partial-room", "four-buckets", "core"],
        input=cap_input(872.40, 687.52, 184.88, [buyer("b1", 184.88)],
                        cap=700.0, allowed=True, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(
            True, 172.40,
            [{"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "172.40 over limit"}],
            _alloc(687.52, 12.48, 0.0, 172.40, 1)),
    ),
    dict(
        id="scenario-09-multi-buyer-all-included",
        desc="Two buyers, both inside the included count, per-buyer share 771.20 under "
             "the 800 cap. Everything is funded and there is no violation. The "
             "contrast case to scenario-04.",
        provenance="scenario:09",
        tags=["scenario", "cap", "multi-buyer", "not-applicable", "happy-path"],
        input=cap_input(1542.40, 1542.40, 0.0, [buyer("b1"), buyer("b2")],
                        cap=800.0, allowed=False, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=2, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(False, 0.0, []),
    ),
    dict(
        id="scenario-10-stacked-add-ons-and-over-cap",
        desc="Two conditions at once: item cost 817.38 over the 700 cap AND a 22.56 "
             "add-on the policy does not allow. Overage sums both (117.38 + 22.56) "
             "and two violations are emitted.",
        provenance="scenario:10",
        tags=["scenario", "cap", "over-cap", "add-ons", "not-allowed",
              "two-violations", "core"],
        input=cap_input(839.94, 817.38, 22.56, [buyer("b1", 22.56)],
                        cap=700.0, allowed=False, not_incl_fee=NOT_INCLUDED_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(
            True, 139.94,
            [{"code": "BUYER_COST_NOT_ALLOWED", "status": "REQUIRES_APPROVAL",
              "message": "22.56 add-on cost not allowed by policy"},
             {"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "139.94 over limit"}],
            _alloc(700.0, 0.0, 117.38, 22.56, 1)),
    ),
]
