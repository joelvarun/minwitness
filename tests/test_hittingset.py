"""The certificate is only worth shipping if the solver is exact."""

import itertools
import random
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minwitness.hittingset import min_hitting_set, packing_bound, reduce_clauses


def brute_force(clauses, n, up=None):
    for size in range(n + 1):
        for combo in itertools.combinations(range(n), size):
            mask = 0
            for element in combo:
                mask |= 1 << element
            if up is not None and any(up[e] & ~mask for e in combo):
                continue
            if all(clause & mask for clause in clauses):
                return size
    return None


class TestHittingSet(unittest.TestCase):
    def test_matches_brute_force_flat(self):
        rng = random.Random(1)
        for _ in range(250):
            n = rng.randint(3, 11)
            clauses = [rng.getrandbits(n) | (1 << rng.randrange(n))
                       for _ in range(rng.randint(1, 7))]
            result = min_hitting_set(clauses)
            self.assertTrue(result["exact"])
            self.assertEqual(result["size"], brute_force(clauses, n))
            self.assertEqual(result["bound"], result["size"])

    def test_matches_brute_force_closed(self):
        rng = random.Random(2)
        for _ in range(250):
            n = rng.randint(3, 11)
            parent = [-1] * n
            for i in range(1, n):
                parent[i] = rng.choice([-1] + list(range(i)))
            up = []
            for i in range(n):
                mask, cursor = 0, i
                while cursor != -1:
                    mask |= 1 << cursor
                    cursor = parent[cursor]
                up.append(mask)
            clauses = [rng.getrandbits(n) | (1 << rng.randrange(n))
                       for _ in range(rng.randint(1, 6))]
            result = min_hitting_set(clauses, expand=lambda e: up[e])
            self.assertTrue(result["exact"])
            self.assertEqual(result["size"], brute_force(clauses, n, up))

    def test_witness_really_hits_every_clause(self):
        rng = random.Random(3)
        for _ in range(200):
            n = rng.randint(4, 14)
            clauses = [rng.getrandbits(n) | (1 << rng.randrange(n))
                       for _ in range(rng.randint(1, 9))]
            result = min_hitting_set(clauses)
            for clause in clauses:
                self.assertTrue(clause & result["witness"])

    def test_packing_is_a_lower_bound(self):
        rng = random.Random(4)
        for _ in range(200):
            n = rng.randint(3, 10)
            clauses = sorted({rng.getrandbits(n) | (1 << rng.randrange(n))
                              for _ in range(rng.randint(1, 6))}, key=int.bit_count)
            self.assertLessEqual(packing_bound(clauses), brute_force(clauses, n))

    def test_subsumed_clauses_are_dropped(self):
        self.assertEqual(reduce_clauses([0b1110, 0b0010, 0b1111]), [0b0010])

    def test_empty_clause_is_unsatisfiable(self):
        self.assertIsNone(reduce_clauses([0b101, 0]))
        self.assertTrue(min_hitting_set([0b101, 0])["infeasible"])


if __name__ == "__main__":
    unittest.main()
