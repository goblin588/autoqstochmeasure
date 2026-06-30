"""
Functions associated with Tomography control / movement of stages.
"""

from libraries.basis_vectors import basis_angles
from libraries.settings import SIM_MODE
import time

if SIM_MODE:
    from interfaces.mock import MockSMC100Connection as _Connection, MockSMC100Stage as _Stage
else:
    import interfaces.smc100 as _smc
    _Connection = _smc.SMC100Connection
    _Stage = _smc.SMC100Stage

# Named basis sets for use by callers
HV_BASES   = ('H', 'V')
HVAD_BASES = ('H', 'V', 'A', 'D')
FULL_BASES = ('H', 'V', 'A', 'D', 'R', 'L')


def input_tomography(qwp, hwp, hwp_in, qwp_in, powermeter, smc_port,
                     bases: tuple = HVAD_BASES) -> dict:
    """
    Perform single_tomography for each input basis in bases.
    Returns {basis: {output_state: (power, err)}}.
    """
    res = {}
    for basis in bases:
        print(f"Setting New Input Basis : |{basis}>")
        move_stage(hwp_in, basis_angles[basis][0], smc_port)
        move_stage(qwp_in, basis_angles[basis][1], smc_port)
        res[basis] = single_tomography(qwp, hwp, powermeter, smc_port)
    return res


def single_tomography(qwp, hwp, powermeter, smc_port) -> dict:
    """Measure all 6 output states (HVADRL) for the current input state."""
    res = {}
    for basis in FULL_BASES:
        print(f"Measuring Output |{basis}>, HWP: {basis_angles[basis][0]}, QWP: {basis_angles[basis][1]}")
        move_stage(hwp, basis_angles[basis][0], smc_port)
        move_stage(qwp, basis_angles[basis][1], smc_port)
        time.sleep(0.1)
        pwr, err = powermeter.read(n=300)
        print(f"Power: {round(pwr * 1000, 2)} mW")
        res[basis] = (pwr, err)
    return res


def move_stage(this_stage, angle: float, smc_port: str) -> None:
    with _Connection(port=smc_port) as stages:
        stage = _Stage(stages, smcID=this_stage.ID)
        stage.enable()
        try:
            stage.move_absolute(angle + this_stage.OA)
        finally:
            stage.disable()
