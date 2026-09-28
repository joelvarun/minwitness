"""Reducer and constraint store behaviour against oracles we control.

On a monotone oracle the constraint store must never change an answer, and the
certificate must prove the exact minimum. On a non monotone one the harness
must notice rather than quietly report a wrong bound.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minwitness.certify import certify
from minwitness.monotone import is_self_refuting
from minwitness.reducers import REDUCERS, Task, run, enforce_1_minimal
from minwitness.store import GuardedTester


class FlatTree:
    """A unit tree with no nesting, so closure is the identity."""

    def __init__(self, n):
        self.n = n
        self.up_masks = [1 << i for i in range(n)]

    def close(self, kept):
        return frozenset(kept)

    def levels(self):
        return [list(range(self.n))]


class MonotoneOracle:
    """Reproduces exactly when every required unit is present."""

    def __init__(self, n, required):
        self.n = n
        self.required = frozenset(required)
        self.calls = 0

    def test(self, kept):
        self.calls += 1
        return self.required <= frozenset(kept)


class TwoWitnessOracle:
    """Reproduces for one large set or one unrelated small set. Not monotone."""

    def __init__(self, n, required, alternative):
        self.n = n
        self.required = frozenset(required)
        self.alternative = frozenset(alternative)
        self.calls = 0

    def test(self, kept):
        self.calls += 1
        kept = frozenset(kept)
        return self.required <= kept or kept == self.alternative


def build(oracle, enabled, validate_rate=0.0):
    tree = FlatTree(oracle.n)
    tester = GuardedTester(oracle, enabled=enabled, validate_rate=validate_rate,
                           expand=lambda e: tree.up_masks[e])
    return Task(tree, tester)


class TestReducers(unittest.TestCase):
    REQUIRED = {2, 5, 9, 14}
    N = 20

    def test_every_reducer_finds_the_required_set(self):
        for name in REDUCERS:
            for guarded in (False, True):
                oracle = MonotoneOracle(self.N, self.REQUIRED)
                witness = run(name, build(oracle, guarded))
                self.assertEqual(set(witness), self.REQUIRED, name)

    def test_results_are_1_minimal(self):
        for name in REDUCERS:
            oracle = MonotoneOracle(self.N, self.REQUIRED)
            task = build(oracle, True)
            witness = run(name, task)
            for unit in witness:
                self.assertFalse(oracle.test(set(witness) - {unit}))

    def test_store_never_contradicts_a_monotone_oracle(self):
        for name in REDUCERS:
            oracle = MonotoneOracle(self.N, self.REQUIRED)
            task = build(oracle, True, validate_rate=1.0)
            run(name, task)
            self.assertEqual(task.tester.violations, 0, name)
            self.assertGreater(task.tester.queries, 0)

    def test_store_saves_oracle_calls(self):
        plain = MonotoneOracle(self.N, self.REQUIRED)
        run("ddmin", build(plain, False))
        guarded = MonotoneOracle(self.N, self.REQUIRED)
        run("ddmin", build(guarded, True))
        self.assertLess(guarded.calls, plain.calls)

    def test_certificate_proves_the_true_minimum(self):
        oracle = MonotoneOracle(self.N, self.REQUIRED)
        task = build(oracle, True)
        witness = run("ddmin", task)
        witness, certificate, _ = certify(task, witness)
        self.assertTrue(certificate["exact"])
        self.assertEqual(certificate["bound"], len(self.REQUIRED))
        self.assertEqual(len(witness), len(self.REQUIRED))
        self.assertFalse(is_self_refuting(certificate, witness))

    def test_bound_never_exceeds_witness_on_a_monotone_oracle(self):
        for name in REDUCERS:
            oracle = MonotoneOracle(self.N, self.REQUIRED)
            task = build(oracle, True)
            witness, certificate, _ = certify(task, run(name, task))
            self.assertLessEqual(certificate["bound"], len(witness), name)

    def test_non_monotone_oracle_is_detected(self):
        oracle = TwoWitnessOracle(self.N, self.REQUIRED, {0, 1})
        task = build(oracle, True, validate_rate=1.0)
        witness = run("ddmin", task)
        witness, certificate, _ = certify(task, witness)
        flagged = (is_self_refuting(certificate, witness)
                   or task.tester.violations > 0
                   or certificate["bound"] < len(witness))
        self.assertTrue(flagged)

    def test_verified_pass_ignores_a_poisoned_store(self):
        oracle = MonotoneOracle(self.N, self.REQUIRED)
        task = build(oracle, True)
        task.tester.store.clauses.append(1 << 19)
        witness = enforce_1_minimal(task, frozenset(range(self.N)),
                                    trust_store=False)
        self.assertEqual(set(witness), self.REQUIRED)


if __name__ == "__main__":
    unittest.main()
