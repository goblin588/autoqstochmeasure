"""Regression check for read_counts_integrated's latch handling: a latched
bin (some channel's singles == 0) must be discarded and retried, not
accumulated into the returned totals or int_time."""
import itertools
import sys
import types

import numpy as np

# hardware.detector needs pythonnet's `clr` + the TimeTag DLL, both
# Windows-only — stub them out so the module (and its pure retry logic) can
# be imported and tested on any platform.
sys.modules.setdefault('clr', types.SimpleNamespace(AddReference=lambda p: None))
sys.modules.setdefault('System', types.SimpleNamespace(Int32=int))
sys.modules.setdefault('TimeTag', types.SimpleNamespace(TTInterface=object, Logic=object))
sys.modules.setdefault('libraries.settings', types.SimpleNamespace(
    ANTILATCH_HOST='x', ANTILATCH_PORT=1, ANTILATCH_DEVICE_IDS=[0], ANTILATCH_BIAS_VOLTAGES=[{}]))

import hardware.detector as det


class _FakeLogic16(det.Logic16):
    """Bypasses __init__ (no real card) and feeds canned reads in order."""
    def __init__(self, reads, integration_window=1.0):
        self._reads = list(reads)
        self._integration_window = integration_window
        self.singles = None
        self.antilatch_func = lambda: None  # no real network ping
        self._antilatch_thread = None

    def read_counts(self, pos_coincidence, pos_singles, neg_singles=[0]):
        c, s = self._reads.pop(0)
        return c, s, 0


def _run(reads, monkeypatch):
    monkeypatch.setattr(det.time, 'sleep', lambda s: None)
    clock = itertools.count(0, 1.0)
    monkeypatch.setattr(det.time, 'monotonic', lambda: next(clock))
    logic = _FakeLogic16(reads)
    return logic.read_counts_integrated(pos_coincidence=[[3, 2]], pos_singles=[3, 2])


def test_latched_bin_is_discarded_and_retried(monkeypatch):
    reads = [
        (np.array([0]), np.array([0, 5])),   # latched: herald singles == 0
        (np.array([3]), np.array([9, 5])),   # good bin
    ]
    c, s, t = _run(reads, monkeypatch)
    assert list(c) == [3], "latched bin's zero counts must not be accumulated"
    assert list(s) == [9, 5]
    assert t == 1.0, "int_time should reflect only the good bin, not the discarded one"


def test_no_latch_counts_normally(monkeypatch):
    reads = [(np.array([3]), np.array([9, 5]))]
    c, s, t = _run(reads, monkeypatch)
    assert list(c) == [3]
    assert list(s) == [9, 5]
    assert t == 1.0


if __name__ == "__main__":
    class _MonkeyPatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _MonkeyPatch()
    test_latched_bin_is_discarded_and_retried(mp)
    test_no_latch_counts_normally(mp)
    print("ok")
