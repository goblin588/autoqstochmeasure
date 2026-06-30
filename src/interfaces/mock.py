"""
Simulation stand-ins for SMC100 motor stages and the Thorlabs PM100USB.

Run with AUTOTOMO_SIM=1 (or pass --sim at the entry point) to use these
instead of opening real serial / USB connections.
"""

import numpy as np


class MockSMC100Connection:
    """Context manager that mimics SMC100Connection without touching serial."""

    _silent = True
    _port = None

    def __init__(self, port='MOCK', **kwargs):
        self.COMport = port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockSMC100Stage:
    """Tracks commanded positions in memory instead of moving hardware."""

    _positions: dict[str, float] = {}

    def __init__(self, parent, smcID):
        self._smcID = str(smcID)

    def enable(self):
        pass

    def disable(self):
        pass

    def move_absolute(self, position, waitStop=True, retry=True):
        MockSMC100Stage._positions[self._smcID] = position
        print(f'[SIM] Stage {self._smcID} → {position:.3f}°')

    def get_position(self):
        return MockSMC100Stage._positions.get(self._smcID, 0.0)


class MockPowerMeter:
    """Returns plausible-looking noise around a fixed power level."""

    def __init__(self, wavelength=1550, verbose=False, baseline_W=1e-3):
        self._baseline = baseline_W
        if verbose:
            print(f'[SIM] MockPowerMeter initialised (λ={wavelength} nm, P₀={baseline_W*1e3:.1f} mW)')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, n=30):
        samples = self._baseline + np.random.normal(0, self._baseline * 0.01, n)
        return float(np.mean(samples)), float(np.std(samples, ddof=1))

    def close(self):
        pass