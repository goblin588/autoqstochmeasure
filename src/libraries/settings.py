
"""
Waveplate hardware settings
"""

import os
from pathlib import Path


class Waveplate:
    def __init__(self, id, oa=0):
        self.ID = id
        self.OA = oa

    def setOA(self, oa):
        self.OA = oa

SIM_MODE = os.environ.get('AUTOTOMO_SIM', '0') == '1'

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = PROJECT_ROOT / "data" / "Figures"

qwp_in_oa = 3
hwp_in_oa = 54.57
qwp_tom_dump_oa = 107.58
hwp_tom_dump_oa = 41.50
qwp_in_2_oa = 131.32
hwp_in_2_oa = 29.24
hwp_tom_1_oa = 1
qwp_tom_1_oa = 1
hwp_out_2_oa = 1
qwp_out_2_oa = 1


# STAGES
hwp_in_stage = 6
qwp_in_stage = 8

qwp_in_2_stage = 7
hwp_in_2_stage = 1

hwp_tom_1_stage = 4
qwp_tom_1_stage = 9

hwp_out_2_stage = 14
qwp_out_2_stage = 12

qwp_tom_dump_stage = 13
hwp_tom_dump_stage = 11

QWP_IN   = Waveplate(qwp_in_stage,    qwp_in_oa)
HWP_IN   = Waveplate(hwp_in_stage,    hwp_in_oa)
QWP_TOM_DUMP = Waveplate(qwp_tom_dump_stage, qwp_tom_dump_oa)
HWP_TOM_DUMP = Waveplate(hwp_tom_dump_stage, hwp_tom_dump_oa)
QWP_IN_2 = Waveplate(qwp_in_2_stage,  qwp_in_2_oa)
HWP_IN_2 = Waveplate(hwp_in_2_stage,  hwp_in_2_oa)
HWP_TOM_1 = Waveplate(hwp_tom_1_stage, hwp_tom_1_oa)
QWP_TOM_1 = Waveplate(qwp_tom_1_stage, qwp_tom_1_oa)
HWP_OUT_2 = Waveplate(hwp_out_2_stage, hwp_out_2_oa)
QWP_OUT_2 = Waveplate(qwp_out_2_stage, qwp_out_2_oa)

COMPORT = 'COM6'

