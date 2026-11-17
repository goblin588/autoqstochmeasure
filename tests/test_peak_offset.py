"""Regression check for _peak_offset's parabolic sub-step interpolation --
makes sure it actually pulls the estimate toward a real off-grid peak
instead of just returning the raw argmax bin, while staying safe on edges
and flat/degenerate scans."""
import numpy as np

from libraries.countingcard import _peak_offset


def test_symmetric_peak_stays_on_grid():
    offsets = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    counts = np.array([0.0, 8.0, 10.0, 8.0, 0.0])  # true peak exactly at offset 0
    offset, idx = _peak_offset(counts, offsets, step=1.0)
    assert idx == 2
    assert offset == 0.0


def test_asymmetric_peak_interpolates_toward_true_peak():
    offsets = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    # tent peaking at true offset +0.5 (between the +0 and +1 bins) -- the
    # raw argmax bin (idx=2, offset=0) undershoots it
    counts = np.array([0.0, 5.0, 9.5, 9.5, 0.0])
    offset, idx = _peak_offset(counts, offsets, step=1.0)
    assert idx == 2  # raw bin is a tie between idx 2 and 3; argmax picks the first
    assert offset > 0.0  # interpolation correctly shifts toward the true peak


def test_edge_peak_has_no_neighbour_to_fit_falls_back_to_raw():
    offsets = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    counts = np.array([10.0, 8.0, 5.0, 2.0, 0.0])  # peak sits at the left edge
    offset, idx = _peak_offset(counts, offsets, step=1.0)
    assert idx == 0
    assert offset == offsets[0]


def test_flat_top_has_zero_curvature_falls_back_to_raw():
    offsets = np.array([-1.0, 0.0, 1.0])
    counts = np.array([5.0, 5.0, 5.0])  # no curvature -- denom == 0
    offset, idx = _peak_offset(counts, offsets, step=1.0)
    assert offset == offsets[idx]  # no crash, no interpolation attempted


if __name__ == "__main__":
    test_symmetric_peak_stays_on_grid()
    test_asymmetric_peak_interpolates_toward_true_peak()
    test_edge_peak_has_no_neighbour_to_fit_falls_back_to_raw()
    test_flat_top_has_zero_curvature_falls_back_to_raw()
    print("test_peak_offset: ok")
