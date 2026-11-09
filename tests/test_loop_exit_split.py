"""Regression check for the 50/50 loop/exit split: HWP_12 (h2) at 22.5 with
everything else at 0 must give an equal path1(exit)/path2(loop) split via
getUnitary; 45 on HWP_12 gives a deterministic all-exit split instead."""
import numpy as np
from libraries.plotting import getUnitary
from libraries.basis_vectors import basis_vectors

Hin = basis_vectors['H']
M1, M2, M3 = 3.16, 3.77, 3.74  # real fixed mirror phases, from the U_3..U_6 presets


def _exit_loop_probs(h2):
    U = getUnitary(h2=h2, m1=M1, m2=M2, m3=M3)
    out = U @ Hin
    p_exit = abs(out[0, 0]) ** 2 + abs(out[1, 0]) ** 2  # path1 -> TOM_1
    p_loop = abs(out[2, 0]) ** 2 + abs(out[3, 0]) ** 2  # path2 -> OUT_2
    return p_exit, p_loop


def test_22_5_degrees_gives_50_50_split():
    p_exit, p_loop = _exit_loop_probs(22.5)
    assert np.isclose(p_exit, 0.5, atol=1e-6)
    assert np.isclose(p_loop, 0.5, atol=1e-6)


def test_45_degrees_gives_deterministic_exit_not_50_50():
    p_exit, p_loop = _exit_loop_probs(45)
    assert np.isclose(p_exit, 1.0, atol=1e-6)
    assert np.isclose(p_loop, 0.0, atol=1e-6)
