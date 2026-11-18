"""Regression check for _set_loop{3,4,5,6}_optics: each config's hardcoded
angles must actually reproduce the exit-probability peak its own docstring
claims. (The angles previously in loop3/loop4 didn't -- this would have
caught that.)

Multi-pass recirculation model: getUnitary(path=1, ...) gives one full loop
traversal with OUT_2 (hf2/qf2) already applied to the continuing beam (it
acts only on path2 slots) -- confirmed against the three existing
closed-form configs (_set_bypass_optics/_set_loop_optics/_set_5050_optics)
before trusting it on anything numerically optimized. See
test_loop_exit_split.py for the single-pass path1/path2 convention this
builds on.
"""
import numpy as np
from libraries.plotting import getUnitary
import libraries.optics as ol

M1, M2, M3 = 3.16, 3.77, 3.74  # real fixed mirror phases, from the U_3..U_6 presets


def _full_pass(h1, q1, h2, q2, hf2, qf2):
    return getUnitary(h1=h1, q1=q1, h2=h2, q2=q2, hf2=hf2, qf2=qf2,
                       hin2=0, qin2=0, m1=M1, m2=M2, m3=M3, path=1)


def _input_vec(hwp, qwp):
    H2 = np.array([[1], [0]], dtype=complex)
    v = ol.QWP(qwp) @ ol.HWP(hwp) @ H2
    return np.vstack([np.zeros((2, 1), dtype=complex), v])


def _exit_probs(hwp_in, qwp_in, h1, q1, h2, q2, hf2, qf2, n=6):
    U = _full_pass(h1, q1, h2, q2, hf2, qf2)
    state = _input_vec(hwp_in, qwp_in)
    probs = []
    for _ in range(n):
        out = U @ state
        probs.append(float(abs(out[0, 0]) ** 2 + abs(out[1, 0]) ** 2))
        state = np.array([[0], [0], [out[2, 0]], [out[3, 0]]], dtype=complex)
    return probs


def test_ground_truth_loop0_all_exit_pass1():
    # HWP_12=45/QWP_12=0, everything else 0 -- _set_bypass_optics's config
    probs = _exit_probs(0, 0, 0, 0, 45, 0, 0, 0)
    assert np.isclose(probs[0], 1.0, atol=1e-6)


def test_ground_truth_loop1_all_exit_pass2():
    # HWP_1=45/HWP_OUT_2=45, everything else 0 -- _set_loop_optics's config
    probs = _exit_probs(0, 0, 45, 0, 0, 0, 45, 0)
    assert np.isclose(probs[1], 1.0, atol=1e-6)


def test_ground_truth_5050_geometric_decay():
    # HWP_12=22.5, everything else 0 -- _set_5050_optics's config
    probs = _exit_probs(0, 0, 0, 0, 22.5, 0, 0, 0)
    for i, p in enumerate(probs):
        assert np.isclose(p, 0.5 ** (i + 1), atol=1e-6)


def test_loop3_peaks_at_pass3():
    probs = _exit_probs(139.487, 176.765, 90.000, 90.000, 129.320, 62.933, 47.397, 127.347)
    assert np.argmax(probs) == 2  # pass 3 (0-indexed)
    assert np.isclose(probs[2], 0.4375, atol=1e-3)


def test_loop4_peaks_at_pass4():
    probs = _exit_probs(131.546, 9.471, 90.000, 90.000, 103.672, 148.759, 64.044, 62.087)
    assert np.argmax(probs) == 3
    assert np.isclose(probs[3], 0.3008, atol=1e-3)


def test_loop5_peaks_at_pass5():
    probs = _exit_probs(93.510, 129.214, 73.937, 92.330, 90.001, 90.002, 93.923, 115.389)
    assert np.argmax(probs) == 4
    assert np.isclose(probs[4], 0.1930, atol=1e-3)


def test_loop6_peaks_at_pass6():
    probs = _exit_probs(48.990, 121.052, 90.000, 90.000, 90.000, 66.526, 90.000, 103.077)
    assert np.argmax(probs) == 5
    assert np.isclose(probs[5], 0.1296, atol=1e-3)


if __name__ == '__main__':
    test_ground_truth_loop0_all_exit_pass1()
    test_ground_truth_loop1_all_exit_pass2()
    test_ground_truth_5050_geometric_decay()
    test_loop3_peaks_at_pass3()
    test_loop4_peaks_at_pass4()
    test_loop5_peaks_at_pass5()
    test_loop6_peaks_at_pass6()
    print('test_loop_peak_optics: ok')
