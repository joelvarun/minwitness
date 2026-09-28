"""Program reducers under a shared oracle interface.

All three baselines return a 1-minimal witness, so their oracle call counts are
directly comparable. ``ddmin`` is Zeller and Hildebrandt's original, ``hdd``
is Misherghi and Su's hierarchical variant, and ``probdd`` is the probabilistic
reducer of Wang et al., which is the closest prior art to this project: it also
learns "at least one of these units is required" from every failure, but uses
it as a soft Bayesian update rather than an exact constraint.
"""


class Task:
    """One reduction problem: a unit tree plus a guarded tester."""

    def __init__(self, tree, tester):
        self.tree = tree
        self.tester = tester
        self.n = tree.n

    def close(self, kept):
        return self.tree.close(kept)

    def test(self, kept):
        return self.tester.test(kept)

    def test_raw(self, kept):
        """Bypass the constraint store and ask the oracle itself."""
        return self.tester.test_direct(kept)


def partition(items, count):
    """Split ``items`` into ``count`` near equal contiguous chunks."""
    size = len(items)
    step = size / count
    chunks = []
    for index in range(count):
        lo = int(round(index * step))
        hi = int(round((index + 1) * step))
        if hi > lo:
            chunks.append(items[lo:hi])
    return chunks


def _ddmin_over(task, removable, materialise, current):
    """Classic ddmin restricted to ``removable``, everything else held fixed."""
    live = set(removable)
    granularity = 2
    while len(live) >= 2:
        chunks = partition(sorted(live), min(granularity, len(live)))
        progressed = False
        for chunk in chunks:
            candidate = materialise(set(chunk))
            if len(candidate) < len(current) and task.test(candidate):
                current, live = candidate, {u for u in chunk if u in candidate}
                granularity = 2
                progressed = True
                break
        if progressed:
            continue
        for chunk in chunks:
            candidate = materialise(live - set(chunk))
            if len(candidate) < len(current) and task.test(candidate):
                current = candidate
                live = {u for u in live if u in candidate}
                granularity = max(granularity - 1, 2)
                progressed = True
                break
        if progressed:
            continue
        if granularity >= len(live):
            break
        granularity = min(granularity * 2, len(live))
    return current


def ddmin(task):
    """Flat ddmin over every statement in the module."""
    current = task.close(set(range(task.n)))
    return _ddmin_over(task, current, task.close, current)


def hdd(task):
    """Hierarchical delta debugging: ddmin level by level down the tree."""
    current = task.close(set(range(task.n)))
    for level in task.tree.levels():
        present = [u for u in level if u in current]
        if len(present) < 2:
            continue
        fixed = current - set(present)
        current = _ddmin_over(
            task, present, lambda sub: task.close(fixed | sub), current)
    return current


def probdd(task, prior=0.1, rounds=None):
    """Probabilistic delta debugging (Wang et al., ESEC/FSE 2021)."""
    current = task.close(set(range(task.n)))
    required = {unit: prior for unit in current}
    budget = rounds if rounds is not None else 20 * task.n
    for _ in range(budget):
        order = sorted(current, key=lambda u: required[u])
        best_gain, best_k = 0.0, 0
        survival = 1.0
        for index, unit in enumerate(order, start=1):
            survival *= 1.0 - required[unit]
            gain = index * survival
            if gain > best_gain:
                best_gain, best_k = gain, index
        if best_k == 0:
            break
        chosen = order[:best_k]
        candidate = task.close(current - set(chosen))
        if len(candidate) >= len(current):
            break
        if task.test(candidate):
            current = candidate
            required = {u: required[u] for u in current}
        else:
            miss = 1.0
            for unit in chosen:
                miss *= 1.0 - required[unit]
            evidence = 1.0 - miss
            if evidence <= 1e-12:
                break
            for unit in chosen:
                required[unit] = min(required[unit] / evidence, 1.0 - 1e-9)
    return current


def enforce_1_minimal(task, current, trust_store=True):
    """Remove single units until no single removal keeps the reproduction.

    With ``trust_store`` false every query goes to the real oracle, so the
    result is genuinely 1-minimal without assuming monotonicity. That final
    pass is what lets the fast path stay unsound and still ship a correct
    answer.
    """
    probe = task.test if trust_store else task.test_raw
    changed = True
    while changed:
        changed = False
        for unit in sorted(current, reverse=True):
            if unit not in current:
                continue
            candidate = task.close(current - {unit})
            if len(candidate) < len(current) and probe(candidate):
                current = candidate
                changed = True
    return current


REDUCERS = {"ddmin": ddmin, "hdd": hdd, "probdd": probdd}


def run(name, task, verify=True):
    """Run a named reducer, then settle 1-minimality against the oracle."""
    current = enforce_1_minimal(task, REDUCERS[name](task))
    if verify:
        current = enforce_1_minimal(task, current, trust_store=False)
    return current
