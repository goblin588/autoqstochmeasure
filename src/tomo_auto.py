"""
Automated polarisation tomography characterisation.

Requires:
    Thorlabs PM100USB power meter
    SMC100 motor stages (1 input HWP/QWP pair, 1 tomography HWP/QWP pair)

Run with AUTOTOMO_SIM=1 to use mock hardware (no physical connection needed):
    AUTOTOMO_SIM=1 python tomo_auto.py
"""
import datetime
import os
import sys

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'

import libraries.data_processing as dpl
import libraries.plotting as cpl
import libraries.tomography as tl
from libraries.angle_menu import angle_menu
from libraries.basis_vectors import basis_angles
from libraries.settings import (HWP_IN, QWP_IN, QWP_TOM_DUMP, HWP_TOM_DUMP,
                                HWP_IN_2, QWP_IN_2, HWP_OUT_2, QWP_OUT_2,
                                HWP_TOM_1, QWP_TOM_1, COMPORT, SIM_MODE)
from libraries.notifier import notify


def _beep():
    print('\a', end='', flush=True)


def _set_fixed_waveplates(angles):
    """Move any fixed-position waveplates that have non-zero angles set."""
    if angles.get('hin2'):
        print(f"Setting HWP_IN_2 to {angles['hin2']}°")
        tl.move_stage(HWP_IN_2, angles['hin2'], COMPORT)
    if angles.get('qin2'):
        print(f"Setting QWP_IN_2 to {angles['qin2']}°")
        tl.move_stage(QWP_IN_2, angles['qin2'], COMPORT)
    if angles.get('hf2'):
        print(f"Setting HWP_OUT_2 to {angles['hf2']}°")
        tl.move_stage(HWP_OUT_2, angles['hf2'], COMPORT)
    if angles.get('qf2'):
        print(f"Setting QWP_OUT_2 to {angles['qf2']}°")
        tl.move_stage(QWP_OUT_2, angles['qf2'], COMPORT)


def _tomo_stages(path: int):
    if path == 1:
        return HWP_TOM_1, QWP_TOM_1
    return HWP_OUT_2, QWP_OUT_2


def _get_powermeter(wavelength=1550, verbose=True):
    if SIM_MODE:
        from interfaces.mock import MockPowerMeter
        return MockPowerMeter(wavelength=wavelength, verbose=verbose)
    import interfaces.pm100usb as pml
    return pml.PM100USB(wavelength=wavelength, verbose=verbose)


def set_stages(basis_in, basis_out):
    tl.move_stage(HWP_IN,   basis_angles[basis_in.upper()][0],  COMPORT)
    tl.move_stage(QWP_IN,   basis_angles[basis_in.upper()][1],  COMPORT)
    tl.move_stage(HWP_IN_2, basis_angles[basis_out.upper()][0], COMPORT)
    tl.move_stage(QWP_IN_2, basis_angles[basis_out.upper()][1], COMPORT)


def set_stages_loop(basis_in, basis_out):
    tl.move_stage(HWP_IN_2,  -basis_angles[basis_in.upper()][0],  COMPORT)
    tl.move_stage(QWP_IN_2,  -basis_angles[basis_in.upper()][1],  COMPORT)
    tl.move_stage(HWP_OUT_2,  basis_angles[basis_out.upper()][0], COMPORT)
    tl.move_stage(QWP_OUT_2,  basis_angles[basis_out.upper()][1], COMPORT)


def polarisation_tuner():
    mode = input("Polarisation mode — 'input' (IN/IN_2) or 'loop' (IN/TOM_1/OUT_2): ").strip().lower()
    if mode == 'loop':
        _set = set_stages_loop
        print("Loop mode: IN_2 reverses input polarisation (negative angles), OUT_2 selects output basis")
    else:
        _set = set_stages
        print("Input mode: IN sets input, IN_2 sets output basis")

    this_basis = 'H'
    while True:
        print("Press enter to swap basis, type a basis letter (H/V/A/D/R/L), or 'stop' to exit")
        user_input = input()
        if user_input.lower() == 'stop':
            break
        elif user_input.upper() in basis_angles:
            _set(user_input, user_input)
            print(f"Measuring {user_input.upper()} basis")
        else:
            if this_basis == 'D':
                this_basis = 'H'
                _set('H', 'V')
                print("Measuring H in V OUT")
            else:
                this_basis = 'D'
                _set('D', 'A')
                print("Measuring D in A OUT")
        print("READY")
        _beep()


def single_tomo(basis, angles, path: int = 2):
    print(f"Performing tomography for single input basis |{basis}>")
    _set_fixed_waveplates(angles)
    hwp_tom, qwp_tom = _tomo_stages(path)
    tl.move_stage(HWP_IN, basis_angles[basis][0], COMPORT)
    tl.move_stage(QWP_IN, basis_angles[basis][1], COMPORT)
    with _get_powermeter() as pm:
        res = {basis: tl.single_tomography(qwp=qwp_tom, hwp=hwp_tom, powermeter=pm, smc_port=COMPORT)}
    _beep()
    fit = cpl.plot_characterisation(res, graph_title=angles['title'], plot_type='Single', angles=angles, show_plot=True, path=path)
    notify(f"|{basis}⟩ tomo done — fit: {fit:.4f} — {angles['title']}", title="Single tomo complete")


def full_tomo(angles, path: int = 2):
    print("Performing tomography for H, V, A, D input states")
    _set_fixed_waveplates(angles)
    hwp_tom, qwp_tom = _tomo_stages(path)
    with _get_powermeter() as pm:
        res = tl.input_tomography(qwp_tom, hwp_tom, HWP_IN, QWP_IN, pm, COMPORT, bases=tl.HVAD_BASES)
    _beep()
    fit = cpl.plot_characterisation(res, graph_title=angles['title'], angles=angles, plot_type='Full', show_plot=False, path=path)
    notify(f"HVAD tomo done — fit: {fit:.4f} — {angles['title']}", title="Full tomo complete", priority="high")


def full6_tomo(angles, path: int = 2):
    print("Performing tomography for all 6 input states (H, V, A, D, R, L)")
    _set_fixed_waveplates(angles)
    hwp_tom, qwp_tom = _tomo_stages(path)
    with _get_powermeter() as pm:
        res = tl.input_tomography(qwp_tom, hwp_tom, HWP_IN, QWP_IN, pm, COMPORT, bases=tl.FULL_BASES)
    _beep()
    fit = cpl.plot_characterisation(res, graph_title=angles['title'], angles=angles, plot_type='Full6', show_plot=False, path=path)
    notify(f"HVADRL tomo done — fit: {fit:.4f} — {angles['title']}", title="Full 6 tomo complete", priority="high")


def hv_tomo(angles, path: int = 2):
    print("Performing tomography for H and V input states")
    _set_fixed_waveplates(angles)
    hwp_tom, qwp_tom = _tomo_stages(path)
    with _get_powermeter() as pm:
        res = tl.input_tomography(qwp_tom, hwp_tom, HWP_IN, QWP_IN, pm, COMPORT, bases=tl.HV_BASES)
    _beep()
    fit = cpl.plot_characterisation(res, graph_title=angles['title'], angles=angles, plot_type='HV', show_plot=True, path=path)
    notify(f"HV tomo done — fit: {fit:.4f} — {angles['title']}", title="HV tomo complete")


def multi_run(angles, path: int = 2):
    n = int(input("Collect how many measurements?: "))
    _set_fixed_waveplates(angles)
    hwp_tom, qwp_tom = _tomo_stages(path)
    res_out = {}
    with _get_powermeter() as pm:
        try:
            for i in range(n):
                print(f"Performing measurement {i + 1}/{n}...")
                res_out[i] = tl.input_tomography(qwp_tom, hwp_tom, HWP_IN, QWP_IN, pm, COMPORT, bases=tl.HVAD_BASES)
                notify(f"Run {i + 1}/{n} done — {angles['title']}", title="Multi-run progress")
        except Exception as e:
            print(f"Measurement failed: {e}")
            notify(f"Measurement failed at run {len(res_out)}/{n}: {e}", title="autotomo error", priority="urgent")

    _beep()
    notify(f"All {n} runs complete — {angles['title']}", title="Multi-run complete", priority="high")

    for i in res_out:
        cpl.plot_characterisation(res_out[i], graph_title=angles['title'], angles=angles,
                                  plot_type=f'{i}_Multi', save_data=False, save_plot=False, show_plot=False, path=path)

    norm_data = {i: cpl.normalise_full_tomo_data(res_out[i]) for i in res_out}
    filepath = datetime.datetime.now().strftime("Figures/Figures_%Y-%m-%d/%Y-%m-%d__%H-%M/")
    filepath += f"{angles['title']}_ITERATIONS"
    cpl.writeData2File(filename=filepath, data=res_out, normalised_data=norm_data, angles=angles, plot_type='Multi')


def replot(angles, path: int = 2):
    filepath = input("Path to data CSV: ").strip()
    try:
        data = dpl.load_csv_data(filepath)
        avg_data = dpl.average_measurements(data['raw_data'])
        cpl.plot_characterisation(avg_data, f"Replot — {angles['title']}", angles=angles, path=path)
    except Exception as e:
        print(f"Error loading data: {e}")


def main():
    if SIM_MODE:
        print("[SIM MODE] Running without hardware")

    print("Automated Tomography Characterisation")
    angles = angle_menu()

    _p = input("Output path [1/2, default 2]: ").strip()
    path = 1 if _p == '1' else 2

    run = True
    while run:
        choice = input(
            "Mode?\n"
            "  H/V/A/D/R/L  — single basis tomo\n"
            "  HV            — H + V only\n"
            "  F             — HVAD (4 input states)\n"
            "  6             — HVADRL (all 6 input states)\n"
            "  M             — multi-run\n"
            "  T             — polarisation tuner\n"
            "  R             — replot saved data\n"
            "> "
        ).upper()

        if choice in ['H', 'V', 'A', 'D', 'R', 'L']:
            single_tomo(choice, angles, path)
            run = False
        elif choice == 'HV':
            hv_tomo(angles, path)
            run = False
        elif choice == 'F':
            full_tomo(angles, path)
            run = False
        elif choice == '6':
            full6_tomo(angles, path)
            run = False
        elif choice == 'M':
            multi_run(angles, path)
            run = False
        elif choice == 'T':
            polarisation_tuner()
            run = False
        elif choice == 'R':
            replot(angles, path)
            run = False
        else:
            print("Valid inputs: H, V, A, D, R, L, HV, F, 6, M, T, R")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
