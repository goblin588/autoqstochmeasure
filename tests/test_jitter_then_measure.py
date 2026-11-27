"""Regression check for jitter_then_measure(): it must rank jitter-sweep
configs by KL and actually measure the sall run AT each chosen config's
angles -- not the plain nominal unitary. measurement() unconditionally
repositions the waveplates itself (normally via _set_unitary(N)); passing the
chosen config's angles through fixed_waveplate_angles=... is what makes that
stick instead of being immediately overwritten (2026-11-27 bug: a prior
version pre-positioned with a standalone _set_fixed_waveplates() call that
measurement() then clobbered a line later). Runs entirely in AUTOTOMO_SIM
mode (mock stages)."""
import os
import sys

os.environ.setdefault('AUTOTOMO_SIM', '1')
os.environ.setdefault('DUMP_ENABLED', '0')
sys.path.insert(0, 'src')

import measurement as m


def test_full_angles_to_short_round_trips():
    # unitaries_angles also carries mirror phases (m1/m2/m3) that aren't
    # motorized waveplates -- _set_fixed_waveplates only moves/returns the
    # 10 it knows about, so restrict the comparison to those.
    short_keys = {key for key, _name, _stage in m._FIXED_WAVEPLATE_KEYS}
    nominal = {k: v for k, v in m.unitaries_angles['3'].items() if k in short_keys}
    confirmed = m._set_fixed_waveplates(dict(nominal))
    round_tripped = m._full_angles_to_short(confirmed)
    assert round_tripped.keys() == nominal.keys()
    # sim-mode move_stage reads back the commanded angle through its own
    # simulated position encoding, so expect float noise, not a byte-identical echo.
    for key in nominal:
        assert abs(round_tripped[key] - nominal[key]) < 1e-6, key


def test_full_angles_to_short_ignores_non_stage_keys():
    entry = {'setting': 'jitter0', 'jitter_config': 0, 'jitter_h1_deg': 0.0, 'HWP_IN': 1.0}
    assert m._full_angles_to_short(entry) == {}


def test_measurement_with_fixed_waveplate_angles_skips_set_unitary(monkeypatch):
    """The regression this file exists for: fixed_waveplate_angles must be
    what actually reaches the hardware, not get reset to N's nominal unitary
    a moment later."""
    calls = []
    monkeypatch.setattr(m, '_set_unitary', lambda N: calls.append(('nominal', N)) or {})
    monkeypatch.setattr(m, '_set_fixed_waveplates',
                         lambda angles, path=None: calls.append(('custom', dict(angles))) or {})

    custom = {'h1': 12.3}
    m.measurement('3', js=[0], duration_s=0.01, auto=True, fixed_waveplate_angles=custom)

    assert calls == [('custom', custom)], \
        "measurement() must use fixed_waveplate_angles, not also/instead call _set_unitary(N)"


def test_jitter_then_measure_picks_lowest_kl_and_passes_its_angles(monkeypatch):
    angle_log = [
        {'setting': 's0'},
        {'setting': 'jitter0', 'jitter_config': 0, 'HWP_1': 10.0, 'QWP_1': 0.0},
        {'setting': 'jitter1', 'jitter_config': 1, 'HWP_1': 99.0, 'QWP_1': 0.0},
    ]
    config_kls = {0: 0.9, 1: 0.1}  # config 1 is the better (lower) KL

    monkeypatch.setattr(m, 'jitter_unitary_measurement',
                         lambda *a, **kw: ([], config_kls, angle_log))
    seen = []
    monkeypatch.setattr(m, 'measurement', lambda *a, **kw: seen.append(kw.get('fixed_waveplate_angles')))

    chosen, kls = m.jitter_then_measure('3', n_best=1, sall_duration_s=1, auto=True)

    assert chosen == [1]
    assert kls == config_kls
    assert seen == [m._full_angles_to_short({'HWP_1': 99.0, 'QWP_1': 0.0})]


if __name__ == '__main__':
    test_full_angles_to_short_round_trips()
    test_full_angles_to_short_ignores_non_stage_keys()
    print('test_jitter_then_measure (sans monkeypatch cases): ok')
