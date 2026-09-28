"""Exact minimum hitting set over bitmask clauses, with structural expansion.

Every failed oracle call says "at least one of these units must be kept", which
is a clause. Any set of units that still reproduces has to hit every clause, so
the smallest hitting set is a lower bound on the size of any reproducer. That
bound is the certificate this project ships; no other reducer reports one.

Kept sets are downward closed in the syntax tree: keeping a statement means
keeping every statement that encloses it. Passing ``expand`` (unit -> mask of
that unit plus its ancestors) makes the solver respect that, which both
tightens the bound and returns a candidate that is already a legal program.
"""


def bits(mask):
    """Yield the set bit positions of ``mask``, lowest first."""
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def reduce_clauses(clauses):
    """Drop clauses implied by a stricter one. None means unsatisfiable."""
    ordered = sorted(set(clauses), key=int.bit_count)
    kept = []
    for clause in ordered:
        if clause == 0:
            return None
        if not any(other & clause == other for other in kept):
            kept.append(clause)
    return kept


def packing_bound(clauses):
    """Lower bound: pairwise disjoint clauses each need their own element.

    Assumes ``clauses`` is already ordered by popcount, which the solver
    maintains, so the greedy packing takes the tightest clauses first.
    """
    used = 0
    count = 0
    for clause in clauses:
        if clause & used == 0:
            used |= clause
            count += 1
    return count


def _greedy(clauses, expand):
    """Upper bound: take the element hitting the most clauses per added unit."""
    index = {}
    for position, clause in enumerate(clauses):
        for element in bits(clause):
            index.setdefault(element, []).append(position)
    alive = [True] * len(clauses)
    remaining = len(clauses)
    chosen = 0
    counts = {element: len(rows) for element, rows in index.items()}
    while remaining:
        best, best_score = None, None
        for element, count in counts.items():
            if not count:
                continue
            grown = chosen | expand(element)
            cost = grown.bit_count() - chosen.bit_count()
            score = (count / max(cost, 1), -element)
            if best_score is None or score > best_score:
                best, best_score = element, score
        chosen |= expand(best)
        for position, clause in enumerate(clauses):
            if alive[position] and clause & chosen:
                alive[position] = False
                remaining -= 1
                for element in bits(clause):
                    counts[element] -= 1
    return chosen


def min_hitting_set(clauses, expand=None, node_limit=30000):
    """Smallest legal unit set meeting every clause.

    Returns ``size`` (best set found, an upper bound), ``bound`` (a guaranteed
    lower bound on the true minimum), ``exact`` (whether they provably agree)
    and ``witness`` (the set as a bitmask).
    """
    if expand is None:
        expand = lambda element: 1 << element
    reduced = reduce_clauses(clauses)
    if reduced is None:
        return {"size": 0, "bound": 0, "exact": False, "witness": 0,
                "infeasible": True, "nodes": 0}
    if not reduced:
        return {"size": 0, "bound": 0, "exact": True, "witness": 0,
                "infeasible": False, "nodes": 0}

    reduced.sort(key=int.bit_count)
    root_bound = packing_bound(reduced)
    start = _greedy(reduced, expand)
    best = [start.bit_count(), start]
    nodes = [0]
    complete = [True]

    def search(unhit, chosen):
        if nodes[0] >= node_limit:
            complete[0] = False
            return
        nodes[0] += 1
        size = chosen.bit_count()
        if not unhit:
            if size < best[0]:
                best[0], best[1] = size, chosen
            return
        if size + packing_bound(unhit) >= best[0]:
            return
        pivot = unhit[0]
        order = sorted(bits(pivot), key=lambda e: (chosen | expand(e)).bit_count())
        for element in order:
            grown = chosen | expand(element)
            survivors = [c for c in unhit if c & grown == 0]
            search(survivors, grown)

    search(reduced, 0)
    exact = complete[0]
    bound = best[0] if exact else root_bound
    return {"size": best[0], "bound": bound, "exact": exact,
            "witness": best[1], "infeasible": False, "nodes": nodes[0]}
