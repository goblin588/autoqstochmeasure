
"""
Hardware settings
"""

import json
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

# WAVEPLATES: stage number + optical axis (deg)
WAVEPLATES = {
    'HWP_IN':       {'stage': 6,  'oa': 54.57 + 45},  # +45: true input polarisation is V, not H (basis_angles assumes H)
    'QWP_IN':       {'stage': 8,  'oa': 3},
    'HWP_IN_2':     {'stage': 1,  'oa': 29.24},
    'QWP_IN_2':     {'stage': 7,  'oa': 131.32},
    'HWP_TOM_1':    {'stage': 4,  'oa': 41.5},
    'QWP_TOM_1':    {'stage': 9,  'oa': 107.58},
    'HWP_OUT_2':    {'stage': 14, 'oa': 13},
    'QWP_OUT_2':    {'stage': 12, 'oa': 12.5},
    'HWP_TOM_DUMP': {'stage': 11, 'oa': 35.5},
    'QWP_TOM_DUMP': {'stage': 13, 'oa': 73},
}

# Bind each entry as a module-level Waveplate (HWP_IN, QWP_IN, ...) so
# `from libraries.settings import HWP_IN` keeps working everywhere.
for _name, _cfg in WAVEPLATES.items():
    globals()[_name] = Waveplate(_cfg['stage'], _cfg['oa'])


# CC CHANNELS: delay (ns) + input threshold (V) per channel.
# Herald on ch3; loop-k "1" outputs on ch2/4/6/8/10; dump on ch7.
# All delays are fixed regardless of process length now, including the dump
# — it's parked at its max-loop timing instead of switching per N — so every
# loop channel can be measured in one run without knowing the unitary length.
TRIGG_CH = 3
LOOP_CHS = [2, 4, 6, 8, 10]  # loop 1..5
DUMP_CH = 7
CHANNELS = {
    3:  {'delay': 3841, 'threshold': 0.6},  # herald
    2:  {'delay': 2972, 'threshold': 0.6},  # loop 1
    4:  {'delay': 2542, 'threshold': 0.6},  # loop 2
    6:  {'delay': 2110, 'threshold': 0.8},  # loop 3 — 0.6 read 0 singles, reverted pending retest
    8:  {'delay': 1677, 'threshold': 0.8},  # loop 4 — 0.6 read 0 singles, reverted pending retest
    10: {'delay': 1249, 'threshold': 0.8},  # loop 5 — 0.6 read 0 singles, reverted pending retest
    7:  {'delay': 1220, 'threshold': 0.2},  # dump — fixed regardless of N
}

THRESHOLDS = {ch: cfg['threshold'] for ch, cfg in CHANNELS.items()}

# Tuned delays saved by countingcard.tune_delays override the defaults above.
# Delete calibration.json to fall back to the hardcoded values.
CAL_FILE = Path(__file__).with_name('calibration.json')
if CAL_FILE.exists():
    _cal = json.loads(CAL_FILE.read_text())
    for _ch, _delay in _cal['channel_delays'].items():
        CHANNELS[int(_ch)]['delay'] = _delay

def save_calibration():
    """Persist the current (tuned) delays; loaded over the defaults on import."""
    CAL_FILE.write_text(json.dumps({
        'channel_delays': {ch: cfg['delay'] for ch, cfg in CHANNELS.items()},
    }, indent=1))
    print(f"Saved calibration -> {CAL_FILE}")

def delays_for(N=None):
    """Full delay list, every channel fixed. N is accepted (and ignored) so
    existing call sites that still pass a unitary N keep working unchanged."""
    d = [0.0] * max(CHANNELS)
    for ch, cfg in CHANNELS.items():
        d[ch - 1] = cfg['delay']
    return d

DELAYS = delays_for()
DET_CHS = [*LOOP_CHS, DUMP_CH]

SINGLE_DET_CHS = [TRIGG_CH, *DET_CHS]
COINCIDENCE_CHS = [[TRIGG_CH, ch] for ch in DET_CHS]
COINCIDENCE_WINDOW = 2.0  # ns — keep within 1-3; tune_delays' window check recommends a value

# ANTILATCH SERVER (detector bias reset over TCP, see detector-antilatch-server/)
# These voltages are what actually get applied on reset — the server ignores its
# own config.py when driven from here. Keep in sync with
# detector-antilatch-server/config.py (the copy deployed on the blue-box PC).
ANTILATCH_HOST = '10.126.251.233'  # blue-box PC
ANTILATCH_PORT = 65201
ANTILATCH_DEVICE_IDS = [0]
ANTILATCH_BIAS_VOLTAGES = [{0: 4, 1: 4.45, 2: 0.23, 3: 3.45}]