"""
Prepare the s0 process state for a chosen unitary N:
sets HWP_IN/QWP_IN to s0_N and the fixed waveplates (IN_2/OUT_2) to that U's angles.

Run with AUTOTOMO_SIM=1 or --sim for mock hardware.
"""
import os
import sys
import datetime

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'

import libraries.tomography as tl
from libraries.basis_vectors import process_state_angles, basis_angles
from libraries.settings import HWP_IN, QWP_IN, COMPORT, SIM_MODE
from libraries.waveplate_angles import unitaries_angles
from libraries.settings import (HWP_IN, QWP_IN, QWP_TOM_DUMP, HWP_TOM_DUMP,
                                HWP_IN_2, QWP_IN_2, HWP_OUT_2, QWP_OUT_2,
                                HWP_TOM_1, QWP_TOM_1, COMPORT, SIM_MODE)
from libraries.notifier import notify


def _set_fixed_waveplates(angles, path=None):
    """Move any fixed-position waveplates that have non-zero angles set.

    The analyzer pair for `path` (TOM_1 for path 1, OUT_2 for path 2) is
    skipped — the tomo sweep drives it. path=None sets all pairs.
    """
    plates = [
        ('hin2', 'HWP_IN_2',  HWP_IN_2),
        ('qin2', 'QWP_IN_2',  QWP_IN_2),
        ('hf2',  'HWP_OUT_2', HWP_OUT_2),
        ('qf2',  'QWP_OUT_2', QWP_OUT_2),
        ('hf1',  'HWP_TOM_1', HWP_TOM_1),
        ('qf1',  'QWP_TOM_1', QWP_TOM_1),
    ]
    skip = {1: ('hf1', 'qf1'), 2: ('hf2', 'qf2')}.get(path, ())
    for key, name, stage in plates:
        if key in skip or angles.get(key) is None:
            continue
        print(f"Setting {name} to {angles[key]}°")
        tl.move_stage(stage, angles[key], COMPORT)

# TOMO STAGES IN PATH1 ARE TOM1 IN PATH2 THEY ARE DUMP WE ARE USING BOTH ALWAYS

def set_unitary_and_s0():
    hwp_angle, qwp_angle = process_state_angles[f's0_{N}']
    print(f"Setting HWP_IN to {hwp_angle}°, QWP_IN to {qwp_angle}° (s0_{N})")
    tl.move_stage(HWP_IN, hwp_angle, COMPORT)
    tl.move_stage(QWP_IN, qwp_angle, COMPORT)

    _set_fixed_waveplates(unitaries_angles[N])
    _beep()
    print("READY")

def measurement(N, performTomo=False):
    # Set unitary 
    set_unitary_and_s0(N)

    # if tomo them set plates
    if performTomo:
        pass


    notify(f"Measurement completed", title="Measurement Complete", priority="high")


def main():
    if SIM_MODE:
        print("[SIM MODE] Running without hardware")

    run1 = True

    while run1:
        try:
            N = input(f"Which unitary N? ({'/'.join(unitaries_angles)}): ").strip()
            if N not in unitaries_angles:
                raise ValueError(f"No unitary for N={N}")
            run1 = False
        except:
            print("Invalid unitary choice")


    run = True 
    while run:
        n = input(
            "Do you want to:\n"
            "\t1. Set unitary and s0 input state\n"
            "\t2. Collect statistics wihtout tomo\n"
            "\t3. Collect statistics with output tomo\n"
            f"\t4. Collect statistics for each input s{N}_n\n"
            )
            
        match n:
            case '1':
                set_unitary_and_s0(N)
            case '2':
                measurement(N)
            case '3':
                measurement(N, performTomo=True)
            case '4':
                pass
            case _:
                print("Please choose a valid option 1-4 from list:") 


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
