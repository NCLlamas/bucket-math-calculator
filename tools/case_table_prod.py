"""
The eleven production cases from Linear ENG-1035, translated into the generic model.

Source: ENG-1035 "Prod data samples: seed I/O cases for checkout policy assessment
(Core + Complex)" — README + checkout_01..11 attachments. Every case came from
`itineraries.quest_booking_intent -> 'flight'` on Quest Prod.

Each entry carries `expected_override`: the PRODUCTION output, transcribed, not
derived. The generator also runs the spec reference implementation over the same
input and records any difference as a `divergence` block. Where prod and spec
disagree the prod numbers are authoritative — see cases/README.md "Findings".

Domain mapping (spec appendix + ENG-1035 README):

  total_fare                -> item.total                (aggregate, all pax)
  flight_cost               -> item.item_cost
  seat_cost                 -> item.buyer_cost
  passenger                 -> buyer
  passenger.is_additional   -> buyer.not_included
  price_cap                 -> policy.cap                (0 == no cap)
  are_paid_seats_allowed    -> policy.are_buyer_costs_allowed
  ticketing_fee             -> policy.buyer_not_included_fee
  covered guest count       -> policy.included_buyer_count
  allowed_cabin_classes     -> policy.allowed_classes     (canonicalised, see below)
  cabin_class               -> upgrade_context.selected_class
  other_fare_options        -> upgrade_context.alternate_classes
  split_pay_required        -> mode == "CLASS"            (else "CAP")

  upgrades                             -> overage
  split_pay_summary.company_flight_cost-> covered.item
  split_pay_summary.company_seat_cost  -> covered.buyer_cost
  split_pay_summary.user_flight_cost   -> owed.item
  split_pay_summary.user_seat_cost     -> owed.buyer_cost
  split_pay_summary == null            -> applicable == false

  PRICE_CAP              -> CAP
  CABIN_CLASS            -> CLASS
  MAX_TRAVELER_VIOLATION -> NOT_INCLUDED
  BUDGET_SEAT_COVERAGE   -> BUYER_COST_NOT_ALLOWED   (no code exists in the spec — G2)
  requires-split-pay / -approval / -user-choice
                         -> REQUIRES_SPLIT_PAY / REQUIRES_APPROVAL / REQUIRES_USER_CHOICE

Cabin canonicalisation: prod stores `allowed_cabin_classes` as display strings
("Premium Economy", "Business Refundable") but keys `other_fare_options` by
snake_case cabin ("premium_economy"). Both are folded to the ranked set below;
refundability is a fare attribute, not a class, so it is dropped from the class id.
"""

from case_table import buyer, cap_input, class_input

PROD_CLASS_RANKS = {
    "BASIC": 1,
    "ECONOMY": 2,
    "PREMIUM_ECONOMY": 3,
    "BUSINESS": 4,
    "FIRST": 5,
}

# Prod records no fee on payment_summary_flight — the 4% processing fee is applied
# downstream at invoicing. The real rate is kept on the input for fidelity, but the
# `derived` block is not asserted for these cases (no production ground truth).
FEE = 0.04
TICKETING_FEE = 35.0


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
    # ------------------------------------------------- Core (01-05)
    dict(
        id="prod-01-in-policy-no-violations",
        desc="In policy, no violations. Single traveler, fare 505.40 comfortably "
             "under the 650 cap, no paid seats. The clean baseline.",
        provenance="ENG-1035:01",
        tags=["prod", "core", "cap", "not-applicable", "happy-path"],
        source={"itinerary_id": "06a748d4-a76a-72fb-8000-1535bc3754bf",
                "prod_case": "checkout_01_in_policy_no_violations"},
        input=cap_input(505.40, 505.40, 0.0, [buyer("pax1")],
                        cap=650.0, allowed=True, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY"]),
        expected_override=_out(False, 0.0, []),
    ),
    dict(
        id="prod-02-class-upgrade-split-pay",
        desc="Class upgrade with split pay. Selected fare 549.81 sits above the best "
             "in-policy fare the org would cover (459.80); the 90.01 difference goes "
             "to the buyer. Note the benchmark is a cheaper fare in the SAME class, "
             "not a lower class.",
        provenance="ENG-1035:02",
        tags=["prod", "core", "class", "benchmark", "same-class-benchmark"],
        source={"itinerary_id": "06a73e55-5140-7dff-8000-8e01f8309d30",
                "prod_case": "checkout_02_class_upgrade_split_pay"},
        input=class_input(549.81, 549.81, 0.0, [buyer("pax1")],
                          cap=500.0, allowed=True, selected="ECONOMY",
                          alternates=[("ECONOMY", 459.80),
                                      ("PREMIUM_ECONOMY", 587.80),
                                      ("PREMIUM_ECONOMY", 648.80),
                                      ("FIRST", 651.80),
                                      ("FIRST", 925.40)],
                          not_incl_fee=TICKETING_FEE, included_count=1, fee_rate=FEE,
                          allowed_classes=["BASIC", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS"]),
        expected_override=_out(
            True, 90.01,
            [{"code": "CLASS", "status": "REQUIRES_SPLIT_PAY",
              "message": "Class Upgrade: $90.01 difference from in-policy fare"}],
            _alloc(459.80, 0.0, 90.01, 0.0, 1)),
    ),
    # ENG-1035 case 03 ("Cost over cap, no split pay") is deliberately NOT included.
    # It was the only fixture whose expected output encoded split-pay-UNavailable
    # behaviour (no buckets produced, CAP @ requires-approval). The system now assumes
    # split pay is always available, so that scenario cannot arise; prod-07 covers the
    # same over-cap branch with split pay on. Cases 01/04/10 also ran with
    # split_pay_available=false in prod, but their outcomes do not depend on the flag
    # (01 and 10 have no overage at all), so they are kept.

    dict(
        id="prod-04-add-ons-not-allowed-no-cap",
        desc="Paid seats not covered on an OPEN-mode event (cap 0). A seat-coverage "
             "violation is emitted while upgrades stay 0, because cap 0 is unlimited "
             "and nothing can be over it. The case that drove both G2 and G3.",
        provenance="ENG-1035:04",
        tags=["prod", "core", "cap", "no-cap", "sentinel", "add-ons", "not-allowed",
              "violation-without-allocation", "core"],
        source={"itinerary_id": "069f3c01-1672-7ab4-8000-75e75bb7f9ac",
                "prod_case": "checkout_04_paid_seats_not_covered"},
        input=cap_input(835.71, 728.39, 107.32, [buyer("pax1", 107.32)],
                        cap=0.0, allowed=False, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE, allowed_classes=["ECONOMY"]),
        expected_override=_out(
            False, 0.0,
            [{"code": "BUYER_COST_NOT_ALLOWED", "status": "REQUIRES_APPROVAL",
              "message": "Out of Policy: Paid Seats: ($107.32) Not Included in Policy"}]),
    ),
    dict(
        id="prod-05-not-included-buyer-split-pay",
        desc="Additional traveler beyond the covered-guest count. The covered pax is "
             "within cap so the company funds it; the additional pax's full fare plus "
             "the 35 ticketing fee shifts to the buyer.",
        provenance="ENG-1035:05",
        tags=["prod", "core", "cap", "not-included", "fee-creates-cost", "core"],
        source={"itinerary_id": "06a6cc47-dfa4-70fe-8000-edbdcad7a496",
                "prod_case": "checkout_05_additional_traveler_split_pay"},
        input=cap_input(1180.80, 1180.80, 0.0,
                        [buyer("pax1"), buyer("pax2", not_included=True)],
                        cap=600.0, allowed=False, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY"]),
        expected_override=_out(
            True, 625.40,
            [{"code": "NOT_INCLUDED", "status": "REQUIRES_USER_CHOICE",
              "message": "1 Additional Traveler(s)"}],
            _alloc(590.40, 0.0, 625.40, 0.0, 1)),
    ),

    # ---------------------------------------------- Complex (06-11)
    dict(
        id="prod-06-class-upgrade-requires-approval",
        desc="Class upgrade with no in-policy benchmark and no enforceable cap. The "
             "engine cannot compute a split, so it clears the summary, turns split pay "
             "off, and routes to approval.",
        provenance="ENG-1035:06",
        tags=["prod", "complex", "class", "not-applicable", "requires-approval",
              "policy-drift", "divergence-G4"],
        source={"itinerary_id": "06a35d42-fd8a-7da8-8000-ab530c043f86",
                "prod_case": "checkout_06_class_upgrade_requires_approval",
                "note": "price_cap pinned to 0.0 from the persisted summary; the "
                        "current policy row shows long_price_cap 500 (edited "
                        "post-booking)."},
        input=class_input(451.76, 451.76, 0.0, [buyer("pax1")],
                          cap=0.0, allowed=False, selected="FIRST",
                          alternates=[("FIRST", 2654.51)],
                          not_incl_fee=TICKETING_FEE, included_count=1, fee_rate=FEE,
                          allowed_classes=["BASIC", "ECONOMY"]),
        expected_override=_out(
            False, 0.0,
            [{"code": "CLASS", "status": "REQUIRES_APPROVAL",
              "message": "Class upgrade requires approval"}]),
    ),
    dict(
        id="prod-07-over-cap-split-pay",
        desc="Cost over cap: fare 848.80 against a 700 cap. Company covers the cap, "
             "buyer covers the 148.80 excess.",
        provenance="ENG-1035:07",
        tags=["prod", "complex", "cap", "over-cap", "core"],
        source={"itinerary_id": "06a74976-3581-7828-8000-ab9b94003075",
                "prod_case": "checkout_07_price_cap_split_pay"},
        input=cap_input(848.80, 848.80, 0.0, [buyer("pax1")],
                        cap=700.0, allowed=False, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(
            True, 148.80,
            [{"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "Booking $148.80 Over Limit"}],
            _alloc(700.0, 0.0, 148.80, 0.0, 1)),
    ),
    dict(
        id="prod-08-long-haul-cap-tier",
        desc="Long-haul tier selection: a 12.8h leg pushes the policy to the long "
             "tier (cap 1500, not the short 750). Tier selection happens UPSTREAM of "
             "the allocator, so here the resolved cap 1500 is simply the input.",
        provenance="ENG-1035:08",
        tags=["prod", "complex", "cap", "over-cap", "upstream-tier-selection"],
        source={"itinerary_id": "06a6d78b-70c7-7cf1-8000-764339a074d3",
                "prod_case": "checkout_08_long_haul_tier",
                "note": "long_price_cap 1500 vs short_price_cap 750; the generic "
                        "function does not own tier selection."},
        input=cap_input(1588.03, 1588.03, 0.0, [buyer("pax1")],
                        cap=1500.0, allowed=False, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["BASIC", "ECONOMY"]),
        expected_override=_out(
            True, 88.03,
            [{"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "Booking $88.03 Over Limit"}],
            _alloc(1500.0, 0.0, 88.03, 0.0, 1)),
    ),
    dict(
        id="prod-09-add-ons-allowed-partial-cap-room",
        desc="Paid seats allowed and partially covered by leftover cap room. Fare "
             "687.52 under the 700 cap leaves 12.48 of room, which the company applies "
             "to the 184.88 seat cost; the buyer covers the remaining 172.40. Exercises "
             "all four buckets at once.",
        provenance="ENG-1035:09",
        tags=["prod", "complex", "cap", "add-ons", "partial-room", "four-buckets", "core"],
        source={"itinerary_id": "06a73eea-9ec4-7db4-8000-fe50c0ee5831",
                "prod_case": "checkout_09_paid_seats_allowed_partial_cap"},
        input=cap_input(872.40, 687.52, 184.88, [buyer("pax1", 184.88)],
                        cap=700.0, allowed=True, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(
            True, 172.40,
            [{"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "Booking $172.40 Over Limit"}],
            _alloc(687.52, 12.48, 0.0, 172.40, 1)),
    ),
    dict(
        id="prod-10-covered-guests-multi-buyer",
        desc="Two travelers, both inside the covered count (1 guest + primary). "
             "Per-pax fare 771.20 under the 800 cap, so both are company-funded and "
             "there is no violation. The contrast case to prod-05.",
        provenance="ENG-1035:10",
        tags=["prod", "complex", "cap", "multi-buyer", "covered-guests",
              "not-applicable", "happy-path"],
        source={"itinerary_id": "06a67c61-c692-7ac3-8000-aa5f3385c3cb",
                "prod_case": "checkout_10_covered_guests_multi_pax"},
        input=cap_input(1542.40, 1542.40, 0.0, [buyer("pax1"), buyer("pax2")],
                        cap=800.0, allowed=False, not_incl_fee=TICKETING_FEE,
                        included_count=2, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(False, 0.0, []),
    ),
    dict(
        id="prod-11-stacked-add-ons-and-over-cap",
        desc="Stacked violations: fare 817.38 over the 700 cap AND a 22.56 paid seat "
             "that policy does not cover. Overage sums both (117.38 + 22.56) and two "
             "violations are emitted.",
        provenance="ENG-1035:11",
        tags=["prod", "complex", "cap", "over-cap", "add-ons", "not-allowed",
              "two-violations", "core"],
        source={"itinerary_id": "06a73436-608b-786d-8000-74d4fbb7fa0a",
                "prod_case": "checkout_11_stacked_seat_and_price_cap"},
        input=cap_input(839.94, 817.38, 22.56, [buyer("pax1", 22.56)],
                        cap=700.0, allowed=False, not_incl_fee=TICKETING_FEE,
                        included_count=1, fee_rate=FEE,
                        allowed_classes=["ECONOMY", "PREMIUM_ECONOMY"]),
        expected_override=_out(
            True, 139.94,
            [{"code": "BUYER_COST_NOT_ALLOWED", "status": "REQUIRES_APPROVAL",
              "message": "Out of Policy: Paid Seats: ($22.56) Not Included in Policy"},
             {"code": "CAP", "status": "REQUIRES_USER_CHOICE",
              "message": "Booking $139.94 Over Limit"}],
            _alloc(700.0, 0.0, 117.38, 22.56, 1)),
    ),
]
