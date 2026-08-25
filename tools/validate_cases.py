#!/usr/bin/env python3
"""
Run a calculator over cases/inputs/ and diff against cases/expected/.

Two modes:

  # self-check the fixtures against the spec-transcribed reference allocator
  python3 tools/validate_cases.py

  # check a real implementation: a command that reads one input JSON on stdin
  # and writes one output JSON on stdout
  python3 tools/validate_cases.py --cmd "docker run --rm -i bucket-calc"
  python3 tools/validate_cases.py --cmd "./my-calculator" --filter cap-

Comparison rules (see cases/manifest.json comparison_notes):
  * Money compared with +/- 0.01 tolerance.
  * Violations compared as a SET of (code, status). Messages are ignored.
  * The `reconciliation` block in expected files is diagnostic and skipped.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from reference_impl import InvalidInput   # noqa: E402

CASES = os.path.join(ROOT, "cases")
TOL = 0.01

MONEY_PATHS = [
    ("allocation", "covered", "item"),
    ("allocation", "covered", "buyer_cost"),
    ("allocation", "owed", "item"),
    ("allocation", "owed", "buyer_cost"),
    ("derived", "covered", "total"),
    ("derived", "owed", "base"),
    ("derived", "owed", "fee"),
    ("derived", "owed", "total"),
]


def dig(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def compare_raise(exp, raised):
    """Grade a case that must fail validation."""
    want = sorted(exp["failures"])
    if raised is None:
        return [f"expected a rejection ({', '.join(want)}), got a normal result"]
    got = sorted(raised.constraints)
    if not got:
        return []          # rejected, but did not name the constraints — accepted
    if got != want:
        return [f"constraints: expected {want}, got {got}"]
    return []


def compare(exp, got):
    diffs = []
    skip = set(exp.get("assert_skip", []))

    if bool(exp["applicable"]) != bool(got.get("applicable")):
        diffs.append(f"applicable: expected {exp['applicable']}, got {got.get('applicable')}")
        return diffs

    e_ov, g_ov = float(exp["overage"]), float(got.get("overage", 0))
    if abs(e_ov - g_ov) > TOL:
        diffs.append(f"overage: expected {e_ov:.2f}, got {g_ov:.2f}")

    if exp["applicable"]:
        if got.get("allocation") is None:
            diffs.append("allocation: expected an allocation, got null")
        else:
            for p in MONEY_PATHS:
                if p[0] in skip:
                    continue
                e, g = dig(exp, p), dig(got, p)
                label = ".".join(p)
                if e is None:
                    continue
                if g is None:
                    diffs.append(f"{label}: missing")
                    continue
                if float(g) < -TOL:
                    diffs.append(f"{label}: negative ({g}) violates O2")
                if abs(float(e) - float(g)) > TOL:
                    diffs.append(f"{label}: expected {float(e):.2f}, got {float(g):.2f}")

            e_n = dig(exp, ("allocation", "covered_buyer_count"))
            g_n = dig(got, ("allocation", "covered_buyer_count"))
            if e_n != g_n:
                diffs.append(f"covered_buyer_count: expected {e_n}, got {g_n}")
    else:
        if got.get("allocation") is not None:
            diffs.append("allocation: expected null (O3), got an allocation")
        if abs(g_ov) > TOL:
            diffs.append(f"overage: expected 0 when not applicable (O3), got {g_ov:.2f}")

    e_v = {(v["code"], v["status"]) for v in exp["violations"]}
    g_v = {(v.get("code"), v.get("status")) for v in got.get("violations", [])}
    if e_v != g_v:
        diffs.append(f"violations: expected {sorted(e_v)}, got {sorted(g_v)}")

    return diffs


class Raised(Exception):
    """The calculator rejected the input. `constraints` is [] if it did not say which."""

    def __init__(self, constraints):
        self.constraints = constraints


def run_external(cmd, payload):
    proc = subprocess.run(cmd, shell=True, input=json.dumps(payload),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        # Non-zero exit means the calculator rejected the input. If it emitted a
        # failure list on either stream, use it; otherwise record the bare rejection.
        ids = []
        for stream in (proc.stdout, proc.stderr):
            try:
                ids = sorted({f["constraint"] if isinstance(f, dict) else f
                              for f in json.loads(stream).get("failures", [])})
            except Exception:
                continue
            if ids:
                break
        raise Raised(ids)
    return json.loads(proc.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", help="command reading input JSON on stdin, writing output JSON on stdout")
    ap.add_argument("--filter", default="", help="only run case ids containing this substring")
    args = ap.parse_args()

    if not args.cmd:
        from reference_impl import allocate

    ids = sorted(os.path.basename(p)[:-5]
                 for p in glob.glob(os.path.join(CASES, "inputs", "*.json")))
    ids = [i for i in ids if args.filter in i]

    failed = errored = xfailed = 0
    for cid in ids:
        with open(os.path.join(CASES, "inputs", f"{cid}.json")) as fh:
            payload = json.load(fh)
        with open(os.path.join(CASES, "expected", f"{cid}.json")) as fh:
            exp = json.load(fh)

        raised = None
        try:
            if args.cmd:
                got = run_external(args.cmd, payload)
            else:
                r = allocate(payload)
                r.pop("_reconciliation", None)
                r["violations"] = [{"code": c, "status": s, "message": m}
                                   for c, s, m in r["violations"]]
                got = r
        except Raised as exc:
            got, raised = None, exc
        except InvalidInput as exc:
            got, raised = None, SimpleNamespace(constraints=exc.constraints)
        except Exception as exc:
            print(f"ERROR {cid}\n       {exc}")
            errored += 1
            continue

        if exp.get("raises"):
            diffs = compare_raise(exp, raised)
            if diffs:
                failed += 1
                print(f"FAIL  {cid}")
                for d in diffs:
                    print(f"       {d}")
            else:
                print(f"ok    {cid}  (rejected: {', '.join(exp['failures'])})")
            continue

        if raised is not None:
            failed += 1
            print(f"FAIL  {cid}\n       unexpected rejection "
                  f"({', '.join(raised.constraints) or 'no constraints named'})")
            continue

        diffs = compare(exp, got)
        known = exp.get("divergence_from_spec")
        if diffs and known and not args.cmd:
            # Running the spec reference against a fixed expectation the spec
            # provably cannot satisfy. Expected, not a regression.
            xfailed += 1
            print(f"xfail {cid}  (known spec divergence)")
            for d in known:
                print(f"       {d}")
        elif diffs:
            failed += 1
            print(f"FAIL  {cid}" + ("  [expected output diverges from spec]" if known else ""))
            for d in diffs:
                print(f"       {d}")
        else:
            print(f"ok    {cid}")

    total = len(ids)
    print(f"\n{total - failed - errored - xfailed}/{total} passed"
          + (f", {xfailed} xfail (fixed expectation disagrees with the spec)" if xfailed else "")
          + (f", {failed} failed" if failed else "")
          + (f", {errored} errored" if errored else ""))
    return 1 if (failed or errored) else 0


if __name__ == "__main__":
    sys.exit(main())
