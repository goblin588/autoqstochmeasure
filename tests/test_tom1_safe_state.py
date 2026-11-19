"""Regression check for _tom1_safe_state: which polarization (H or V)
actually arrives at TOM_1's real downstream PBS for each loop channel's
peak-optics preset. Two wrong fixed guesses already shipped in this file's
history (commit df483c0 forced V and silently blocked ch6; the fix after
it forced H and silently blocked ch4/8/10/12/14) -- this locks in the
Jones-matrix-derived answer instead of a guess.

ch4/ch6 (_TOM_1_CLOSED_FORM_STATE) are independently re-derived here
straight from plotting.getUnitary, the same way tests/test_loop_exit_split.py
verifies the 50/50 split, so that dict can't silently drift from what
_set_bypass_optics/_set_loop_optics actually do."""
import os
import sys

os.environ.setdefault('AUTOTOMO_SIM', '1')
os.environ.setdefault('DUMP_ENABLED', '0')
sys.path.insert(0, 'src')

import numpy as np

import measurement as m
from libraries.basis_vectors import basis_vectors
from libraries.plotting import getUnitary

M1, M2, M3 = 3.16, 3.77, 3.74


def _as_vec4(x):
    return np.asarray(x, dtype=complex).reshape(4, 1)


def test_ch4_bypass_delivers_pure_v_to_tom1():
    # _set_bypass_optics: input H, HWP_12=45/QWP_12=0, one pass, exit immediately.
    U = getUnitary(h2=45, q2=0, path=1, m1=M1, m2=M2, m3=M3)
    out = _as_vec4(U @ _as_vec4(basis_vectors['H']))
    h_amp, v_amp = out[0, 0], out[1, 0]
    assert abs(h_amp) ** 2 < 1e-6
    assert abs(v_amp) ** 2 > 0.99
    assert m._TOM_1_CLOSED_FORM_STATE[4] == 'V'


def test_ch6_loop_delivers_pure_h_to_tom1():
    # _set_loop_optics: input H, HWP_OUT_2=45/0 flips H->V for the loop,
    # HWP_1=45/0 (fixed, same stationary plate both passes) routes it out.
    pass1 = getUnitary(h1=45, q1=0, h2=0, q2=0, hf2=45, qf2=0, path=1, m1=M1, m2=M2, m3=M3)
    out1 = _as_vec4(pass1 @ _as_vec4(basis_vectors['H']))
    continuing = np.zeros((4, 1), dtype=complex)
    continuing[2, 0], continuing[3, 0] = out1[2, 0], out1[3, 0]
    pass2 = getUnitary(h1=45, q1=0, h2=0, q2=0, hf2=0, qf2=0, path=1, m1=M1, m2=M2, m3=M3)
    out2 = _as_vec4(pass2 @ continuing)
    h_amp, v_amp = out2[0, 0], out2[1, 0]
    assert abs(v_amp) ** 2 < 1e-6
    assert abs(h_amp) ** 2 > 0.99
    assert m._TOM_1_CLOSED_FORM_STATE[6] == 'H'


def test_loop_channels_safe_state_matches_current_presets():
    # ch8/10/12/14 are computed live from unitaries_angles/process_state_angles
    # (not hardcoded) -- this just locks in what that computation currently
    # returns, so a future preset change that flips the answer is visible
    # here instead of silently blocking signal on the bench.
    for ch in (4, 6, 8, 10, 12, 14):
        assert m._tom1_safe_state(ch) in ('H', 'V')
    assert [m._tom1_safe_state(ch) for ch in (4, 6, 8, 10, 12, 14)] == \
        ['V', 'H', 'V', 'V', 'V', 'V']


if __name__ == '__main__':
    print('test_tom1_safe_state needs pytest -- run via pytest.')
