"""
Check homing status of all known stages and home as needed.
"""
import os
import sys

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'

from libraries.settings import (
    HWP_IN, QWP_IN, HWP_IN_2, QWP_IN_2,
    HWP_TOM_1, QWP_TOM_1, HWP_OUT_2, QWP_OUT_2,
    HWP_TOM_DUMP, QWP_TOM_DUMP, SIM_MODE, COMPORT
)

ALL_STAGES = {
    HWP_IN.ID:       'HWP_IN',
    QWP_IN.ID:       'QWP_IN',
    HWP_IN_2.ID:     'HWP_IN_2',
    QWP_IN_2.ID:     'QWP_IN_2',
    HWP_TOM_1.ID:    'HWP_TOM_1',
    QWP_TOM_1.ID:    'QWP_TOM_1',
    HWP_OUT_2.ID:    'HWP_OUT_2',
    QWP_OUT_2.ID:    'QWP_OUT_2',
    HWP_TOM_DUMP.ID: 'HWP_TOM_DUMP',
    QWP_TOM_DUMP.ID: 'QWP_TOM_DUMP',
}

_NOT_REFERENCED = {'0A', '0B', '0C', '0D', '0E', '0F', '10', '11'}


def _get_state(sid):
    import interfaces.smc100 as smc
    with smc.SMC100Connection(port=COMPORT) as conn:
        stage = smc.SMC100Stage(conn, smcID=sid)
        _, state = stage.get_status()
    return state


def _home_stage(sid):
    import interfaces.smc100 as smc
    with smc.SMC100Connection(port=COMPORT) as conn:
        stage = smc.SMC100Stage(conn, smcID=sid)
        stage.enable()
        stage.home(waitStop=True)
        stage.disable()


def main():
    if SIM_MODE:
        print("[SIM MODE]")
        unhomed = list(ALL_STAGES.keys())
    else:
        print("Checking stage homing status...")
        unhomed = [sid for sid, name in ALL_STAGES.items()
                   if _get_state(sid) in _NOT_REFERENCED]

    if not unhomed:
        print("All stages are homed.")
        return

    print("\nStages not homed:")
    for sid in unhomed:
        print(f"  {sid}: {ALL_STAGES[sid]}")

    choice = input("\nEnter stage number to home, or press Enter to home all: ").strip()

    if choice == '':
        to_home = unhomed
    else:
        try:
            sid = int(choice)
        except ValueError:
            print("Invalid input.")
            return
        if sid not in ALL_STAGES:
            print(f"Stage {sid} not recognised.")
            return
        to_home = [sid]

    for sid in to_home:
        name = ALL_STAGES[sid]
        print(f"  Homing stage {sid} ({name})...")
        if not SIM_MODE:
            _home_stage(sid)
        print(f"  Stage {sid} ({name}) homed.")

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
