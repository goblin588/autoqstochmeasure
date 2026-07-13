"""
Prepare the s0 process state for a chosen unitary N:
sets HWP_IN/QWP_IN to s0_N and the fixed waveplates (IN_2/OUT_2) to that U's angles.

Run with AUTOTOMO_SIM=1 or --sim for mock hardware.
"""
import csv
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
                                HWP_TOM_1, QWP_TOM_1, COMPORT, SIM_MODE,
                                DET_CHS)
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

def _set_input_state(N, j=0):
    """Set input state j for process N. defaults to s0_N."""
    hwp_angle, qwp_angle = process_state_angles[f's{j}_{N}']
    print(f"Setting HWP_IN to {hwp_angle}°, QWP_IN to {qwp_angle}° (s{j}_{N})")
    tl.move_stage(HWP_IN, hwp_angle, COMPORT)
    tl.move_stage(QWP_IN, qwp_angle, COMPORT)
    print(f"(s{j}_{N}) READY")

def _beep():
    print('\a', end='', flush=True)

def _set_unitary(N):
    _set_fixed_waveplates(unitaries_angles[N])
    _beep()
    print("UNITARY READY")

def _set_tomo_stages(HWP, QWP, basis):
    """ For tomo ordering QWP -> HWP """
    tl.move_stage(HWP, basis_angles[basis][0], COMPORT)
    tl.move_stage(QWP, basis_angles[basis][1], COMPORT)


def _acquire_counts(duration):
    """Integrate counts for `duration` s, return one row of totals."""
    if SIM_MODE:
        return {'herald': 0,
                **{f'singles_ch{ch}': 0 for ch in DET_CHS},
                **{f'coinc_ch{ch}': 0 for ch in DET_CHS},
                'int_time': duration}
    # imported here: hardware.detector loads the TimeTag DLL on import,
    # which doesn't exist in sim mode
    from libraries.countingcard import acquire_counts
    return acquire_counts(duration)

def _save_results(rows, N, label):
    """Write rows to data/measurement_N{N}_s{label}_{timestamp}.csv.

    Called from finally — saves whatever rows exist even mid-sweep.
    """
    if not rows:
        print("No data to save")
        return
    os.makedirs('data', exist_ok=True)
    path = (f"data/measurement_N{N}_s{label}_"
            f"{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows -> {path}")

def _input_states(N):
    """All j's with a defined input state for process N.

    ponytail: read off process_state_angles keys for now — point this at the
    causal model once it exists.
    """
    return sorted(int(k.split('_')[0][1:]) for k in process_state_angles
                  if k.endswith(f'_{N}'))

def measurement(N, performTomo=False, allInputs=False, duration=20.0):
    """Collect statistics through unitary N, one row per acquisition.

    performTomo=False : single acquisition at the current analyzer setting
    performTomo=True  : full 6-basis tomo sweep
    allInputs=False   : s0 input only
    allInputs=True    : repeat for every input state s{j}_N

    Everything goes to one file; rows carry an input_state column (= j).
    Returns the list of result rows so callers can aggregate.
    """
    _set_unitary(N)

    js = _input_states(N) if allInputs else [0]
    bases = ['H', 'V', 'A', 'D', 'R', 'L'] if performTomo else [None]
    rows = []
    try:
        for j in js:
            _set_input_state(N, j)
            for basis in bases:
                if basis is not None:
                    _set_tomo_stages(HWP=HWP_TOM_1, QWP=QWP_TOM_1, basis=basis)
                    _set_tomo_stages(HWP=HWP_TOM_DUMP, QWP=QWP_TOM_DUMP, basis=basis)

                counts = _acquire_counts(duration)
                rows.append({'N': N, 'input_state': j, 'basis': basis,
                             'time': datetime.datetime.now().isoformat(),
                             **counts})
                print(f"[s{j} {basis or 'no-tomo'}] {counts}")
    finally:
        # runs on success, error, or Ctrl-C — partial data still gets saved
        _save_results(rows, N, 'all' if allInputs else 0)
        notify(f"Measurement N={N} done ({len(rows)}/{len(js) * len(bases)} acquisitions)",
               title="Measurement Complete", priority="high")
    return rows


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
            "\t2. Collect statistics without tomo\n"
            "\t3. Collect statistics with output tomo\n"
            f"\t4. Collect statistics for each input s{N}_n\n"
            )

        match n:
            case '1':
                # Set unitary and s0
                _set_unitary(N)
                _set_input_state(N, 0)
            case '2':
                # Statistics 
                measurement(N)
            case '3':
                # Statistics with tomo
                measurement(N, performTomo=True)
            case '4':
                measurement(N, allInputs=True)
            case _:
                print("Please choose a valid option 1-4 from list:") 


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
