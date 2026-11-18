"""Regression check for _tune_delays_peaked's dispatch: ch4/ch6 get their
dedicated, bench-trusted closed-form presets (_set_bypass_optics/
_set_loop_optics); ch8/10/12/14 get U3/U4/U5/U6 + s0 respectively (each
channel's own process preset, via _set_u); DUMP_CH (no dedicated preset
at all) falls back to U6/s0. Stubs out libraries.countingcard.tune_delays
so this runs without the real counting card (needs pythonnet/TimeTag
even to import)."""
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


def test_ch4_and_ch6_get_their_dedicated_presets(monkeypatch):
    applied = []
    for ch, fn in list(m._LOOP_PEAK_OPTICS.items()):
        def wrapper(ch=ch, orig=fn):
            applied.append(ch)
            return orig()
        monkeypatch.setitem(m._LOOP_PEAK_OPTICS, ch, wrapper)

    _calls.clear()
    m._tune_delays_peaked([4, 6], integration_time=2.0, auto_save=True)

    assert applied == [4, 6]
    assert _calls == [((ch,), 2.0, True) for ch in (4, 6)]


def test_ch8_10_12_14_get_their_own_process_preset(monkeypatch):
    # each gets U_N/s0 for N = that channel's own pass number, not a
    # shared U6 -- U_N concentrates meaningful probability at pass N.
    seeded = []
    monkeypatch.setattr(m, '_set_unitary', lambda N: seeded.append(('unitary', N)))
    monkeypatch.setattr(m, '_set_input_state', lambda N, j: seeded.append(('state', N, j)))

    _calls.clear()
    m._tune_delays_peaked([8, 10, 12, 14], integration_time=2.0, auto_save=True)

    assert seeded == [('unitary', '3'), ('state', '3', 0), ('unitary', '4'), ('state', '4', 0),
                       ('unitary', '5'), ('state', '5', 0), ('unitary', '6'), ('state', '6', 0)]
    assert _calls == [((ch,), 2.0, True) for ch in (8, 10, 12, 14)]


def test_only_last_channel_can_prompt_to_save(monkeypatch):
    # tune_delays() itself asks "save?" whenever auto_save is falsy --
    # calling it once per channel must not ask once per channel. Every
    # channel but the last always auto-saves; the last uses auto_save as
    # given, so an interactive caller (auto_save=False) is asked exactly
    # once, covering every channel just tuned.
    for ch, fn in list(m._LOOP_PEAK_OPTICS.items()):
        monkeypatch.setitem(m._LOOP_PEAK_OPTICS, ch, lambda orig=fn: orig())

    _calls.clear()
    m._tune_delays_peaked([4, 6, 8], integration_time=2.0, auto_save=False)

    assert _calls == [((4,), 2.0, True), ((6,), 2.0, True), ((8,), 2.0, False)]


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
