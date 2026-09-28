"""Reduction tasks built from the local CPython standard library.

Each subject pairs a real pure Python stdlib module with a one line probe. The
task is: find the smallest subset of the module's statements under which the
probe still does exactly what it does under the full module. No downloads, no
synthetic code, no injected faults.
"""

import os
import sysconfig

STDLIB = sysconfig.get_paths()["stdlib"]

SUBJECTS = [
    ("colorsys", "colorsys", "M.rgb_to_hsv(0.2, 0.4, 0.4)", "value"),
    ("fnmatch", "fnmatch", "M.fnmatch('report.txt', '*.txt')", "value"),
    ("string", "string", "M.Template('$a-$b').substitute(a='x', b='y')", "value"),
    ("textwrap", "textwrap", "M.wrap('the quick brown fox jumps', 10)", "value"),
    ("getopt", "getopt", "M.getopt(['-a', '-b', 'x'], 'ab:')", "value"),
    ("shlex", "shlex", "M.split('one \"two three\" four')", "value"),
    ("shlex-error", "shlex", "M.split('unbalanced \"quote')", "exception"),
    ("csv", "csv", "M.Sniffer().sniff('a,b,c')  .delimiter", "value"),
    ("base64", "base64", "M.b85encode(b'abcdefgh')", "value"),
    ("copy", "copy", "M.deepcopy({'a': [1, 2], 'b': (3, 4)})", "value"),
    ("posixpath", "posixpath", "M.normpath('a/b/../c/./d')", "value"),
    ("fractions", "fractions", "repr(M.Fraction('3/6') + M.Fraction(1, 6))", "value"),
    ("fractions-error", "fractions", "M.Fraction('1/0')", "exception"),
    ("calendar", "calendar", "M.monthrange(2024, 2)", "value"),
]


def source_of(module):
    """Read one stdlib module's source text from the running interpreter."""
    path = os.path.join(STDLIB, module + ".py")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def load(names=None):
    """Yield (name, module, probe, kind, source) for the requested subjects."""
    for name, module, probe, kind in SUBJECTS:
        if names is not None and name not in names:
            continue
        yield name, module, probe, kind, source_of(module)
