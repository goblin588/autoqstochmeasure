
"""
Hardware settings
"""

import os
from pathlib import Path

class Waveplate:
    def __init__(self, id, oa=0):
        self.ID = id
        self.OA = oa

    def setOA(self, oa):
        self.OA = oa

COMPORT = 'COM6'
SIM_MODE = os.environ.get('AUTOTOMO_SIM', '0') == '1'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = PROJECT_ROOT / "data" / "Figures"

# OPTICAL AXIS
qwp_in_oa = 3
hwp_in_oa = 54.57 + 45  # +45: true input polarisation is V, not H (basis_angles assumes H)
qwp_tom_dump_oa = 73
hwp_tom_dump_oa = 35.5
qwp_in_2_oa = 131.32
hwp_in_2_oa = 29.24
hwp_tom_1_oa = 41.5
qwp_tom_1_oa = 107.58
hwp_out_2_oa = 13
qwp_out_2_oa = 12.5


# STAGE NUMBER 
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

# WAVEPLATES
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


# CC DELAY SETTINGS 
DELAY_1 = 0
DELAY_2 = 0
DELAY_3 = 0
DELAY_4 = 0
DELAY_5 = 30
DELAY_6 = 0
DELAY_7 = 0
DELAY_8 = 0

# CC CHANNELS 
TRIGG_CH = 8
DET_CH1 = 1
DET_CH2 = 2
DET_CH3 = 3
DET_CH4 = 4
DET_CH5 = 5


DELAYS = [DELAY_1, DELAY_2, DELAY_3, DELAY_4, DELAY_5, DELAY_6, DELAY_7, DELAY_8]
DET_CHS = [DET_CH3]

SINGLE_DET_CHS = [TRIGG_CH, *DET_CHS]
COINCIDENCE_CHS = [[TRIGG_CH, ch] for ch in DET_CHS] 
COINCIDENCE_WINDOW = 20.0