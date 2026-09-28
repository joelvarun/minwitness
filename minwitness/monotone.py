"""Measure the monotonicity assumption instead of taking it on faith.

Every learning based reducer, ProbDD included, assumes that if a kept set
reproduces then so does every superset of it. The constraint store and the
certificate both rest on the same assumption. This module checks it two ways.

self refutation  the certified lower bound can only exceed the witness size if
                 some clause is unsound, because the witness is a measured
                 reproducer that ought to hit every clause. That check is free
                 and needs no extra oracle call.
counterexample   an unsound clause names a concrete kept set that contains the
                 witness and still failed. Re testing that pair against the
                 oracle is an assumption free proof of non monotonicity.
"""

from .store import to_mask, to_set


def is_self_refuting(certificate, witness):
    """True when the bound provably contradicts the witness we already hold."""
    return certificate["exact"] and certificate["bound"] > len(witness)


def find_counterexamples(task, witness, limit=3):
    """Confirm superset/subset pairs where the superset fails and the subset holds."""
    store = task.tester.store
    witness_mask = to_mask(witness)
    universe = set(range(task.n))
    found = []
    for clause in sorted(store.clauses, key=int.bit_count, reverse=True):
        if clause & witness_mask:
            continue
        bigger = task.close(universe - to_set(clause))
        if len(bigger) <= len(witness):
            continue
        if task.test_raw(bigger) or not task.test_raw(set(witness)):
            continue
        found.append({"superset_units": len(bigger),
                      "witness_units": len(witness),
                      "extra_units": len(bigger) - len(witness)})
        if len(found) >= limit:
            break
    return found


def describe_unit(tree, unit):
    """The statement's own first line, as written in the original file."""
    node = tree.nodes[unit]
    return tree.source.splitlines()[node.lineno - 1].strip()


def single_statement_breaks(tree, oracle, witness, limit=None):
    """Units that, put back into the witness alone, stop it reproducing.

    This is the sharpest possible refutation: strictly more program, strictly
    less reproduction. It happens because a program is not a bag of independent
    parts. The statement being restored refers to a name the reduction already
    deleted, so the module now raises on import.
    """
    found = []
    for unit in range(tree.n):
        if unit in witness:
            continue
        candidate = tree.close(set(witness) | to_set(tree.up_masks[unit]))
        if len(candidate) != len(witness) + 1:
            continue
        if not oracle.test(candidate):
            found.append(unit)
            if limit is not None and len(found) >= limit:
                break
    return found


def audit(task, witness, certificate):
    """Full monotonicity report for one finished reduction."""
    tester = task.tester
    report = {
        "self_refuting": is_self_refuting(certificate, witness),
        "bound": certificate["bound"],
        "witness_units": len(witness),
        "validated": tester.validated,
        "violations": tester.violations,
    }
    if report["self_refuting"]:
        report["counterexamples"] = find_counterexamples(task, witness)
    else:
        report["counterexamples"] = []
    return report
