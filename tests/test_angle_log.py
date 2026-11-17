"""Regression check for measurement.py's angle logging: every waveplate
move made during measurement() should end up recorded, with its CONFIRMED
(read-back) angle, in the saved sidecar JSON -- not just assumed from the
angle table. Runs entirely in AUTOTOMO_SIM mode (mock stages), set before
any libraries import so the mock interfaces are the ones loaded."""
import json
import os
import sys

os.environ.setdefault('AUTOTOMO_SIM', '1')
os.environ.setdefault('DUMP_ENABLED', '0')
sys.path.insert(0, 'src')

import measurement as m


def test_set_unitary_returns_confirmed_angles():
    confirmed = m._set_unitary('3')
    assert confirmed  # at least one fixed waveplate has a non-null angle for U3
    assert all(isinstance(v, float) for v in confirmed.values())


def test_set_input_state_returns_confirmed_angles():
    confirmed = m._set_input_state('3', 0)
    assert set(confirmed) == {'HWP_IN', 'QWP_IN'}


def test_apply_setting_merges_input_and_tomo_angles():
    confirmed = m._apply_setting('3', 0, 'H')
    assert set(confirmed) == {
        'HWP_IN', 'QWP_IN', 'HWP_TOM_1', 'QWP_TOM_1', 'HWP_TOM_DUMP', 'QWP_TOM_DUMP',
    }

    # basis=None (no tomo sweep) -- only the input-state angles
    confirmed_no_tomo = m._apply_setting('3', 0, None)
    assert set(confirmed_no_tomo) == {'HWP_IN', 'QWP_IN'}


def test_save_results_embeds_angle_log(tmp_path, monkeypatch):
    monkeypatch.setattr(m.st, 'DATA_DIR', str(tmp_path))
    angle_log = [
        {'setting': 'unitary', 'hin2': 1.0},
        {'setting': 's0', 'input_state': 0, 'basis': None, 'HWP_IN': 2.0, 'QWP_IN': 3.0},
    ]
    m._save_results([{'N': '3', 'int_time': 1.0}], '3', 0, angles=angle_log)

    [json_file] = tmp_path.glob('*_measurement_N3_s0.json')
    saved = json.loads(json_file.read_text())
    assert saved['angles'] == angle_log


if __name__ == '__main__':
    test_set_unitary_returns_confirmed_angles()
    test_set_input_state_returns_confirmed_angles()
    test_apply_setting_merges_input_and_tomo_angles()
    print('test_angle_log (sans tmp_path cases): ok')
