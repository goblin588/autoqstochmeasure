"""Regression check for tune_delays' quick pre-scan: a clear peak within
+/-5 steps of the old delay should skip the full zoom; a drifted/no-peak
channel should still fall back to it."""
import sys
import types

import numpy as np

sys.modules.setdefault('clr', types.SimpleNamespace(AddReference=lambda p: None))
sys.modules.setdefault('System', types.SimpleNamespace(Int32=int))
sys.modules.setdefault('TimeTag', types.SimpleNamespace(TTInterface=object, Logic=object))

_settings_stub = types.SimpleNamespace(
    ANTILATCH_HOST='x', ANTILATCH_PORT=1, ANTILATCH_DEVICE_IDS=[0], ANTILATCH_BIAS_VOLTAGES=[{}],
    TRIGG_CH=1, DET_CHS=[2], DUMP_CH=7, LOOP_CHS=[2], COINCIDENCE_WINDOW=1.0,
    DELAYS=[0.0] * 16, THRESHOLDS=0.4, BACKGROUND_OFFSET_NS=15.0,
    TUNE_INTEGRATION_S={}, CHANNELS={2: {'delay': 0.0}},
    delays_for=lambda: [0.0] * 16, save_calibration=lambda *a, **kw: None,
)
# Direct assignment, not setdefault: test_scan_resweep.py registers the same
# module name with a stub missing CHANNELS/save_calibration, and whichever
# test file's import runs first would otherwise win for both.
sys.modules['libraries.settings'] = _settings_stub

import libraries.countingcard as cc
import hardware.detector as det


class _FakeLogic16(det.Logic16):
    """Coincidence counts form a tent peaking at `peak_delay` on channel `ch`.
    `background` sets the flat floor read everywhere else (including the
    background-offset probe), so tests can push the peak below/above the bar."""
    def __init__(self, peak_delay, ch, background=0.0):
        self.peak_delay = peak_delay
        self.ch = ch
        self.background = background
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

    def set_coincidence_window(self, window):
        pass

    def read_counts_integrated(self, pos_coincidence, pos_singles, neg_singles=[0]):
        self.n_reads += 1
        peak = max(0.0, 10.0 - abs(self.current_delay - self.peak_delay))
        counts = max(peak, self.background)
        return np.array([counts]), np.array([50, 50]), 1.0


def test_clear_peak_in_quick_window_skips_full_zoom(monkeypatch):
    # Old delay (0.0) is close to the true peak (2.0) -- well inside +/-5 steps.
    fake = _FakeLogic16(peak_delay=2.0, ch=2, background=0.0)
    monkeypatch.setattr(cc, 'Logic16', lambda **kwargs: fake)
    cc.tune_delays(step=1.0, signal_chs=[2], integration_time=1.0, min_counts=1.0, auto_save=True)
    assert _settings_stub.CHANNELS[2]['delay'] == 2.0
    # Quick scan is 11 points + background probes; the full zoom (several
    # windows x many points) would read far more than that.
    assert fake.n_reads < 25, f"expected the quick path, got {fake.n_reads} reads"


def test_drifted_peak_falls_back_to_full_zoom(monkeypatch):
    # True peak (30.0) sits way outside the +/-5ns quick window around 0.0.
    fake = _FakeLogic16(peak_delay=30.0, ch=2, background=0.0)
    monkeypatch.setattr(cc, 'Logic16', lambda **kwargs: fake)
    cc.tune_delays(step=1.0, span=40.0, signal_chs=[2], integration_time=1.0, min_counts=1.0,
                   auto_save=True)
    assert abs(_settings_stub.CHANNELS[2]['delay'] - 30.0) < 1.0
    assert fake.n_reads > 25, "should have fallen through to the full zoom"
