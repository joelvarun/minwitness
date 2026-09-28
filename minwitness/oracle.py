"""Parent side driver for the reduction oracle.

Holds a persistent worker subprocess, enforces a wall clock timeout, and counts
every real invocation. A timeout is never trusted on its own: the query is
re decided alone in a fresh worker at a much longer limit before it is recorded
as a non reproduction.
"""

import json
import os
import queue
import subprocess
import sys
import threading

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.py")


class OracleError(RuntimeError):
    pass


class Oracle:
    """Answers "does this subset of units still reproduce the observation?"."""

    def __init__(self, source, modname, probe, timeout=1.0, recheck=2.5):
        self.source = source
        self.modname = modname
        self.probe = probe
        self.timeout = timeout
        self.recheck = recheck
        self.proc = None
        self.queue = None
        self.n = 0
        self.reference = None
        self.cache = {}
        self.calls = 0
        self.cache_hits = 0
        self.timeouts = 0
        self.soft_timeouts = 0
        self.reclassified = 0
        self.restarts = 0
        self._start()

    def _start(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-u", WORKER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        self.queue = queue.Queue()
        pipe, box = self.proc.stdout, self.queue
        thread = threading.Thread(target=self._pump, args=(pipe, box), daemon=True)
        thread.start()
        payload = {"source": self.source, "modname": self.modname, "probe": self.probe}
        self.proc.stdin.write(json.dumps(payload) + chr(10))
        self.proc.stdin.flush()
        try:
            handshake = json.loads(self.queue.get(timeout=30.0))
        except (queue.Empty, ValueError):
            raise OracleError("worker failed to start for " + self.modname)
        self.n = handshake["n"]
        self.reference = handshake["reference"]
        self.baseline = handshake["baseline"]
        self.deadline = handshake["deadline"]

    @staticmethod
    def _pump(pipe, box):
        for line in pipe:
            box.put(line)
        box.put(None)

    def _kill(self):
        try:
            self.proc.kill()
            self.proc.wait(timeout=5)
        except Exception:
            pass

    def _ask(self, removed, timeout):
        line = "-" if not removed else ",".join(str(i) for i in sorted(removed))
        try:
            self.proc.stdin.write(line + chr(10))
            self.proc.stdin.flush()
        except (OSError, ValueError):
            return None
        try:
            reply = self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if reply is None:
            return None
        token = reply.strip()
        if token == "2":
            self.soft_timeouts += 1
            return False
        if token not in ("0", "1"):
            return None
        return token == "1"

    def test(self, kept):
        """True if the module restricted to ``kept`` still reproduces."""
        key = frozenset(kept)
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        removed = [i for i in range(self.n) if i not in key]
        self.calls += 1
        verdict = self._ask(removed, self.timeout)
        if verdict is None:
            self.timeouts += 1
            self._kill()
            self.restarts += 1
            self._start()
            verdict = self._ask(removed, self.recheck)
            if verdict is None:
                self._kill()
                self.restarts += 1
                self._start()
                verdict = False
            elif verdict:
                self.reclassified += 1
        self.cache[key] = verdict
        return verdict

    def reset(self):
        """Clear the cache and counters so each reducer is measured alone."""
        self.cache.clear()
        self.calls = 0
        self.cache_hits = 0
        self.timeouts = 0
        self.soft_timeouts = 0
        self.reclassified = 0
        self.restarts = 0

    def stats(self):
        return {"calls": self.calls, "cache_hits": self.cache_hits,
                "timeouts": self.timeouts, "soft_timeouts": self.soft_timeouts,
                "reclassified": self.reclassified, "restarts": self.restarts}

    def close(self):
        try:
            self.proc.stdin.write("q" + chr(10))
            self.proc.stdin.flush()
            self.proc.wait(timeout=5)
        except Exception:
            self._kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
