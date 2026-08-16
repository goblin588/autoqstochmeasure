
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

# Where measurement() / calibrate_background() write their output. Point this
# at a network drive (e.g. r"R:\autoqstochmeasure_data") to save there instead
# of the local, gitignored data/ folder.
DATA_DIR = PROJECT_ROOT / "data"
FIG_DIR = DATA_DIR / "Figures"

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
# Herald on ch3; loop-k "1" outputs on ch2/4/6/8/10/12; dump on ch7.
# Back to the old method again: every run reads every loop channel and lets
# the photon complete all 6 physical loops before dumping, regardless of the
# nominal process N — the dump's delay is just CHANNELS[7]['delay'], fixed
# and tuned like any other channel (see tune_delays). See det_chs_for().
TRIGG_CH = 3
LOOP_CHS = [2, 4, 6, 8, 10, 12]  # loop 1..6
DUMP_CH = 7
CHANNELS = {
    3:  {'delay': 3841, 'threshold': 0.6},  # herald
    2:  {'delay': 2972, 'threshold': 0.4},  # loop 1
    4:  {'delay': 2542, 'threshold': 0.4},  # loop 2
    6:  {'delay': 2108, 'threshold': 0.4},  # loop 3
    8:  {'delay': 1676, 'threshold': 0.4},  # loop 4
    10: {'delay': 1240, 'threshold': 0.4},  # loop 5
    12: {'delay': 810,  'threshold': 0.4},  # loop 6
    7:  {'delay': 790,  'threshold': 0.2},  # dump — parked at dump-after-6 (DUMP_DELAYS[6])
}
# "Dump After" column of the calibration table — dump channel delay if the
# photon is dumped having completed k loops (0 = herald row, straight to
# dump). Only used directly by path-2 tomo (_tomo_path2/check_projector),
# which swaps CHANNELS[DUMP_CH]['delay'] to DUMP_DELAYS[k] for a chosen
# loop count during phase-tuning checks, then restores it. Ordinary stats
# collection ignores this table — the dump is fixed at CHANNELS[DUMP_CH]
# (see tune_delays, menu option 4) regardless of process N.
# DUMP_DELAYS[6]=790 is not yet calibrated — it's a linear extrapolation of
# the ~430 ns/loop step seen in 0-5.
DUMP_DELAYS = {0: 3390, 1: 2954, 2: 2523, 3: 2088, 4: 1656, 5: 1223, 6: 790}

# "Switch Dwell" column — the photon switch's dwell time isn't under this
# program's control, so this is just what to tell the operator to set it to
# by hand before a measurement at process N starts (see measurement()'s
# reminder print). No entry (or "man"/blank in the table) = set manually,
# no calibrated number yet.
SWITCH_DWELL_NS = {2: 125, 3: 210, 4: 300, 5: 390, 6: 480}

THRESHOLDS = {ch: cfg['threshold'] for ch, cfg in CHANNELS.items()}

# Tuned delays saved by countingcard.tune_delays override the defaults above.
# Delete calibration.json to fall back to the hardcoded values.
CAL_FILE = Path(__file__).with_name('calibration.json')
if CAL_FILE.exists():
    _cal = json.loads(CAL_FILE.read_text())
    for _ch, _delay in _cal['channel_delays'].items():
        CHANNELS[int(_ch)]['delay'] = _delay
    for _n, _delay in _cal.get('dump_delays', {}).items():
        DUMP_DELAYS[int(_n)] = _delay

def save_calibration():
    """Persist the current (tuned) delays; loaded over the defaults on import."""
    CAL_FILE.write_text(json.dumps({
        'channel_delays': {ch: cfg['delay'] for ch, cfg in CHANNELS.items()},
        'dump_delays': DUMP_DELAYS,
    }, indent=1))
    print(f"Saved calibration -> {CAL_FILE}")

def delays_for(N=None):
    """Full delay list, every channel fixed (dump included — it's parked at
    dump-after-6, see DUMP_DELAYS). N is accepted (and ignored) so existing
    call sites that still pass a unitary N keep working unchanged."""
    d = [0.0] * max(CHANNELS)
    for ch, cfg in CHANNELS.items():
        d[ch - 1] = cfg['delay']
    return d

def det_chs_for(N=None):
    """All loop channels plus dump — every run reads the full channel set
    now, regardless of process N (accepted and ignored, same as delays_for)."""
    return DET_CHS

DELAYS = delays_for()
DET_CHS = [*LOOP_CHS, DUMP_CH]

SINGLE_DET_CHS = [TRIGG_CH, *DET_CHS]
COINCIDENCE_CHS = [[TRIGG_CH, ch] for ch in DET_CHS]
COINCIDENCE_WINDOW = 2.0  # ns — keep within 1-3; tune_delays sets this to 1.5 ns after tuning
MEASUREMENT_INTEGRATION_S = 1.0  # seconds per row in measurement(); raise if 1 s rows are too noisy

BACKGROUND_OFFSET_NS = 15.0  # off a channel's tuned delay = misses the real photon, counts accidentals only

# Quick background check run automatically at the start of every measurement()
# call (distinct from BACKGROUND_OFFSET_NS/calibrate_background, which is a
# separate deliberate calibration step) — offset is bigger since 15ns can
# still catch the tail of a slow channel's peak.
MEASUREMENT_BG_OFFSET_NS = 20.0
MEASUREMENT_BG_DURATION_S = 10.0

# tune_delays' per-channel integration time (s): later loops lose more photons,
# so their coincidence peak needs longer collection to clear the noise floor.
# Anchored on ch2 (~1.5 s, plenty of signal) and ch12 (~15 s, barely any left);
# the channels between are a linear guess — tune these down/up as real noise
# is observed. Dump (ch7) isn't a loop step so it just uses the flat fallback.
TUNE_INTEGRATION_S = {2: 1.5, 4: 4.2, 6: 6.9, 8: 9.6, 10: 12.3, 12: 15.0}

# measurement()'s default for longer multi-setting runs: above ROUND_ROBIN_THRESHOLD_S
# total, settings (state x basis) are interleaved in ROUND_ROBIN_COLLECTION_TIME_S bins
# instead of run to completion one at a time, so slow drift doesn't bias one setting
# more than another.
ROUND_ROBIN_COLLECTION_TIME_S = 20 * 60
ROUND_ROBIN_THRESHOLD_S = 60 * 60

# ANTILATCH SERVER (detector bias reset over TCP, see detector-antilatch-server/)
# These voltages are what actually get applied on reset — the server ignores its
# own config.py when driven from here. Keep in sync with
# detector-antilatch-server/config.py (the copy deployed on the blue-box PC).
ANTILATCH_HOST = '10.126.251.233'  # blue-box PC
ANTILATCH_PORT = 65201
ANTILATCH_DEVICE_IDS = [0]
ANTILATCH_BIAS_VOLTAGES = [{0: 4.27, 1: 4.22, 2: 0.25, 3: 3.6}]