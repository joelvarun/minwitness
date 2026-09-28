"""Worker process that decides whether a reduced module still reproduces.

Runs out of process because deleting a ``break`` turns a stdlib ``while True``
into a real hang, which an in process oracle cannot escape. Hangs are handled
in two tiers: a watchdog first asks the evaluating thread to stop, which CPython
honours at any bytecode back edge and costs no process restart, and only a C
level loop that ignores that escalates to the parent killing the process.
"""

import ctypes
import io
import json
import os
import sys
import threading
import time
import types

PROTO_OUT = sys.stdout
PROTO_IN = sys.stdin
GRACE = 0.05
MAX_LEAKED = 3
DEADLINE_FACTOR = 25
MIN_DEADLINE = 0.05


class Interrupted(BaseException):
    """Raised into the evaluating thread when it overruns the deadline."""


def outcome(module, probe):
    """Encode what the probe expression does against a built module."""
    try:
        value = eval(probe, {"M": module, "__builtins__": __builtins__})
    except Interrupted:
        raise
    except BaseException as exc:
        return "E" + type(exc).__name__ + ":" + str(exc)
    try:
        return "V" + repr(value)
    except BaseException:
        return "Rrepr"


def evaluate(tree, kept, modname, probe):
    code = tree.compile_kept(kept)
    if code is None:
        return "Xsyntax"
    module = types.ModuleType(modname)
    module.__file__ = "<reduced>"
    saved = (sys.stdout, sys.stderr)
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    sys.modules[modname] = module
    try:
        exec(code, module.__dict__)
    except Interrupted:
        raise
    except BaseException as exc:
        return "B" + type(exc).__name__ + ":" + str(exc)
    finally:
        sys.stdout, sys.stderr = saved
        sys.modules.pop(modname, None)
    saved = (sys.stdout, sys.stderr)
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        return outcome(module, probe)
    finally:
        sys.stdout, sys.stderr = saved


def async_raise(thread):
    """Ask one thread to unwind. CPython checks this at every back edge."""
    ident = ctypes.c_ulong(thread.ident)
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ident, ctypes.py_object(Interrupted))


def guarded_evaluate(tree, kept, modname, probe, leaked, deadline):
    """Evaluate with a soft deadline; returns None when the thread will not die."""
    box = {}

    def body():
        try:
            box["result"] = evaluate(tree, kept, modname, probe)
        except BaseException as exc:
            box["result"] = "T" + type(exc).__name__

    thread = threading.Thread(target=body, daemon=True)
    thread.start()
    thread.join(deadline)
    if thread.is_alive():
        async_raise(thread)
        thread.join(GRACE)
        if thread.is_alive():
            leaked.append(1)
            return None
        return "Ttimeout"
    return box.get("result", "Tlost")


def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from minwitness.units import UnitTree

    config = json.loads(PROTO_IN.readline())
    tree = UnitTree(config["source"])
    modname, probe = config["modname"], config["probe"]
    clock = time.perf_counter()
    reference = evaluate(tree, tree.all_units, modname, probe)
    baseline = time.perf_counter() - clock
    deadline = max(MIN_DEADLINE, DEADLINE_FACTOR * baseline)
    PROTO_OUT.write(json.dumps({"n": tree.n, "reference": reference,
                                "baseline": baseline,
                                "deadline": deadline}) + chr(10))
    PROTO_OUT.flush()

    leaked = []
    served = 0
    while True:
        line = PROTO_IN.readline()
        if not line:
            return
        line = line.strip()
        if line == "q":
            return
        removed = set() if line == "-" else {int(x) for x in line.split(",")}
        kept = tree.close(tree.all_units - removed)
        result = guarded_evaluate(tree, kept, modname, probe, leaked, deadline)
        if result is None:
            return
        served += 1
        if served % 400 == 0:
            if evaluate(tree, tree.all_units, modname, probe) != reference:
                return
        if result == "Ttimeout":
            reply = "2"
        else:
            reply = "1" if result == reference else "0"
        PROTO_OUT.write(reply + chr(10))
        PROTO_OUT.flush()
        if len(leaked) >= MAX_LEAKED:
            return


if __name__ == "__main__":
    main()
