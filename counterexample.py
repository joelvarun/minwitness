"""Search for the sharpest possible refutation of the monotonicity assumption.

Delta debugging theory, and every reducer that learns from failures, assumes
that adding statements back to a reproducing program cannot stop it from
reproducing. This script takes the reduced witness and puts single statements
back, one at a time, against a fresh oracle. Any statement that breaks the
reproduction is a one statement counterexample: strictly more code, strictly
less reproduction.

    python counterexample.py                 every subject
    python counterexample.py base64 copy     a chosen few
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minwitness import UnitTree, Oracle, GuardedTester, Task, run
from minwitness.monotone import describe_unit, single_statement_breaks
from minwitness.subjects import load


def main():
    wanted = sys.argv[1:] or None
    total = 0
    for name, module, probe, kind, text in load(wanted):
        tree = UnitTree(text)
        oracle = Oracle(text, "m_" + module, probe)
        tester = GuardedTester(oracle, enabled=True,
                               expand=lambda e: tree.up_masks[e])
        witness = run("ddmin", Task(tree, tester))
        oracle.reset()
        breakers = single_statement_breaks(tree, oracle, witness)
        print("%-16s witness=%3d of %3d   one statement breakers: %d"
              % (name, len(witness), tree.n, len(breakers)), flush=True)
        for unit in breakers[:2]:
            print("    adding  %s" % describe_unit(tree, unit)[:88], flush=True)
            print("    makes the %d statement program stop reproducing %s"
                  % (len(witness) + 1, oracle.reference[:40]), flush=True)
        total += len(breakers)
        oracle.close()
    print("")
    print("one statement monotonicity counterexamples found: %d" % total)


if __name__ == "__main__":
    main()
