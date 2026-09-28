"""Derived per subject verdicts, shared by the demo and the chart.

A certificate is conditional on monotonicity. If any run on a subject produced
a bound above its own witness then that subject is provably not monotone, and
every "proved minimal" verdict for it, including ones from other reducers whose
clause sets happened to stay consistent, has to be withdrawn.
"""


def subject_flags(entry):
    """Verdicts for one subject, from the per method records alone."""
    methods = entry["methods"]
    refuting = [name for name, record in methods.items()
                if record["bound_exact"] and record["bound"] > record["witness_units"]]
    claimed = [name for name, record in methods.items()
               if record["certified_minimal"]]
    witnesses = {record["witness_units"] for record in methods.values()}
    return {
        "monotone_broken": bool(refuting),
        "refuting_methods": sorted(refuting),
        "claiming_methods": sorted(claimed),
        "proved_minimal": bool(claimed) and not refuting,
        "witness_units": min(witnesses),
        "witness_agrees": len(witnesses) == 1,
    }


def portfolio(subjects):
    """Roll the per subject verdicts up across every subject."""
    flags = [subject_flags(entry) for entry in subjects]
    return {
        "proved_minimal": sum(1 for f in flags if f["proved_minimal"]),
        "monotone_broken": sum(1 for f in flags if f["monotone_broken"]),
        "undecided": sum(1 for f in flags
                         if not f["proved_minimal"] and not f["monotone_broken"]),
        "witness_agrees": sum(1 for f in flags if f["witness_agrees"]),
        "flags": flags,
    }
