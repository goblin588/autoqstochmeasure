"""
Manually set waveplate stage pairs to a named basis or specific angles.
"""
import libraries.tomography as tl
from libraries.basis_vectors import basis_angles
from libraries.settings import (HWP_IN, QWP_IN, HWP_IN_2, QWP_IN_2,
                                 HWP_TOM_DUMP, QWP_TOM_DUMP,
                                 HWP_TOM_1, QWP_TOM_1, HWP_OUT_2, QWP_OUT_2,
                                 COMPORT, Waveplate)

_PAIRS = {
    'in':   (HWP_IN,    QWP_IN,    "Input     (HWP_IN   / QWP_IN)"),
    'in2':  (HWP_IN_2,  QWP_IN_2,  "Input 2   (HWP_IN_2 / QWP_IN_2)"),
    'dump': (HWP_TOM_DUMP, QWP_TOM_DUMP, "Tomo dump (HWP_TOM_DUMP / QWP_TOM_DUMP)"),
    'tom1': (HWP_TOM_1, QWP_TOM_1, "Tomo 1    (HWP_TOM_1 / QWP_TOM_1)"),
    'out2': (HWP_OUT_2, QWP_OUT_2, "Output 2  (HWP_OUT_2 / QWP_OUT_2)"),
}

# Map stage ID → Waveplate so OA can be applied when addressing by number
_STAGE_MAP: dict[int, Waveplate] = {
    wp.ID: wp
    for _, (hwp, qwp, _) in _PAIRS.items()
    for wp in (hwp, qwp)
}


def _beep():
    print('\a', end='', flush=True)


def _move_pair(hwp, qwp, basis):
    tl.move_stage(hwp, basis_angles[basis][0], COMPORT)
    tl.move_stage(qwp, basis_angles[basis][1], COMPORT)
    print(f"  Set to |{basis}⟩  (HWP={basis_angles[basis][0]:.2f}°, QWP={basis_angles[basis][1]:.2f}°)")


def _set_pair_interactive(hwp, qwp, label):
    val = input(f"  {label}\n  Basis (H/V/A/D/R/L) or 'manual': ").strip().upper()
    if val in basis_angles:
        _move_pair(hwp, qwp, val)
    elif val == 'MANUAL':
        hwp_angle = float(input("    HWP angle (deg): "))
        qwp_angle = float(input("    QWP angle (deg): "))
        tl.move_stage(hwp, hwp_angle, COMPORT)
        tl.move_stage(qwp, qwp_angle, COMPORT)
        print(f"  Set to HWP={hwp_angle:.2f}°, QWP={qwp_angle:.2f}°")
    else:
        print("  Unrecognised — skipping.")


def _set_by_number():
    """Move a single stage by its ID number, applying OA if the stage is known."""
    stage_id = input("  Stage number: ").strip()
    try:
        stage_id = int(stage_id)
    except ValueError:
        print("  Invalid stage number.")
        return
    angle = input("  Angle (deg): ").strip()
    try:
        angle = float(angle)
    except ValueError:
        print("  Invalid angle.")
        return
    wp = _STAGE_MAP.get(stage_id, Waveplate(stage_id, 0))
    tl.move_stage(wp, angle, COMPORT)
    oa_note = f" (OA={wp.OA:.2f}° applied → {angle + wp.OA:.2f}°)" if wp.OA else ""
    print(f"  Stage {stage_id} → {angle:.2f}°{oa_note}")


def main():
    val = input("Input basis (H/V/A/D/R/L), 'set' for stage pair menu, or 'num' for stage by number: ").strip().upper()

    if val in basis_angles:
        _move_pair(HWP_IN, QWP_IN, val)
        tom = input("Tom basis (H/V/A/D/R/L): ").strip().upper()
        if tom in basis_angles:
            _move_pair(HWP_TOM_DUMP, QWP_TOM_DUMP, tom)
        else:
            print("Unrecognised tom basis — skipping.")

    elif val == 'SET':
        print("Stage pairs:  in  |  in2  |  dump  |  tom1  |  out2  |  all")
        while True:
            choice = input("Which pair? (or Enter to finish): ").strip().lower()
            if choice in ('', 'done'):
                break
            elif choice == 'all':
                for hwp, qwp, label in _PAIRS.values():
                    _set_pair_interactive(hwp, qwp, label)
            elif choice in _PAIRS:
                hwp, qwp, label = _PAIRS[choice]
                _set_pair_interactive(hwp, qwp, label)
            else:
                print("  Options: in, in2, dump, tom1, out2, all")

    elif val == 'NUM':
        while True:
            _set_by_number()
            again = input("  Set another? (y/n): ").strip().lower()
            if again != 'y':
                break

    else:
        print("Unrecognised input.")

    _beep()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
