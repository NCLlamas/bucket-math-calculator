"""
Inputs that violate C1-C7. Every one of these must raise; none produces an allocation.

Expected outputs record the SET of failing constraint ids, not the messages — spec
§1 Validation makes wording informational. Cases that trip several clauses at once
list all of them, which is the point: validation reports every failure in one raise
rather than stopping at the first.

Each entry names the damage the constraint prevents. Before validation existed, all
but two of these returned a confident, plausible, wrong answer instead of failing —
the `silent_damage` note records what the caller would have received.
"""

from case_table import buyer, cap_input, class_input

FEE = 0.04

# Baseline that every mutation starts from: total 1000, item_cost 800, buyer_cost 200,
# two buyers @100, cap 450, add-ons allowed. Valid, and yields
# cov(800,100) owed(0,100) overage=100 owed.total=104.
def _base(**over):
    kw = dict(total=1000.0, item_cost=800.0, buyer_cost=200.0,
              buyers=[buyer("b1", 100.0), buyer("b2", 100.0)],
              cap=450.0, allowed=True, not_incl_fee=25.0, included_count=2,
              fee_rate=FEE, allowed_classes=[])
    kw.update(over)
    return cap_input(**kw)


CASES = [
    dict(
        id="invalid-01-no-buyers",
        desc="C1: empty buyers list. N == 0 makes the per-buyer derivation undefined. "
             "Also trips C3, since an empty sum cannot match a non-zero aggregate.",
        provenance="spec:C1",
        tags=["invalid", "C1", "C3", "structural", "multi-failure"],
        expects_raise=["C1", "C3"],
        silent_damage="Previously crashed with a bare ZeroDivisionError — a language "
                      "fault rather than a domain error.",
        input=_base(buyers=[], buyer_cost=200.0),
    ),
    dict(
        id="invalid-02-negative-total",
        desc="C1: negative `total`. Also trips C2, because a positive item_cost now "
             "exceeds it.",
        provenance="spec:C1",
        tags=["invalid", "C1", "C2", "silent", "multi-failure", "core"],
        expects_raise=["C1", "C2"],
        silent_damage="Returned applicable=false, allocation=null — indistinguishable "
                      "from a clean in-policy pass.",
        input=_base(total=-1000.0),
    ),
    dict(
        id="invalid-03-item-cost-exceeds-total",
        desc="C2: item_cost 1400 against a total of 1000.",
        provenance="spec:C2",
        tags=["invalid", "C2", "silent", "core"],
        expects_raise=["C2"],
        silent_damage="Inert while add-ons are allowed (basis reads `total`), but the "
                      "same payload with are_buyer_costs_allowed=false doubled the "
                      "buyer's overage from 100 to 200. Severity depended on an "
                      "unrelated policy flag.",
        input=_base(item_cost=1400.0),
    ),
    dict(
        id="invalid-04-add-on-aggregate-mismatch",
        desc="C3: item.buyer_cost says 260 while the per-buyer costs sum to 200.",
        provenance="spec:C3",
        tags=["invalid", "C3", "silent", "core"],
        expects_raise=["C3"],
        silent_damage="Returned cov(740,160) owed(0,40): buckets summed to 940 against "
                      "a total of 1000. Sixty units of the input vanished while every "
                      "field looked plausible.",
        input=_base(buyer_cost=260.0),
    ),
    dict(
        id="invalid-05-negative-cap",
        desc="C4: negative cap. The sentinel test is `cap > 0`, so anything below zero "
             "falls into the unlimited branch.",
        provenance="spec:C4",
        tags=["invalid", "C4", "silent", "core"],
        expects_raise=["C4"],
        silent_damage="Returned applicable=false: the most restrictive input "
                      "conceivable silently produced the most permissive behaviour.",
        input=_base(cap=-450.0),
    ),
    dict(
        id="invalid-06-fee-rate-as-percent",
        desc="C5: fee_rate given as 4 rather than 0.04 — the everyday percent-versus-"
             "fraction slip.",
        provenance="spec:C5",
        tags=["invalid", "C5", "silent", "core"],
        expects_raise=["C5"],
        silent_damage="Every bucket stayed correct while owed.total went from 104.00 "
                      "to 500.00. The buyer is charged five times over and nothing in "
                      "the allocation looks wrong.",
        input=_base(fee_rate=4.0),
    ),
    dict(
        id="invalid-07-fee-rate-at-upper-bound",
        desc="C5 boundary: fee_rate exactly 1.0. Rate is compared strictly, so the "
             "half-open interval [0, 1) excludes it.",
        provenance="spec:C5 boundary",
        tags=["invalid", "C5", "boundary", "rate-is-strict"],
        expects_raise=["C5"],
        silent_damage="Doubled owed.total.",
        input=_base(fee_rate=1.0),
    ),
    dict(
        id="invalid-08-class-context-in-cap-mode",
        desc="C6: mode is CAP but an upgrade_context is supplied. Harmless to the "
             "arithmetic — the context is never read — but C6 is an `iff`.",
        provenance="spec:C6",
        tags=["invalid", "C6", "inert"],
        expects_raise=["C6"],
        silent_damage="None. Returned the correct allocation and ignored the context. "
                      "Included because the spec enforces uniformly rather than by "
                      "severity.",
        input={**_base(), "upgrade_context": {
            "selected_class": "TIER_3",
            "alternate_classes": [{"class": "TIER_2", "cost": 600.0}]}},
    ),
    dict(
        id="invalid-09-class-mode-without-context",
        desc="C6 in the other direction: mode is CLASS with no upgrade_context.",
        provenance="spec:C6",
        tags=["invalid", "C6", "structural"],
        expects_raise=["C6"],
        silent_damage="Previously crashed with a bare KeyError.",
        input={**_base(), "mode": "CLASS"},
    ),
    dict(
        id="invalid-10-negative-buyer-cost",
        desc="C1: a buyer carries a negative add-on cost. Also trips C3 — the "
             "per-buyer costs no longer sum to the aggregate.",
        provenance="spec:C1",
        tags=["invalid", "C1", "C3", "multi-failure"],
        expects_raise=["C1", "C3"],
        silent_damage="Produced a negative owed.buyer_cost, violating O2.",
        input=_base(buyers=[buyer("b1", -50.0), buyer("b2", 100.0)], buyer_cost=200.0),
    ),
    dict(
        id="invalid-11-stacked-failures",
        desc="Three independent clauses at once. Validation must report all three, "
             "not stop at the first.",
        provenance="spec:C2 + C4 + C5",
        tags=["invalid", "C2", "C4", "C5", "multi-failure", "granularity", "core"],
        expects_raise=["C2", "C4", "C5"],
        silent_damage="Compounded: an inflated basis, an unlimited cap, and a doubled "
                      "fee, each masking the others.",
        input=_base(item_cost=1400.0, cap=-1.0, fee_rate=1.0),
    ),
]
