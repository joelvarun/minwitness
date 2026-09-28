"""Turn a 1-minimal witness into a proved lower bound on the true minimum.

1-minimality only says no single unit can leave *this* witness. It does not say
the witness is the smallest reproducer in the program, because a smaller one may
live elsewhere in the subset lattice. Two steps close that gap:

  necessity probes  remove one unit at a time from the *full* program. If the
                    program minus unit u stops reproducing then u belongs to
                    every reproducer, which is a unit clause. Costs at most
                    one oracle call per unit of the witness.
  hitting set jumps an implicit hitting set loop. The smallest legal unit set
                    consistent with everything seen so far is either a new and
                    smaller reproducer, or its failure is a fresh constraint
                    that raises the bound.
"""

from .reducers import enforce_1_minimal
from .store import to_set


def necessity_probes(task, witness):
    """Test the full program minus each single unit of the witness."""
    full = task.close(set(range(task.n)))
    for unit in sorted(witness):
        candidate = task.close(full - {unit})
        if len(candidate) < len(full):
            task.test(candidate)


def certify(task, witness, max_jumps=40, patience=5):
    """Return (witness, certificate, stats) after probing and jumping.

    ``patience`` stops the loop once the bound has refused to move for that
    many jumps in a row, because each jump costs a real oracle call and a
    failed jump only rules out one candidate.
    """
    store = task.tester.store
    necessity_probes(task, witness)
    certificate = store.certificate()
    seen = set()
    jumps = 0
    improved = 0
    stale = 0
    while certificate["bound"] < len(witness) and jumps < max_jumps:
        candidate = frozenset(to_set(certificate["witness"]))
        if not candidate or candidate in seen:
            break
        seen.add(candidate)
        jumps += 1
        before = certificate["bound"]
        if task.test(set(candidate)):
            shrunk = enforce_1_minimal(task, set(candidate))
            if len(shrunk) < len(witness):
                witness = shrunk
                improved += 1
                necessity_probes(task, witness)
        certificate = store.certificate()
        stale = 0 if certificate["bound"] > before else stale + 1
        if stale >= patience:
            break
    return witness, certificate, {"jumps": jumps, "improved": improved}
