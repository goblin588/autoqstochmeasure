"""Regression check for _tune_delays_peaked's dispatch: each loop channel
must get its own dedicated peak-optics preset (_set_bypass_optics/
_set_loop_optics/_set_loop{3,4,5,6}_optics) before being tuned, and
DUMP_CH (no dedicated preset) must fall back to U6/s0. Stubs out
libraries.countingcard.tune_delays so this runs without the real counting
card (needs pythonnet/TimeTag even to import)."""
import os
import sys
import types

os.environ.setdefault('AUTOTOMO_SIM', '1')
os.environ.setdefault('DUMP_ENABLED', '0')
sys.path.insert(0, 'src')

_calls = []


def _install_fake_countingcard():
    fake = types.ModuleType('libraries.countingcard')

    def fake_tune_delays(signal_chs, integration_time=None, auto_save=False):
        _calls.append((tuple(signal_chs), integration_time, auto_save))

    fake.tune_delays = fake_tune_delays
    sys.modules['libraries.countingcard'] = fake


_install_fake_countingcard()
import measurement as m


def test_each_loop_channel_gets_its_own_preset(monkeypatch):
    applied = []
    for ch, fn in list(m._LOOP_PEAK_OPTICS.items()):
        def wrapper(ch=ch, orig=fn):
            applied.append(ch)
            return orig()
        monkeypatch.setitem(m._LOOP_PEAK_OPTICS, ch, wrapper)

    _calls.clear()
    m._tune_delays_peaked([4, 6, 8, 10, 12, 14], integration_time=2.0, auto_save=True)

    assert applied == [4, 6, 8, 10, 12, 14]
    assert _calls == [((ch,), 2.0, True) for ch in (4, 6, 8, 10, 12, 14)]


def test_dump_channel_falls_back_to_u6_s0(monkeypatch):
    seeded = []
    monkeypatch.setattr(m, '_set_unitary', lambda N: seeded.append(('unitary', N)))
    monkeypatch.setattr(m, '_set_input_state', lambda N, j: seeded.append(('state', N, j)))

    _calls.clear()
    m._tune_delays_peaked([7])

    assert seeded == [('unitary', '6'), ('state', '6', 0)]
    assert _calls == [((7,), None, False)]


if __name__ == '__main__':
    print('test_tune_delays_peaked needs pytest (monkeypatch fixture) -- run via pytest.')
