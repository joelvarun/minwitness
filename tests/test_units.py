"""Unit decomposition has to stay faithful to the original program."""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minwitness.units import UnitTree

NESTED = (
    "import math" + chr(10) +
    "def outer():" + chr(10) +
    "    x = 1" + chr(10) +
    "    def inner():" + chr(10) +
    "        nonlocal x" + chr(10) +
    "        x = 2" + chr(10) +
    "    inner()" + chr(10) +
    "    return x" + chr(10) +
    "VALUE = outer()" + chr(10))


class TestUnitTree(unittest.TestCase):
    def setUp(self):
        self.tree = UnitTree(NESTED)

    def test_every_statement_is_a_unit(self):
        parsed = ast.parse(NESTED)
        statements = sum(1 for n in ast.walk(parsed) if isinstance(n, ast.stmt))
        self.assertEqual(self.tree.n, statements)

    def test_full_render_round_trips(self):
        rendered = self.tree.render(self.tree.all_units)
        self.assertEqual(ast.dump(ast.parse(rendered)),
                         ast.dump(ast.parse(ast.unparse(ast.parse(NESTED)))))

    def test_removing_a_parent_removes_its_children(self):
        outer = next(i for i in range(self.tree.n)
                     if isinstance(self.tree.nodes[i], ast.FunctionDef)
                     and self.tree.nodes[i].name == "outer")
        kept = self.tree.close(set(range(self.tree.n)) - {outer})
        for unit in range(self.tree.n):
            if self.tree.up_masks[unit] >> outer & 1 and unit != outer:
                self.assertNotIn(unit, kept)

    def test_ancestor_masks_include_self_and_parents(self):
        for unit in range(self.tree.n):
            self.assertTrue(self.tree.up_masks[unit] >> unit & 1)
            parent = self.tree.parent[unit]
            if parent >= 0:
                self.assertEqual(self.tree.up_masks[unit] & self.tree.up_masks[parent],
                                 self.tree.up_masks[parent])

    def test_empty_body_is_filled_with_pass(self):
        outer = next(i for i in range(self.tree.n)
                     if isinstance(self.tree.nodes[i], ast.FunctionDef)
                     and self.tree.nodes[i].name == "outer")
        kept = {i for i in range(self.tree.n) if self.tree.parent[i] != outer}
        kept = self.tree.close(kept)
        self.assertIn("pass", self.tree.render(kept))

    def test_invalid_reduction_compiles_to_none(self):
        binder = next(i for i in range(self.tree.n)
                      if isinstance(self.tree.nodes[i], ast.Assign)
                      and getattr(self.tree.nodes[i].targets[0], "id", "") == "x"
                      and self.tree.depth[i] == 1)
        kept = self.tree.close(set(range(self.tree.n)) - {binder})
        self.assertIsNone(self.tree.compile_kept(kept))

    def test_tree_is_restored_after_rendering(self):
        before = ast.dump(self.tree.tree)
        self.tree.render(frozenset({0}))
        self.tree.compile_kept(frozenset({0}))
        self.assertEqual(ast.dump(self.tree.tree), before)

    def test_levels_cover_every_unit_once(self):
        seen = [u for level in self.tree.levels() for u in level]
        self.assertEqual(sorted(seen), list(range(self.tree.n)))


if __name__ == "__main__":
    unittest.main()
