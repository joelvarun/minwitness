"""Decompose a Python module into removable AST units.

A unit is a single ``ast.stmt``. Removing a unit removes its whole subtree, so
the set of kept units is always downward closed from the module root. Rendering
mutates the shared tree in place and restores it afterwards, which avoids a
deepcopy (17.7 ms on a 271 statement module) per oracle call.
"""

import ast

BODY_FIELDS = ("body", "orelse", "finalbody")


class UnitTree:
    """An indexed, prunable view of one module's abstract syntax tree."""

    def __init__(self, source, filename="<reduced>"):
        self.source = source
        self.filename = filename
        self.tree = ast.parse(source, filename)
        self.nodes = []
        self.parent = []
        self.depth = []
        self.children = []
        self._slots = []
        self._index(self.tree, parent=-1, depth=0)
        self.n = len(self.nodes)
        self.all_units = frozenset(range(self.n))
        self.up_masks = []
        for uid in range(self.n):
            mask = 1 << uid
            p = self.parent[uid]
            if p >= 0:
                mask |= self.up_masks[p]
            self.up_masks.append(mask)

    def _index(self, holder, parent, depth):
        for field in BODY_FIELDS:
            seq = getattr(holder, field, None)
            if not isinstance(seq, list) or not seq:
                continue
            for stmt in seq:
                uid = len(self.nodes)
                stmt._uid = uid
                self.nodes.append(stmt)
                self.parent.append(parent)
                self.depth.append(depth)
                self.children.append([])
                if parent >= 0:
                    self.children[parent].append(uid)
            filler = ast.Pass()
            filler.lineno = seq[0].lineno
            filler.col_offset = seq[0].col_offset
            filler.end_lineno = seq[0].lineno
            filler.end_col_offset = seq[0].col_offset + 4
            self._slots.append((holder, field, list(seq), filler))
            for stmt in seq:
                self._index(stmt, stmt._uid, depth + 1)
        for handler in getattr(holder, "handlers", []) or []:
            self._index(handler, parent, depth)

    def close(self, kept):
        """Drop every unit whose ancestor chain is not fully present."""
        kept = set(kept)
        out = set()
        for uid in range(self.n):
            if uid not in kept:
                continue
            p = self.parent[uid]
            if p == -1 or p in out:
                out.add(uid)
        return frozenset(out)

    def _apply(self, kept):
        for holder, field, original, filler in self._slots:
            new = [stmt for stmt in original if stmt._uid in kept]
            if not new:
                if field == "body":
                    new = [filler]
                elif field == "finalbody" and not getattr(holder, "handlers", None):
                    new = [filler]
            setattr(holder, field, new)

    def _restore(self):
        for holder, field, original, _filler in self._slots:
            setattr(holder, field, original)

    def compile_kept(self, kept):
        """Compile the module restricted to ``kept``; None if it is not valid."""
        self._apply(kept)
        try:
            return compile(self.tree, self.filename, "exec")
        except (SyntaxError, ValueError, TypeError):
            return None
        finally:
            self._restore()

    def render(self, kept):
        """Unparse the module restricted to ``kept`` back to source text."""
        self._apply(kept)
        try:
            return ast.unparse(self.tree)
        finally:
            self._restore()

    def levels(self):
        """Unit ids grouped by tree depth, shallowest first (used by HDD)."""
        by_depth = {}
        for uid in range(self.n):
            by_depth.setdefault(self.depth[uid], []).append(uid)
        return [by_depth[d] for d in sorted(by_depth)]
