"""Constraint store over oracle outcomes, plus the guarded tester.

Two sound rules, both under the monotonicity assumption that every reducer in
the literature already relies on:

  failure  removing R broke the reproduction, so any reproducer keeps at least
           one unit of R. That is a clause.
  success  a kept set K reproduces, so every superset of K reproduces.

A query is *determined* when a clause misses it entirely or a known good set
sits inside it. Determined queries need no oracle call at all, which is a
strict generalisation of the exact result cache every reducer already uses.
"""

import random

from .hittingset import min_hitting_set


def to_mask(units):
    mask = 0
    for unit in units:
        mask |= 1 << unit
    return mask


def to_set(mask):
    out = set()
    index = 0
    while mask:
        if mask & 1:
            out.add(index)
        mask >>= 1
        index += 1
    return out


class ConstraintStore:
    """Minimal clause set and minimal known good set over one universe."""

    def __init__(self, n, expand=None):
        self.n = n
        self.expand = expand
        self.universe = (1 << n) - 1
        self.clauses = []
        self.goods = []
        self.determined_fail = 0
        self.determined_pass = 0

    def predict(self, kept_mask):
        """True, False, or None when the outcome is not yet determined."""
        for clause in self.clauses:
            if clause & kept_mask == 0:
                return False
        for good in self.goods:
            if good & ~kept_mask == 0:
                return True
        return None

    def learn(self, kept_mask, reproduces):
        if reproduces:
            self._add_good(kept_mask)
        else:
            self._add_clause(self.universe & ~kept_mask)

    def _add_clause(self, clause):
        if clause == 0:
            return
        for existing in self.clauses:
            if existing & clause == existing:
                return
        self.clauses = [c for c in self.clauses if c & clause != clause]
        self.clauses.append(clause)

    def _add_good(self, good):
        for existing in self.goods:
            if existing & ~good == 0:
                return
        self.goods = [g for g in self.goods if good & ~g != 0]
        self.goods.append(good)

    def certificate(self, node_limit=200000):
        """Lower bound on the size of any reproducer, with the witness set."""
        return min_hitting_set(self.clauses, expand=self.expand,
                               node_limit=node_limit)


class GuardedTester:
    """Answers reducer queries from the store when possible, else the oracle.

    ``validate_rate`` forces a real oracle call on a random sample of the
    determined queries so the monotonicity assumption is measured rather than
    assumed.
    """

    def __init__(self, oracle, enabled=True, validate_rate=0.0, seed=0,
                 expand=None):
        self.oracle = oracle
        self.store = ConstraintStore(oracle.n, expand=expand)
        self.enabled = enabled
        self.validate_rate = validate_rate
        self.random = random.Random(seed)
        self.queries = 0
        self.skipped = 0
        self.validated = 0
        self.violations = 0
        self.violation_detail = []

    def test_direct(self, kept):
        """Force a real oracle call and record what it says."""
        self.queries += 1
        truth = self.oracle.test(kept)
        self.store.learn(to_mask(kept), truth)
        return truth

    def test(self, kept):
        self.queries += 1
        mask = to_mask(kept)
        guess = self.store.predict(mask) if self.enabled else None
        if guess is not None:
            if self.validate_rate and self.random.random() < self.validate_rate:
                truth = self.oracle.test(kept)
                self.validated += 1
                if truth != guess:
                    self.violations += 1
                    self.violation_detail.append((len(kept), guess, truth))
                self.store.learn(mask, truth)
                return truth
            self.skipped += 1
            if guess:
                self.store.determined_pass += 1
            else:
                self.store.determined_fail += 1
            return guess
        truth = self.oracle.test(kept)
        self.store.learn(mask, truth)
        return truth
