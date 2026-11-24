"""Regression check for read_counts_integrated's latch handling: a latched
bin (some channel's singles == 0) must be discarded and retried, not
accumulated into the returned totals or int_time."""
import datetime
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
    ANTILATCH_HOST='x', ANTILATCH_PORT=1, ANTILATCH_DEVICE_IDS=[0], ANTILATCH_BIAS_VOLTAGES=[{}],
    LOOP_CHS=[4, 6, 8, 10, 12, 14], DUMP_CH=7,
    BLACKOUT_START=datetime.time(5, 0), BLACKOUT_END=datetime.time(7, 30),
    in_blackout_window=lambda now=None: False,
    CYCLING_RECOVERY_TIME=datetime.time(9, 30), CYCLING_LATCH_PERSIST_S=600,
    CYCLING_MIN_COOLDOWN_S=3600,
    in_cycling_check_window=lambda now=None: False))

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


def _fake_clock(real_times):
    """real_times: list of real datetime.datetime instances to return from
    successive datetime.datetime.now() calls, then repeat the last one
    forever (the wait loop polls now() many times in a row)."""
    times = list(real_times)

    def now():
        if len(times) > 1:
            return times.pop(0)
        return times[0]
    return types.SimpleNamespace(now=now)


def test_persistent_latch_in_cycling_window_pauses_until_recovery(monkeypatch):
    """A latch that won't clear, inside the cycling-check window, must
    pause the whole read (no antilatch ping) until at least
    CYCLING_RECOVERY_TIME, then resume and finish normally -- this is the
    16-hour-measurement case: pausing in place rather than just
    suppressing a ping."""
    monkeypatch.setattr(det, 'in_cycling_check_window', lambda now=None: True)
    monkeypatch.setattr(det, 'CYCLING_LATCH_PERSIST_S', 0)  # trigger on the first latch
    monkeypatch.setattr(det.datetime, 'datetime', _fake_clock([
        datetime.datetime(2026, 1, 1, 4, 0),   # latch detected
        datetime.datetime(2026, 1, 1, 9, 0),   # still waiting
        datetime.datetime(2026, 1, 1, 9, 31),  # past CYCLING_RECOVERY_TIME -> resume
    ]))
    reads = [
        (np.array([0]), np.array([0, 5])),   # latched -- triggers cycling pause
        (np.array([3]), np.array([9, 5])),   # recovers after the pause
    ]
    c, s, t = _run(reads, monkeypatch)
    assert list(c) == [3]
    assert t == 1.0, "only the post-recovery bin should count"


def test_cycling_pause_enforces_minimum_cooldown_even_if_recovery_time_already_passed(monkeypatch):
    """The 2026-11-22/23 incident: a latch retriggers the cycling pause
    AFTER the clock has already passed CYCLING_RECOVERY_TIME (e.g. it
    relatched right after an earlier pause resumed). "wait until
    CYCLING_RECOVERY_TIME" is then already true on the very next check --
    a no-op that resumes (and starts pinging) immediately, which is
    exactly what kept making it latch more. The pause must still hold for
    CYCLING_MIN_COOLDOWN_S from right now in that case."""
    monkeypatch.setattr(det, 'in_cycling_check_window', lambda now=None: True)
    monkeypatch.setattr(det, 'CYCLING_LATCH_PERSIST_S', 0)
    monkeypatch.setattr(det, 'CYCLING_MIN_COOLDOWN_S', 3600)
    monkeypatch.setattr(det.datetime, 'datetime', _fake_clock([
        datetime.datetime(2026, 1, 1, 10, 0),   # already an hour past CYCLING_RECOVERY_TIME (9:30)
        datetime.datetime(2026, 1, 1, 10, 59),  # under an hour later -- must still be paused
        datetime.datetime(2026, 1, 1, 11, 1),   # now past the real 1hr-from-now cooldown -> resume
    ]))
    reads = [
        (np.array([0]), np.array([0, 5])),
        (np.array([3]), np.array([9, 5])),
    ]
    c, s, t = _run(reads, monkeypatch)
    assert list(c) == [3]
    assert t == 1.0, "must have actually waited out the minimum cooldown, not resumed immediately"


def test_persistent_latch_outside_cycling_window_does_not_pause(monkeypatch):
    """Same persistent latch, but outside 3-6am -- must use the normal
    retry/ping path, not the cycling pause."""
    monkeypatch.setattr(det, 'in_cycling_check_window', lambda now=None: False)
    monkeypatch.setattr(det, 'CYCLING_LATCH_PERSIST_S', 0)
    reads = [
        (np.array([0]), np.array([0, 5])),   # latched
        (np.array([3]), np.array([9, 5])),   # recovers on normal retry
    ]
    c, s, t = _run(reads, monkeypatch)
    assert list(c) == [3]
    assert t == 1.0


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
        """Minimal pytest-monkeypatch stand-in -- undo() restores every
        patched attribute, same as pytest's real fixture does automatically
        between test functions. Needed here because two tests in this file
        both patch det.datetime.datetime (the globally-shared module, not a
        per-test copy): without undo, the second test's real
        datetime.datetime(...) literals would call whatever fake the first
        test left behind instead of the real class."""
        def __init__(self):
            self._saved = []

        def setattr(self, obj, name, value):
            self._saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._saved):
                setattr(obj, name, old)
            self._saved.clear()

    for _test in [
        test_latched_bin_is_discarded_and_retried,
        test_no_latch_counts_normally,
        test_one_loop_channel_lit_is_not_a_latch,
        test_all_loop_channels_dark_is_a_latch,
        test_persistent_latch_in_cycling_window_pauses_until_recovery,
        test_persistent_latch_outside_cycling_window_does_not_pause,
        test_cycling_pause_enforces_minimum_cooldown_even_if_recovery_time_already_passed,
        test_dump_dark_alone_is_not_a_latch,
    ]:
        mp = _MonkeyPatch()
        _test(mp)
        mp.undo()
    print("ok")
