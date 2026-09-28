"""Run the full measurement and write docs/metrics.json.

Every number in the README and in the chart comes from this script. Nothing is
simulated: each oracle call really compiles a reduced copy of a real CPython
standard library module and really runs the probe against it.

Usage:
    python demo.py                      all subjects, writes docs/metrics.json
    python demo.py --subjects shlex csv  a chosen few, writes docs/metrics.json
    python demo.py --dry                 print only, never touch metrics.json
"""

import argparse
import datetime
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minwitness import UnitTree, Oracle, GuardedTester, Task, run
from minwitness.certify import certify
from minwitness.monotone import audit, describe_unit, single_statement_breaks
from minwitness.report import portfolio
from minwitness.subjects import load

METHODS = [("ddmin", False), ("ddmin", True), ("hdd", False), ("hdd", True),
           ("probdd", False), ("probdd", True)]
VALIDATE_RATE = 0.30


def key_of(algo, guarded):
    return algo + ("+store" if guarded else "")


def measure(tree, oracle, algo, guarded, validate_rate=0.0):
    """One reduction plus certification, with every oracle call counted."""
    oracle.reset()
    tester = GuardedTester(oracle, enabled=guarded, validate_rate=validate_rate,
                           expand=lambda e: tree.up_masks[e])
    task = Task(tree, tester)
    started = time.perf_counter()
    witness = run(algo, task)
    reduce_calls = oracle.calls
    witness, certificate, jumps = certify(task, witness)
    elapsed = time.perf_counter() - started
    record = {
        "calls": oracle.calls,
        "reduce_calls": reduce_calls,
        "certify_calls": oracle.calls - reduce_calls,
        "determined": tester.skipped,
        "witness_units": len(witness),
        "bound": certificate["bound"],
        "bound_exact": certificate["exact"],
        "certified_minimal": (certificate["exact"]
                              and certificate["bound"] == len(witness)),
        "jumps": jumps["jumps"],
        "improved": jumps["improved"],
        "seconds": round(elapsed, 2),
        "timeouts": oracle.timeouts,
    }
    return record, task, witness, certificate


def run_subject(name, module, probe, kind, source):
    tree = UnitTree(source)
    oracle = Oracle(source, "m_" + module, probe)
    entry = {
        "name": name, "module": module, "probe": probe, "kind": kind,
        "units": tree.n, "source_lines": source.count(chr(10)) + 1,
        "reference": oracle.reference, "methods": {},
    }
    try:
        for algo, guarded in METHODS:
            record, task, witness, certificate = measure(tree, oracle, algo, guarded)
            entry["methods"][key_of(algo, guarded)] = record
            print("  %-13s calls=%5d witness=%3d bound=%3d %s %5.1fs" % (
                key_of(algo, guarded), record["calls"], record["witness_units"],
                record["bound"],
                "CERTIFIED" if record["certified_minimal"] else "",
                record["seconds"]), flush=True)
            if algo == "ddmin" and guarded:
                entry["witness_source"] = tree.render(witness)
                entry["audit"] = audit(task, witness, certificate)
                shipped = set(witness)

        record, task, witness, certificate = measure(
            tree, oracle, "ddmin", True, validate_rate=VALIDATE_RATE)
        tester = task.tester
        entry["validation"] = {
            "rate": VALIDATE_RATE,
            "checked": tester.validated,
            "violations": tester.violations,
            "calls": record["calls"],
        }
        print("  validation    checked=%d violations=%d" % (
            tester.validated, tester.violations), flush=True)

        oracle.reset()
        breakers = single_statement_breaks(tree, oracle, shipped)
        entry["monotone_probe"] = {
            "witness_units": len(shipped),
            "breakers": len(breakers),
            "calls": oracle.calls,
            "examples": [describe_unit(tree, unit) for unit in breakers[:3]],
        }
        print("  add-one probe breakers=%d in %d calls" % (
            len(breakers), oracle.calls), flush=True)
    finally:
        oracle.close()
    return entry


def summarise(subjects):
    """Portfolio level totals used by the README headline."""
    totals = {}
    for algo, guarded in METHODS:
        name = key_of(algo, guarded)
        totals[name] = sum(s["methods"][name]["calls"] for s in subjects)
    certified = sum(1 for s in subjects
                    if s["methods"]["ddmin+store"]["certified_minimal"])
    refuting = sum(1 for s in subjects if s["audit"]["self_refuting"])
    proven = sum(1 for s in subjects if s["audit"]["counterexamples"])
    verdicts = portfolio(subjects)
    breakers = sum(s["monotone_probe"]["breakers"] for s in subjects)
    broken = sum(1 for s in subjects if s["monotone_probe"]["breakers"])
    checked = sum(s["validation"]["checked"] for s in subjects)
    violations = sum(s["validation"]["violations"] for s in subjects)
    return {
        "calls": totals,
        "speedup_ddmin": round(totals["ddmin"] / max(totals["ddmin+store"], 1), 3),
        "subjects": len(subjects),
        "certified_minimal": certified,
        "proved_minimal": verdicts["proved_minimal"],
        "monotone_broken": verdicts["monotone_broken"],
        "undecided": verdicts["undecided"],
        "witness_agrees": verdicts["witness_agrees"],
        "add_one_breakers": breakers,
        "add_one_broken_subjects": broken,
        "monotone_subjects": len(subjects) - broken,
        "self_refuting": refuting,
        "counterexample_proven": proven,
        "validation_checked": checked,
        "validation_violations": violations,
        "validation_violation_rate": round(violations / max(checked, 1), 4),
        "original_units": sum(s["units"] for s in subjects),
        "witness_units": sum(s["methods"]["ddmin+store"]["witness_units"]
                             for s in subjects),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="*", default=None)
    parser.add_argument("--dry", action="store_true",
                        help="print results without writing docs/metrics.json")
    args = parser.parse_args()

    started = time.perf_counter()
    subjects = []
    for name, module, probe, kind, source in load(args.subjects):
        print("%s (%s)" % (name, module), flush=True)
        subjects.append(run_subject(name, module, probe, kind, source))

    report = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "validate_rate": VALIDATE_RATE,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "subjects": subjects,
        "summary": summarise(subjects),
    }
    print(json.dumps(report["summary"], indent=2), flush=True)
    if args.dry:
        print("dry run, docs/metrics.json untouched", flush=True)
        return
    if args.subjects is not None:
        print("partial subject list, docs/metrics.json untouched", flush=True)
        return
    os.makedirs("docs", exist_ok=True)
    with open(os.path.join("docs", "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("wrote docs/metrics.json", flush=True)


if __name__ == "__main__":
    main()
