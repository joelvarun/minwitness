"""Reduce one module against one probe and print the certified result.

Examples:
    python reduce.py --module shlex --probe "M.split('one two')"
    python reduce.py --module fractions --probe "M.Fraction('1/0')" --reducer probdd
    python reduce.py --module colorsys --probe "M.rgb_to_hsv(0.2, 0.4, 0.4)" --source out.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minwitness import UnitTree, Oracle, GuardedTester, Task, run, REDUCERS
from minwitness.certify import certify
from minwitness.monotone import audit
from minwitness.subjects import source_of


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True,
                        help="a pure Python module on the stdlib path")
    parser.add_argument("--probe", required=True,
                        help="expression over M, the reduced module")
    parser.add_argument("--reducer", default="ddmin", choices=sorted(REDUCERS))
    parser.add_argument("--no-store", action="store_true",
                        help="disable the constraint store and call the oracle for everything")
    parser.add_argument("--source", help="write the reduced program to this path")
    args = parser.parse_args()

    text = source_of(args.module)
    tree = UnitTree(text)
    oracle = Oracle(text, "m_" + args.module, args.probe)
    print("module     %s (%d statements)" % (args.module, tree.n))
    print("probe      %s" % args.probe)
    print("reference  %s" % oracle.reference)
    if oracle.reference.startswith(("X", "B", "T")):
        print("the probe does not run against the unreduced module, nothing to reduce")
        oracle.close()
        return 1

    tester = GuardedTester(oracle, enabled=not args.no_store,
                           expand=lambda e: tree.up_masks[e])
    task = Task(tree, tester)
    witness = run(args.reducer, task)
    reduce_calls = oracle.calls
    witness, certificate, jumps = certify(task, witness)
    report = audit(task, witness, certificate)

    print("")
    print("witness    %d of %d statements (%.1f%% removed)" % (
        len(witness), tree.n, 100.0 * (tree.n - len(witness)) / tree.n))
    print("oracle     %d calls (%d reducing, %d certifying), %d answered by the store"
          % (oracle.calls, reduce_calls, oracle.calls - reduce_calls, tester.skipped))
    if certificate["exact"] and certificate["bound"] == len(witness):
        print("certificate  PROVED MINIMAL: no reproducing program has fewer than "
              "%d statements" % certificate["bound"])
    elif report["self_refuting"]:
        print("certificate  WITHDRAWN: bound %d exceeds the %d statement witness, so this "
              "program is not monotone" % (certificate["bound"], len(witness)))
        for case in report["counterexamples"]:
            print("             counterexample: a %d statement superset of the witness "
                  "does not reproduce" % case["superset_units"])
    else:
        print("certificate  lower bound %d, witness %d, gap %d statements" % (
            certificate["bound"], len(witness), len(witness) - certificate["bound"]))

    text_out = tree.render(witness)
    if args.source:
        with open(args.source, "w", encoding="utf-8") as handle:
            handle.write(text_out + chr(10))
        print("wrote " + args.source)
    else:
        print("")
        print(text_out)
    oracle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
