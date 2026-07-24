"""Regression check for the R/L swap bug: _set_tomo_stages (measurement.py)
must analyze with tomo_angles, not basis_angles, or R and L get swapped."""
import numpy as np
from libraries.basis_vectors import basis_angles, tomo_angles
from libraries.optics import HWP, QWP

H = np.array([[1], [0]], dtype=complex)
R = (H - 1j * np.array([[0], [1]], dtype=complex)) / np.sqrt(2)
L = (H + 1j * np.array([[0], [1]], dtype=complex)) / np.sqrt(2)


def _analyzed_state(hwp_ang, qwp_ang):
    op = HWP(hwp_ang) @ QWP(qwp_ang)
    phi = np.conjugate(op).T @ H
    return phi / np.linalg.norm(phi)


def test_tomo_angles_r_and_l_are_not_swapped():
    r_phi = _analyzed_state(*tomo_angles['R'])
    l_phi = _analyzed_state(*tomo_angles['L'])
    assert np.isclose(abs(np.vdot(R, r_phi)) ** 2, 1.0, atol=1e-6)
    assert np.isclose(abs(np.vdot(L, l_phi)) ** 2, 1.0, atol=1e-6)


def test_basis_angles_would_swap_r_and_l():
    """Documents why _set_tomo_stages can't use basis_angles: this is the bug."""
    r_phi = _analyzed_state(*basis_angles['R'])
    l_phi = _analyzed_state(*basis_angles['L'])
    assert np.isclose(abs(np.vdot(L, r_phi)) ** 2, 1.0, atol=1e-6)
    assert np.isclose(abs(np.vdot(R, l_phi)) ** 2, 1.0, atol=1e-6)
