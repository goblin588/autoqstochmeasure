"""Regression check for read_counts_integrated's latch handling: a latched
bin (some channel's singles == 0) must be discarded and retried, not
accumulated into the returned totals or int_time."""
import itertools

import numpy as np

# tomocore.interfaces.logic16's Logic16 only touches pythonnet/clr/the vendor
# DLL inside __init__, which _FakeLogic16 below bypasses entirely -- so
# unlike the old hardware.detector, no clr/System/TimeTag/settings stubbing
# is needed just to import and test the pure retry logic.
import tomocore.interfaces.logic16 as det

# Matches this rig's real channel layout (see autoqstochmeasure's own
# settings.py), passed explicitly now that Logic16 takes loop_chs/dump_ch as
# constructor args instead of importing them from a settings module.
_LOOP_CHS = (4, 6, 8, 10, 12, 14)
_DUMP_CH = 7


class _FakeLogic16(det.Logic16):
    """Bypasses __init__ (no real card) and feeds canned reads in order."""
    def __init__(self, reads, integration_window=1.0, loop_chs=_LOOP_CHS, dump_ch=_DUMP_CH):
        self._reads = list(reads)
        self._integration_window = integration_window
        self.singles = None
        self.antilatch_func = lambda: None  # no real network ping
        self._antilatch_thread = None
        self._loop_chs = set(loop_chs)
        self._dump_ch = dump_ch

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


def _run_loop(reads, monkeypatch):
    """Same as _run, but pos_singles is [herald, *every loop channel] --
    for checking the loop-channel group behaviour specifically."""
    monkeypatch.setattr(det.time, 'sleep', lambda s: None)
    clock = itertools.count(0, 1.0)
    monkeypatch.setattr(det.time, 'monotonic', lambda: next(clock))
    logic = _FakeLogic16(reads)
    pos_singles = [3, 4, 6, 8, 10, 12, 14]
    return logic.read_counts_integrated(pos_coincidence=[[3, 4]], pos_singles=pos_singles)


def test_one_loop_channel_lit_is_not_a_latch(monkeypatch):
    """Only ch4 has real signal (e.g. _set_bypass_optics routes everything
    there) -- the other 5 loop channels legitimately read 0, but since
    they share one distribution board, that must NOT be flagged as a
    latch (the old any-channel-zero check would have false-positived
    here forever)."""
    reads = [(np.array([3]), np.array([9, 5, 0, 0, 0, 0, 0]))]
    c, s, t = _run_loop(reads, monkeypatch)
    assert list(c) == [3]
    assert t == 1.0, "a lit loop channel must not trigger a discard/retry"


def test_all_loop_channels_dark_is_a_latch(monkeypatch):
    """Herald fine, but every loop channel reads 0 -- the shared detector
    really is latched, so this bin must still be discarded and retried."""
    reads = [
        (np.array([0]), np.array([9, 0, 0, 0, 0, 0, 0])),  # latched
        (np.array([3]), np.array([9, 5, 0, 0, 0, 0, 0])),  # recovers
    ]
    c, s, t = _run_loop(reads, monkeypatch)
    assert list(c) == [3], "the all-dark bin's counts must not be accumulated"
    assert t == 1.0, "int_time should reflect only the recovered bin"


def test_dump_dark_alone_is_not_a_latch(monkeypatch):
    """Dump is a standalone channel excluded from the check entirely --
    none of the automated loop/exit optics configs route light there, so
    it reads 0 every time by design. That alone must never trigger a
    discard/retry, even with herald and every loop channel fine."""
    monkeypatch.setattr(det.time, 'sleep', lambda s: None)
    clock = itertools.count(0, 1.0)
    monkeypatch.setattr(det.time, 'monotonic', lambda: next(clock))
    logic = _FakeLogic16([(np.array([3]), np.array([9, 5, 5, 5, 5, 5, 5, 0]))])
    pos_singles = [3, 4, 6, 8, 10, 12, 14, 7]  # herald, loop chs, dump
    c, s, t = logic.read_counts_integrated(pos_coincidence=[[3, 4]], pos_singles=pos_singles)
    assert list(c) == [3]
    assert t == 1.0, "dump reading 0 alone must not trigger a discard/retry"


if __name__ == "__main__":
    class _MonkeyPatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _MonkeyPatch()
    test_latched_bin_is_discarded_and_retried(mp)
    test_no_latch_counts_normally(mp)
    test_one_loop_channel_lit_is_not_a_latch(mp)
    test_all_loop_channels_dark_is_a_latch(mp)
    test_dump_dark_alone_is_not_a_latch(mp)
    print("ok")
