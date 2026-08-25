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
from case_table_prod import CASES as PROD_CASES   # noqa: E402
from reference_impl import allocate, CLASS_RANKS   # noqa: E402

CASES = SPEC_CASES + PROD_CASES

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


def divergence(prod, ref):
    """Differences between the transcribed production output and the spec reference."""
    diffs = []

    if bool(prod["applicable"]) != bool(ref["applicable"]):
        diffs.append(f"applicable: prod {prod['applicable']}, spec {ref['applicable']}")

    if abs(float(prod["overage"]) - float(ref["overage"])) > TOLERANCE:
        diffs.append(f"overage: prod {float(prod['overage']):.2f}, "
                     f"spec {float(ref['overage']):.2f}")

    if prod["allocation"] is None and ref["allocation"] is not None:
        diffs.append("allocation: prod null (no split produced), spec produced buckets "
                     f"covered.item={_dig(ref, ('allocation','covered','item'))} "
                     f"owed.item={_dig(ref, ('allocation','owed','item'))} "
                     f"owed.buyer_cost={_dig(ref, ('allocation','owed','buyer_cost'))}")
    elif prod["allocation"] is not None and ref["allocation"] is None:
        diffs.append("allocation: prod produced buckets, spec returned null")
    elif prod["allocation"] is not None:
        for path in MONEY_PATHS:
            a, b = _dig(prod, path), _dig(ref, path)
            if a is None or b is None:
                continue
            if abs(float(a) - float(b)) > TOLERANCE:
                diffs.append(f"{'.'.join(path)}: prod {float(a):.2f}, spec {float(b):.2f}")

    p_v = {(v["code"], v["status"]) for v in prod["violations"]}
    r_v = {(v["code"], v["status"]) for v in ref["violations"]}
    if p_v != r_v:
        only_prod = sorted(p_v - r_v)
        only_spec = sorted(r_v - p_v)
        parts = []
        if only_prod:
            parts.append(f"prod-only {only_prod}")
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
        reference = to_expected(allocate(inp))

        override = case.get("expected_override")
        if override is None:
            expected = reference
            diffs = []
        else:
            # Production output is authoritative; record how the spec differs.
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
            "expected_from": "production (ENG-1035)" if override else "spec reference",
            "diverges_from_spec": bool(diffs),
        })
        if diffs:
            divergences[cid] = diffs

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
        print(f"{len(divergences)} case(s) where production disagrees with the spec:")
        for cid, ds in divergences.items():
            print(f"  {cid}")
            for d in ds:
                print(f"    - {d}")


if __name__ == "__main__":
    main()
