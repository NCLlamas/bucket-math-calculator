#!/usr/bin/env python3
"""
Emit the validation fixtures from tools/case_table.py.

  cases/inputs/<id>.json    - bare BucketCalculationInput, nothing else. A container
                              can glob this directory and feed each file straight in.
  cases/expected/<id>.json  - expected BucketCalculationOutput for the same <id>.
  cases/input-index.json    - ordered id list + metadata for the input side alone.
  cases/manifest.json       - the linked view: id -> input path, expected path, tags.

Inputs and expectations are joined by FILENAME. Neither file embeds a pointer to
the other, so either directory is usable on its own.

Usage:  python3 tools/generate_cases.py
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from case_table import CASES as SPEC_CASES        # noqa: E402
from case_table_scenarios import CASES as SCENARIO_CASES  # noqa: E402
from case_table_invalid import CASES as INVALID_CASES     # noqa: E402
from reference_impl import allocate, InvalidInput, CLASS_RANKS  # noqa: E402

CASES = SPEC_CASES + SCENARIO_CASES + INVALID_CASES

CASES_DIR = os.path.join(ROOT, "cases")
IN_DIR = os.path.join(CASES_DIR, "inputs")
EXP_DIR = os.path.join(CASES_DIR, "expected")
TOLERANCE = 0.01


def to_expected(result):
    """Shape the reference result into the documented output structure."""
    recon = result.pop("_reconciliation", None)
    out = {
        "applicable": result["applicable"],
        "allocation": result["allocation"],
        "derived": result["derived"],
        "overage": result["overage"],
        "violations": [
            {"code": c, "status": s, "message": m} for c, s, m in result["violations"]
        ],
    }
    if recon is not None:
        out["reconciliation"] = recon
    return out


MONEY_PATHS = [
    ("allocation", "covered", "item"),
    ("allocation", "covered", "buyer_cost"),
    ("allocation", "owed", "item"),
    ("allocation", "owed", "buyer_cost"),
]


def _dig(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def divergence(fixed, ref):
    """Differences between a fixed expected output and the spec reference."""
    diffs = []

    if bool(fixed["applicable"]) != bool(ref["applicable"]):
        diffs.append(f"applicable: fixture {fixed['applicable']}, spec {ref['applicable']}")

    if abs(float(fixed["overage"]) - float(ref["overage"])) > TOLERANCE:
        diffs.append(f"overage: fixture {float(fixed['overage']):.2f}, "
                     f"spec {float(ref['overage']):.2f}")

    if fixed["allocation"] is None and ref["allocation"] is not None:
        diffs.append("allocation: fixture null (no split), spec produced buckets "
                     f"covered.item={_dig(ref, ('allocation','covered','item'))} "
                     f"owed.item={_dig(ref, ('allocation','owed','item'))} "
                     f"owed.buyer_cost={_dig(ref, ('allocation','owed','buyer_cost'))}")
    elif fixed["allocation"] is not None and ref["allocation"] is None:
        diffs.append("allocation: fixture produced buckets, spec returned null")
    elif fixed["allocation"] is not None:
        for path in MONEY_PATHS:
            a, b = _dig(fixed, path), _dig(ref, path)
            if a is None or b is None:
                continue
            if abs(float(a) - float(b)) > TOLERANCE:
                diffs.append(f"{'.'.join(path)}: fixture {float(a):.2f}, spec {float(b):.2f}")

    f_v = {(v["code"], v["status"]) for v in fixed["violations"]}
    r_v = {(v["code"], v["status"]) for v in ref["violations"]}
    if f_v != r_v:
        only_fixture = sorted(f_v - r_v)
        only_spec = sorted(r_v - f_v)
        parts = []
        if only_fixture:
            parts.append(f"fixture-only {only_fixture}")
        if only_spec:
            parts.append(f"spec-only {only_spec}")
        diffs.append("violations: " + "; ".join(parts))

    return diffs


def main():
    os.makedirs(IN_DIR, exist_ok=True)
    os.makedirs(EXP_DIR, exist_ok=True)

    seen = set()
    manifest_cases = []
    input_index = []
    divergences = {}

    for case in CASES:
        cid = case["id"]
        if cid in seen:
            raise SystemExit(f"duplicate case id: {cid}")
        seen.add(cid)

        inp = case["input"]

        if case.get("expects_raise"):
            try:
                allocate(inp)
            except InvalidInput as exc:
                actual = exc.constraints
            else:
                raise SystemExit(f"{cid}: expected a raise, but validation passed")
            declared = sorted(case["expects_raise"])
            if actual != declared:
                raise SystemExit(f"{cid}: declared {declared}, reference raised {actual}")
            expected = {
                "raises": True,
                "failures": actual,
                "note": case.get("silent_damage"),
            }
            with open(os.path.join(IN_DIR, f"{cid}.json"), "w") as fh:
                json.dump(inp, fh, indent=2); fh.write("\n")
            with open(os.path.join(EXP_DIR, f"{cid}.json"), "w") as fh:
                json.dump(expected, fh, indent=2); fh.write("\n")
            common = {"id": cid, "mode": inp.get("mode"), "description": case["desc"],
                      "provenance": case["provenance"], "tags": case["tags"]}
            input_index.append({**common, "input": f"inputs/{cid}.json"})
            manifest_cases.append({**common, "input": f"inputs/{cid}.json",
                                   "expected": f"expected/{cid}.json",
                                   "expected_from": "constraint",
                                   "raises": True, "failures": actual})
            continue

        reference = to_expected(allocate(inp))

        override = case.get("expected_override")
        if override is None:
            expected = reference
            diffs = []
        else:
            # The fixed expected output is authoritative; record how the spec differs.
            expected = dict(override)
            diffs = divergence(expected, reference)
            if diffs:
                expected["divergence_from_spec"] = diffs
        if "source" in case:
            expected["source"] = case["source"]

        with open(os.path.join(IN_DIR, f"{cid}.json"), "w") as fh:
            json.dump(inp, fh, indent=2)
            fh.write("\n")
        with open(os.path.join(EXP_DIR, f"{cid}.json"), "w") as fh:
            json.dump(expected, fh, indent=2)
            fh.write("\n")

        common = {
            "id": cid,
            "mode": inp["mode"],
            "description": case["desc"],
            "provenance": case["provenance"],
            "tags": case["tags"],
        }
        if "source" in case:
            common["source"] = case["source"]
        input_index.append({**common, "input": f"inputs/{cid}.json"})
        manifest_cases.append({
            **common,
            "input": f"inputs/{cid}.json",
            "expected": f"expected/{cid}.json",
            "applicable": expected["applicable"],
            "violation_codes": [v["code"] for v in expected["violations"]],
            "expected_from": "fixed" if override else "derived",
            "diverges_from_spec": bool(diffs),
        })
        if diffs:
            divergences[cid] = diffs

    # Spec R1: every Class in a case must be rankable, and a deployment configures
    # ONE class set. The two sets here are disjoint and no case may mix them.
    tier = {k for k in CLASS_RANKS if k.startswith("TIER_")}
    ladder = set(CLASS_RANKS) - tier
    for case in CASES:
        if case.get("expects_raise"):
            continue
        inp = case["input"]
        used = set(inp["policy"]["allowed_classes"])
        ctx = inp.get("upgrade_context")
        if ctx:
            used.add(ctx["selected_class"])
            used |= {o["class"] for o in ctx["alternate_classes"]}
        unknown = used - set(CLASS_RANKS)
        if unknown:
            raise SystemExit(f"{case['id']}: unrankable class(es) {sorted(unknown)} (C7/R1)")
        if used & tier and used & ladder:
            raise SystemExit(f"{case['id']}: mixes two class sets {sorted(used)}")

    # Remove fixtures for cases that no longer exist in the tables.
    for d in (IN_DIR, EXP_DIR):
        for path in glob.glob(os.path.join(d, "*.json")):
            if os.path.basename(path)[:-5] not in seen:
                os.remove(path)
                print(f"removed stale fixture {os.path.relpath(path, ROOT)}")

    with open(os.path.join(CASES_DIR, "input-index.json"), "w") as fh:
        json.dump({
            "purpose": "Input side only. Enumerate and feed these into the calculator "
                       "without needing cases/expected/.",
            "join_key": "filename stem == case id",
            "class_ranks": CLASS_RANKS,
            "count": len(input_index),
            "cases": input_index,
        }, fh, indent=2)
        fh.write("\n")

    with open(os.path.join(CASES_DIR, "manifest.json"), "w") as fh:
        json.dump({
            "purpose": "Linked view of the suite: every case's input and expected output.",
            "spec": "bucket-calculations-spec.md",
            "join_key": "filename stem == case id",
            "money_tolerance": TOLERANCE,
            "invalid_case_note": "Cases whose expected output has `raises: true` must "
                                 "fail validation. Compare the SET of `failures` "
                                 "constraint ids; messages are informational.",
            "class_ranks": CLASS_RANKS,
            "divergences_from_spec": divergences,
            "comparison_notes": [
                "Compare violations on (code, status) as a set. `message` is "
                "informational -- exact wording is not specified.",
                "Compare all Money fields with the tolerance above, not exact equality.",
                "`reconciliation` is a diagnostic block, not part of the output "
                "contract. See README Findings F1.",
            ],
            "count": len(manifest_cases),
            "cases": manifest_cases,
        }, fh, indent=2)
        fh.write("\n")

    print(f"wrote {len(manifest_cases)} cases -> cases/inputs/, cases/expected/")
    if divergences:
        print(f"{len(divergences)} case(s) where a fixed expectation disagrees with the spec:")
        for cid, ds in divergences.items():
            print(f"  {cid}")
            for d in ds:
                print(f"    - {d}")


if __name__ == "__main__":
    main()
