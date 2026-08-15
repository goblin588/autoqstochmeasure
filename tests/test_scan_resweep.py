"""Regression check for scan_and_record's edge-of-window resweep: if the
best delay found sits within 2 steps of either edge of the swept window,
the true peak may be outside it, so the scan should recentre there and
sweep again instead of silently returning an edge point."""
import sys
import types

import numpy as np

# hardware.detector needs pythonnet's `clr` + the TimeTag DLL, both
# Windows-only — stub them out so the module (and countingcard, which
# imports Logic16 from it) can be imported and tested on any platform.
sys.modules.setdefault('clr', types.SimpleNamespace(AddReference=lambda p: None))
sys.modules.setdefault('System', types.SimpleNamespace(Int32=int))
sys.modules.setdefault('TimeTag', types.SimpleNamespace(TTInterface=object, Logic=object))

_settings_stub = types.SimpleNamespace(
    ANTILATCH_HOST='x', ANTILATCH_PORT=1, ANTILATCH_DEVICE_IDS=[0], ANTILATCH_BIAS_VOLTAGES=[{}],
    TRIGG_CH=1, DET_CHS=[2], DUMP_CH=7, LOOP_CHS=[2, 4], COINCIDENCE_WINDOW=1.0,
    DELAYS=[0.0] * 16, THRESHOLDS=0.4, BACKGROUND_OFFSET_NS=15.0,
    delays_for=lambda: [0.0] * 16,
)
sys.modules.setdefault('libraries.settings', _settings_stub)

import libraries.countingcard as cc
import hardware.detector as det


class _FakeLogic16(det.Logic16):
    """Bypasses __init__ (no real card); coincidence count peaks in a tent
    shape at `peak_delay` on whichever channel is being scanned."""
    def __init__(self, peak_delay, ch):
        self.peak_delay = peak_delay
        self.ch = ch
        self.current_delay = 0.0
        self.n_reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def configure(self, **kwargs):
        pass

    def set_delays(self, channel_delays):
        self.current_delay = channel_delays[self.ch - 1]

    def set_integration_window(self, seconds):
        pass

    def read_counts_integrated(self, pos_coincidence, pos_singles, neg_singles=[0]):
        self.n_reads += 1
        counts = max(0.0, 10.0 - abs(self.current_delay - self.peak_delay))
        return np.array([counts]), np.array([50, 50]), 1.0


def test_resweeps_until_peak_outside_initial_window_is_found(monkeypatch):
    fake = _FakeLogic16(peak_delay=25.0, ch=2)
    monkeypatch.setattr(cc, 'Logic16', lambda **kwargs: fake)
    best_delay, row = cc.scan_and_record(
        ch=2, absolute_range=(0.0, 20.0), step=1.0, herald_ch=1, record_duration=1.0)
    assert best_delay == 25.0, "should have recentred outward to find the true peak at 25ns"
    assert fake.n_reads > 21, "should have swept more than once to get there"


def test_no_resweep_when_peak_already_has_margin(monkeypatch):
    fake = _FakeLogic16(peak_delay=10.0, ch=2)
    monkeypatch.setattr(cc, 'Logic16', lambda **kwargs: fake)
    best_delay, row = cc.scan_and_record(
        ch=2, absolute_range=(0.0, 20.0), step=1.0, herald_ch=1, record_duration=1.0)
    assert best_delay == 10.0
    assert fake.n_reads == 22, "one sweep (21 pts) + one final recording read, no resweep"
