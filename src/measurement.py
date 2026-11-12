"""
Prepare the s0 process state for a chosen unitary N:
sets HWP_IN/QWP_IN to s0_N and the fixed waveplates (IN_2/OUT_2) to that U's angles.

Run with AUTOTOMO_SIM=1 or --sim for mock hardware.
Run with DUMP_ENABLED=0 or --no-dump if the dump detector isn't connected.
"""
import csv
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import datetime
import time
from pathlib import Path

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'
if '--no-dump' in sys.argv:
    os.environ['DUMP_ENABLED'] = '0'

import libraries.tomography as tl
import libraries.settings as st
import libraries.plotting as plotting
from libraries.basis_vectors import process_state_angles, basis_angles, tomo_angles
from libraries.settings import HWP_IN, QWP_IN, COMPORT, SIM_MODE
from libraries.waveplate_angles import unitaries_angles
from libraries.settings import (HWP_IN, QWP_IN, QWP_TOM_DUMP, HWP_TOM_DUMP,
                                HWP_IN_2, QWP_IN_2, HWP_OUT_2, QWP_OUT_2,
                                HWP_TOM_1, QWP_TOM_1, HWP_1, QWP_1, HWP_12, QWP_12,
                                COMPORT, SIM_MODE,
                                DET_CHS, LOOP_CHS, DUMP_CH, TRIGG_CH, delays_for,
                                ANTILATCH_HOST, ANTILATCH_PORT)
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
        ('h1',   'HWP_1',     HWP_1),
        ('q1',   'QWP_1',     QWP_1),
        ('h2',   'HWP_12',    HWP_12),
        ('q2',   'QWP_12',    QWP_12),
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

def _set_input_basis(basis):
    """Set input polarisation to a named H/V/A/D/R/L basis (generic gate
    tomography — distinct from _set_input_state's process-specific s_j prep)."""
    hwp_angle, qwp_angle = basis_angles[basis]
    tl.move_stage(HWP_IN, hwp_angle, COMPORT)
    tl.move_stage(QWP_IN, qwp_angle, COMPORT)
    print(f"Input set to |{basis}>")

def _beep():
    print('\a', end='', flush=True)

def _play_tune():
    """A little jingle for long runs finishing. winsound is Windows-only
    stdlib; no-ops silently anywhere else (sim machine, lab PC off Windows)."""
    try:
        import winsound
    except ImportError:
        return
    for freq, ms in [(523, 150), (659, 150), (784, 150), (1046, 300)]:
        winsound.Beep(freq, ms)

def _set_unitary(N):
    _set_fixed_waveplates(unitaries_angles[N])
    _beep()
    print("UNITARY READY")

def _set_tomo_stages(HWP, QWP, basis):
    """ For tomo ordering QWP -> HWP """
    tl.move_stage(HWP, tomo_angles[basis][0], COMPORT)
    tl.move_stage(QWP, tomo_angles[basis][1], COMPORT)


def _sim_row(duration, chs=DET_CHS):
    return {'herald': 0,
            **{f'singles_ch{ch}': 0 for ch in chs},
            **{f'coinc_ch{ch}': 0 for ch in chs},
            'int_time': duration}

def _acquire_counts(duration, N):
    """Integrate counts for `duration` s on every loop channel + dump — the
    photon always runs all 6 loops before dumping, regardless of process N."""
    chs = st.det_chs_for(N)
    if SIM_MODE:
        return _sim_row(duration, chs)
    # imported here: hardware.detector loads the TimeTag DLL on import,
    # which doesn't exist in sim mode
    from libraries.countingcard import acquire_counts
    return acquire_counts(duration, signal_chs=chs, delays=delays_for())

def _acquire_rows(N, total):
    """Yield count rows, each integrated for st.MEASUREMENT_INTEGRATION_S
    seconds, until `total` s are collected (None = until Ctrl-C)."""
    chs = st.det_chs_for(N)
    integration = st.MEASUREMENT_INTEGRATION_S
    if SIM_MODE:
        done = 0.0
        while total is None or done < total:
            yield _sim_row(integration, chs)
            done += integration
        return
    from libraries.countingcard import acquire_rows
    yield from acquire_rows(total, integration=integration, signal_chs=chs, delays=delays_for())

def _bin_rate_mean_std(counts, ch):
    """(mean_hz, std_hz) of ch's coincidence rate across counts['bins'].
    Falls back to a single point estimate with no spread for counts
    recorded before per-bin data existed."""
    bins = counts.get('bins')
    if not bins:
        total_rate = counts[f"coinc_ch{ch}"] / counts['int_time'] if counts['int_time'] else 0.0
        return total_rate, 0.0
    bin_rates = [b[f"coinc_ch{ch}"] / b['int_time'] for b in bins if b['int_time']]
    mean_rate = statistics.mean(bin_rates)
    std_rate = statistics.stdev(bin_rates) if len(bin_rates) > 1 else 0.0
    return mean_rate, std_rate


def _fit_loop_decay(counts, loop_chs=None):
    """Fit log(rate) vs. loop-pass-index (1..6) across every loop channel in
    one _record_all_channels() recording. Returns (ratio_per_pass,
    ratio_err): the measured channel-to-channel count ratio, e.g. ~0.5x the
    real per-pass loss under the 50/50 optics (ideal, lossless 50/50 would
    give exactly 0.5 -- the shortfall below that is the loss).

    Plain least-squares, no numpy -- a straight line through <=6 points
    doesn't need it. None if fewer than 2 channels have a nonzero rate."""
    points = []
    for k, ch in enumerate(loop_chs if loop_chs is not None else st.LOOP_CHS, start=1):
        mean_rate, _ = _bin_rate_mean_std(counts, ch)
        if mean_rate > 0:
            points.append((float(k), math.log(mean_rate)))
    if len(points) < 2:
        return None, None
    n = len(points)
    kbar = sum(k for k, _ in points) / n
    ybar = sum(y for _, y in points) / n
    sxx = sum((k - kbar) ** 2 for k, _ in points)
    sxy = sum((k - kbar) * (y - ybar) for k, y in points)
    slope = sxy / sxx
    ratio = math.exp(slope)
    if n > 2:
        resid_sq = sum((y - (ybar + slope * (k - kbar))) ** 2 for k, y in points)
        s_err = (resid_sq / (n - 2)) ** 0.5
        slope_err = s_err / sxx ** 0.5
        ratio_err = ratio * slope_err
    else:
        ratio_err = 0.0
    return ratio, ratio_err


# Descriptive labels for calibrate_loss's 3 stage keys, used wherever a
# stage summary is shown to a human or embedded in a measurement's JSON.
LOSS_STAGE_LABELS = {
    'loop0': 'zero_loop_output',
    'loop1': 'one_loop',
    '5050':  'fifty_fifty_all_channels',
}


def _git_commit():
    """Best-effort short git commit hash of the running code, for
    reproducibility. None if git isn't available (e.g. not a checkout)."""
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                                cwd=os.path.dirname(os.path.abspath(__file__)),
                                capture_output=True, text=True, timeout=2)
        return result.stdout.strip() or None
    except Exception:
        return None


def _save_results(rows, N, label, background=None):
    """Write rows to data/{timestamp}_measurement_N{N}_s{label}.csv, plus a
    same-named .json sidecar recording the delays/thresholds/etc. in effect
    for the run — so old data stays interpretable after later recalibration.

    background is the row from _acquire_background() taken at the start of
    this run, if any — stored alongside so each measurement carries its own
    accidental-coincidence floor rather than relying only on the separate
    noise_calibration pointer.

    noise_calibration is the *entire* contents of the most recent
    data/*_noise_calibration.json (plus a 'file' key naming it), copied in
    wholesale — the point is that a measurement's own .csv + .json pair is
    self-contained for plotting/analysis, no need to separately resolve and
    open the calibration file. A frozen snapshot taken at save time, not a
    live reference, so rerunning the calibration later can't retroactively
    change what an already-saved measurement recorded.

    loss_calibration carries each stage's {mean_hz, std_hz} under
    descriptive labels (LOSS_STAGE_LABELS), the derived loss figures
    (loss_per_loop_pass[_err], loss_per_loop_pass_5050[_err] — whichever
    calibrate_loss managed to compute), and 'file'. The raw per-bin
    recordings stay in calibrate_loss's own file; a measurement's JSON only
    needs the summary. loop0/loop1 each have one representative channel;
    '5050' doesn't (it records every loop channel in one go), so its
    summary is {ch: {mean_hz, std_hz}} per channel instead of a single
    rate.

    Timestamp leads so filenames sort most-recent-last (ls default order).
    Called from finally — saves whatever rows exist even mid-sweep.
    """
    if not rows:
        print("No data to save")
        return
    os.makedirs(st.DATA_DIR, exist_ok=True)
    stem = f"{st.DATA_DIR}/{datetime.datetime.now():%Y%m%d_%H%M%S}_measurement_N{N}_s{label}"
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(f"{stem}.csv", 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    calibration = _latest_calibration()
    noise_calibration = None
    if calibration:
        noise_calibration = json.loads(calibration.read_text())
        noise_calibration['file'] = calibration.name

    loss_cal_path, loss_cal = _find_latest_loss_calibration()
    loss_calibration = None
    if loss_cal_path:
        def _stage_summary(stage):
            if 'ch' in stage:
                return dict(zip(('mean_hz', 'std_hz'), _bin_rate_mean_std(stage['counts'], stage['ch'])))
            return {str(ch): dict(zip(('mean_hz', 'std_hz'), _bin_rate_mean_std(stage['counts'], ch)))
                    for ch in st.LOOP_CHS}
        stages = {
            LOSS_STAGE_LABELS[key]: _stage_summary(stage)
            for key, stage in loss_cal.get('stages', {}).items()
        }
        loss_calibration = {'file': loss_cal_path.name, 'stages': stages,
                             'losses': loss_cal.get('losses')}

    meta = {
        'N': N,
        'label': label,
        # keyed by real channel number — delays_for()'s list is 0-indexed
        # (index 7 = ch8's delay), which reads as off-by-one in raw JSON
        'delays_ns': {ch: d for ch, d in enumerate(delays_for(), start=1) if ch in st.CHANNELS},
        'thresholds_v': st.THRESHOLDS,
        'coincidence_window_ns': st.COINCIDENCE_WINDOW,
        'det_chs': st.det_chs_for(N),
        'dump_ch': DUMP_CH,
        'trigg_ch': TRIGG_CH,
        'sim_mode': SIM_MODE,
        'git_commit': _git_commit(),
        'saved_at': datetime.datetime.now().isoformat(),
        'noise_calibration': noise_calibration,
        'background_offset_ns': st.MEASUREMENT_BG_OFFSET_NS,
        'background': background,
        'loss_calibration': loss_calibration,
    }
    with open(f"{stem}.json", 'w') as f:
        json.dump(meta, f, indent=1)

    print(f"Saved {len(rows)} rows -> {stem}.csv (+ {stem}.json)")
    if calibration:
        print(f"Most recent calibration: {calibration.name} ({_calibration_date(calibration)})")
    else:
        print("No background calibration on file yet — run menu option 11")


def _latest_calibration():
    """Most recent DATA_DIR/*_noise_calibration.json, or None if none exist yet."""
    files = sorted(Path(st.DATA_DIR).glob('*_noise_calibration.json'), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _calibration_date(path):
    return json.loads(path.read_text())['saved_at']


def _ask_calibration_duration(default=60.0):
    while True:
        s = input(f"Integration time per calibration step, in seconds (default {default:.0f}): ").strip()
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            print("Enter a number of seconds")


def _acquire_counts_all(duration, delays=None):
    """Coincidence/singles counts on every detector channel — not scoped to
    a process N, since background calibration isn't tied to a unitary."""
    if SIM_MODE:
        return _sim_row(duration, DET_CHS)
    from libraries.countingcard import acquire_counts
    return acquire_counts(duration, signal_chs=DET_CHS,
                           delays=delays if delays is not None else delays_for())


def _record_all_channels(n_bins=20, bin_s=5.0):
    """20x5s binned coincidence counts on every channel (LOOP_CHS+DUMP_CH)
    at their pre-tuned delays — same primitive as _acquire_background, no
    scan needed. Every channel's counts ride along in one row so a
    miscalibrated waveplate angle shows up as signal in the wrong channel
    instead of silently vanishing."""
    if SIM_MODE:
        row = _sim_row(bin_s * n_bins, DET_CHS)
        row['bins'] = [_sim_row(bin_s, DET_CHS) for _ in range(n_bins)]
        return row
    from libraries.countingcard import acquire_counts_binned
    return acquire_counts_binned(n_bins=n_bins, bin_s=bin_s, signal_chs=DET_CHS,
                                  delays=delays_for())


def _acquire_background(N):
    """Quick background/accidental-coincidence check for N's channels, run
    automatically at the start of measurement() — every channel's delay
    bumped +MEASUREMENT_BG_OFFSET_NS ns off its tuned value (herald left
    alone), same convention as calibrate_background, so the coincidence
    window misses the real photon and counts only accidentals.

    MEASUREMENT_BG_N_BINS x MEASUREMENT_BG_BIN_S (20 x 5s) bins, same
    convention as calibrate_loss's recordings — row['bins'] holds the full
    per-bin data so mean +/- SEM can be reported per channel, not just a
    single point estimate."""
    chs = st.det_chs_for(N)
    n_bins, bin_s = st.MEASUREMENT_BG_N_BINS, st.MEASUREMENT_BG_BIN_S
    if SIM_MODE:
        row = _sim_row(bin_s * n_bins, chs)
        row['bins'] = [_sim_row(bin_s, chs) for _ in range(n_bins)]
        return row
    from libraries.countingcard import acquire_counts_binned
    delays = delays_for()
    for ch in chs:
        delays[ch - 1] += st.MEASUREMENT_BG_OFFSET_NS
    return acquire_counts_binned(n_bins=n_bins, bin_s=bin_s, signal_chs=chs, delays=delays)


def calibrate_background(duration=None):
    """Per-channel background/accidental coincidence rate: every channel's
    delay is bumped +st.BACKGROUND_OFFSET_NS ns off its tuned value (herald
    left alone), so the coincidence window misses the real photon arrival
    and only counts accidentals — no physical beam blocking needed.

    duration=None asks interactively (default 60s); pass a number to skip
    the prompt entirely, e.g. for unattended/queued use.

    Saves data/{timestamp}_noise_calibration.json.
    """
    if duration is None:
        duration = _ask_calibration_duration()
    delays = delays_for()
    for ch in DET_CHS:
        delays[ch - 1] += st.BACKGROUND_OFFSET_NS
    print(f"Measuring background at +{st.BACKGROUND_OFFSET_NS:.0f} ns off every channel's "
          f"tuned delay, {duration:.0f}s...")
    counts = _acquire_counts_all(duration, delays)
    print(f"  {counts}")

    int_time = counts['int_time']
    background_rate_hz = {
        str(ch): counts.get(f'coinc_ch{ch}', 0) / int_time
        for ch in DET_CHS
    }

    calibration = {
        'counts': counts,
        'offset_ns': st.BACKGROUND_OFFSET_NS,
        'background_rate_hz': background_rate_hz,
        'duration_s': duration,
        'saved_at': datetime.datetime.now().isoformat(),
        'git_commit': _git_commit(),
    }
    os.makedirs(st.DATA_DIR, exist_ok=True)
    stem = f"{st.DATA_DIR}/{datetime.datetime.now():%Y%m%d_%H%M%S}_noise_calibration"
    with open(f"{stem}.json", 'w') as f:
        json.dump(calibration, f, indent=1)
    print(f"\nSaved calibration -> {stem}.json")
    print(f"background_rate_hz: {background_rate_hz}")
    notify("Background calibration done", title="Calibration Complete")
    return calibration


def _scan_and_record(ch, **kwargs):
    """SIM-guarded wrapper around countingcard.scan_and_record, same shape
    as _acquire_counts_all."""
    if SIM_MODE:
        n_bins = kwargs.get('n_bins', 20)
        bin_s = kwargs.get('record_bin_s', 5.0)
        row = _sim_row(bin_s * n_bins, [ch])
        row['bins'] = [_sim_row(bin_s, [ch]) for _ in range(n_bins)]
        return kwargs.get('center', 0.0), row
    from libraries.countingcard import scan_and_record
    return scan_and_record(ch, **kwargs)


def _find_latest_loss_calibration():
    """Most recent data/*_loss_calibration.json, parsed — or (None, {}) if
    none exist yet. Same glob/mtime pattern as _latest_calibration()."""
    files = sorted(Path(st.DATA_DIR).glob('*_loss_calibration.json'), key=lambda p: p.stat().st_mtime)
    if not files:
        return None, {}
    path = files[-1]
    return path, json.loads(path.read_text())


def _zero_path2_plates():
    """Park every motorized path-2 plate (HWP_IN_2/QWP_IN_2/QWP_OUT_2/
    HWP_OUT_2) at 0 — the known-idle state for any loss-calibration stage
    that doesn't deliberately route light through them, so a plate left
    somewhere else by an earlier stage (e.g. IN_2 at V from a loop-pass
    stage) can't bleed into this one."""
    print("Parking path-2 plates (HWP_IN_2/QWP_IN_2/QWP_OUT_2/HWP_OUT_2) at 0°")
    tl.move_stage(HWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_OUT_2, 0, COMPORT)
    tl.move_stage(HWP_OUT_2, 0, COMPORT)


def _zero_analyzer_plates():
    """Park TOM_1/TOM_DUMP (the basis analyzers used by perform_tomo/
    check_projector, not by any of the raw-intensity optics setters below)
    at 0 -- a lossless rotation can't itself change total intensity, but a
    leftover angle from an earlier tomography run has no business being set
    during a loop-exit-probability measurement, so every optics setter
    below parks it explicitly rather than leaving it to chance."""
    tl.move_stage(HWP_TOM_1, 0, COMPORT)
    tl.move_stage(QWP_TOM_1, 0, COMPORT)
    tl.move_stage(HWP_TOM_DUMP, 0, COMPORT)
    tl.move_stage(QWP_TOM_DUMP, 0, COMPORT)


def _set_bypass_optics():
    """Zero loops, all exit: input H, IN_2/TOM_1/TOM_DUMP parked at 0 (no
    ring coupling, no stray analyzer rotation), H1/Q1 parked at 0 (unused
    here -- the coin on path 1 never sees any amplitude when input is pure
    H and everything exits on pass 1, but leaving it at a leftover value
    from an earlier stage is still sloppy), HWP_12/QWP_12 at 45°/0° routes
    everything straight out the exit port (22.5 would split H into D,
    sending only half out the exit -- see tests/test_loop_exit_split.py).
    Fully automated — no manual switch/plate step needed. Sets everything
    this stage depends on -- self-contained so it's safe to run even if an
    earlier stage was skipped via resume."""
    _set_input_basis('H')
    _zero_path2_plates()
    _zero_analyzer_plates()
    print("Setting HWP_1/QWP_1 to 0°, HWP_12/QWP_12 to 45°/0° (zero-loop, all exit)")
    tl.move_stage(QWP_1, 0, COMPORT)
    tl.move_stage(HWP_1, 0, COMPORT)
    tl.move_stage(QWP_12, 0, COMPORT)
    tl.move_stage(HWP_12, 45, COMPORT)


def _set_loop_optics():
    """One loop then exit: input H, IN_2 parked at 0 (pass-through both
    ways), HWP_12/QWP_12 at 0 (loop arm does nothing), HWP_OUT_2/QWP_OUT_2
    at 45°/0° flips H->V so it goes around the loop; it crosses IN_2 again
    (still 0, pass-through), then HWP_1/QWP_1 at 45°/0° routes it out the
    exit port. Fully automated — no manual switch needed. Self-contained,
    same reasoning as _set_bypass_optics (also parks TOM_1/TOM_DUMP)."""
    _set_input_basis('H')
    _zero_analyzer_plates()
    print("Setting HWP_IN_2/QWP_IN_2 and HWP_12/QWP_12 to 0 (pass-through / loop arm idle)")
    tl.move_stage(QWP_IN_2, 0, COMPORT)
    tl.move_stage(HWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_12, 0, COMPORT)
    tl.move_stage(HWP_12, 0, COMPORT)
    print("Setting HWP_OUT_2/QWP_OUT_2 to 45°/0° (H->V, sends it around the loop)")
    tl.move_stage(QWP_OUT_2, 0, COMPORT)
    tl.move_stage(HWP_OUT_2, 45, COMPORT)
    print("Setting HWP_1/QWP_1 to 45°/0° (routes it back out the exit port)")
    tl.move_stage(QWP_1, 0, COMPORT)
    tl.move_stage(HWP_1, 45, COMPORT)


def _set_5050_optics():
    """50/50 loop/exit split: input H, path-2 plates (IN_2/OUT_2) and H1/Q1
    parked at 0, HWP_12 at 22.5° (QWP_12 at 0) puts the recombined output
    in an equal superposition of path1 (TOM_1, exit) and path2 (OUT_2,
    loop) — confirmed via getUnitary, see tests/test_loop_exit_split.py.
    45° on HWP_12 is a different, deterministic all-exit solution, not
    this.

    OUT_2 matters here: it sits inside the recirculating loop (applied to
    the continuing beam every pass, not just a one-shot analyzer), so a
    leftover angle from an earlier stage (e.g. _set_loop_optics leaves it
    at 45°/0°) would silently break the assumed-stationary 50/50 split
    every pass after the first -- _zero_path2_plates() parks both IN_2 and
    OUT_2, not just IN_2, to rule that out. Self-contained, same pattern
    as the other two optics setters (also parks TOM_1/TOM_DUMP)."""
    _set_input_basis('H')
    _zero_path2_plates()
    _zero_analyzer_plates()
    print("Setting HWP_1/QWP_1 to 0°, HWP_12 to 22.5° (50/50 exit/loop split)")
    tl.move_stage(QWP_1, 0, COMPORT)
    tl.move_stage(HWP_1, 0, COMPORT)
    tl.move_stage(QWP_12, 0, COMPORT)
    tl.move_stage(HWP_12, 22.5, COMPORT)


def _set_loop3_optics():
    """Peaks the exit probability at the 3rd loop pass (st.LOOP_CHS[2]) --
    43.8% of the photon exits there, vs. 32.1%/14.3% leaking out at loop
    passes 2/4 (the rest is residual beyond 6 loops). For use when tuning
    that channel's delay specifically: much stronger signal there than the
    fast falloff you'd get leaving the optics on a U_N process preset.

    Unlike _set_bypass_optics/_set_loop_optics (exact, closed-form 0- and
    1-loop solutions), this is the best configuration found by numerically
    optimizing h1/q1/h2/q2/hf2/qf2 and the input state over the per-pass
    loop model (PBS -> coin -> fixed mirror phase -> PBS_dag -> OUT_2),
    with the mirror phase pinned to the real hardware value (m1+m2+m3 =
    3.16+3.77+3.74, same as every U_N preset) since it isn't a motorized
    stage. Not yet confirmed on the bench. Also parks TOM_1/TOM_DUMP, as
    every optics setter in this file does."""
    _zero_analyzer_plates()
    print("Setting HWP_IN/QWP_IN to 93.445°/85.188° (loop-3-peaking input state)")
    tl.move_stage(HWP_IN, 93.445, COMPORT)
    tl.move_stage(QWP_IN, 85.188, COMPORT)
    print("Setting HWP_IN_2/QWP_IN_2 to 0°/0°")
    tl.move_stage(HWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_IN_2, 0, COMPORT)
    print("Setting HWP_1/QWP_1 to 142.430°/166.820°, HWP_12/QWP_12 to 89.998°/179.998°")
    tl.move_stage(HWP_1, 142.430, COMPORT)
    tl.move_stage(QWP_1, 166.820, COMPORT)
    tl.move_stage(HWP_12, 89.998, COMPORT)
    tl.move_stage(QWP_12, 179.998, COMPORT)
    print("Setting HWP_OUT_2/QWP_OUT_2 to 133.803°/33.989°")
    tl.move_stage(HWP_OUT_2, 133.803, COMPORT)
    tl.move_stage(QWP_OUT_2, 33.989, COMPORT)


def _set_loop4_optics():
    """Peaks the exit probability at the 4th loop pass (st.LOOP_CHS[3]) --
    30.1% of the photon exits there, vs. 28.9%/16.2% at loop passes 3/5
    (close to loop 3's share, but still the highest of the six). Same
    derivation and caveat as _set_loop3_optics -- optimizer-found, not an
    exact solution, not yet confirmed on the bench. Also parks TOM_1/
    TOM_DUMP, as every optics setter in this file does."""
    _zero_analyzer_plates()
    print("Setting HWP_IN/QWP_IN to 131.788°/99.785° (loop-4-peaking input state)")
    tl.move_stage(HWP_IN, 131.788, COMPORT)
    tl.move_stage(QWP_IN, 99.785, COMPORT)
    print("Setting HWP_IN_2/QWP_IN_2 to 0°/0°")
    tl.move_stage(HWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_IN_2, 0, COMPORT)
    print("Setting HWP_1/QWP_1 to 0.000°/90.002°, HWP_12/QWP_12 to 67.617°/6.486°")
    tl.move_stage(HWP_1, 0.000, COMPORT)
    tl.move_stage(QWP_1, 90.002, COMPORT)
    tl.move_stage(HWP_12, 67.617, COMPORT)
    tl.move_stage(QWP_12, 6.486, COMPORT)
    print("Setting HWP_OUT_2/QWP_OUT_2 to 1.512°/117.523°")
    tl.move_stage(HWP_OUT_2, 1.512, COMPORT)
    tl.move_stage(QWP_OUT_2, 117.523, COMPORT)


def _loss_stage_date(stages, key):
    """Display date for a loss-calibration stage key. 'loop01' is really
    two underlying stages (loop0+loop1) that are always run together now
    (both automated, both needed for loss_per_loop_pass, no reason to let
    one run without the other) -- 'never' unless both are on file, else
    the earlier of the two timestamps."""
    if key == 'loop01':
        d0 = stages.get('loop0', {}).get('saved_at')
        d1 = stages.get('loop1', {}).get('saved_at')
        return min(d0, d1) if d0 and d1 else 'never'
    return stages.get(key, {}).get('saved_at', 'never')


def _loss_stage_done(stages, key):
    return _loss_stage_date(stages, key) != 'never'


def calibrate_loss(run_stages=None):
    """Menu-driven loss calibration over 2 stages, both fully automated (no
    fiber replugging — safe to run unattended/queued):
      loop01 zero-loop bypass + one loop pass, together -> loop0, loop1
      5050   50/50 split optics, one recording across every loop channel

    (Previously also had source/source_dump/dump/straight_to_dump/input
    stages for det_eff_dump/loss_input_to_setup/loss_to_dump — dropped along
    with those stages since they needed physically unplugging fibers, which
    rules out unattended use.)

    Every stage's peak recording is 20 x 5s bins rather than one long read —
    the per-bin counts are kept on file, and losses/rates are reported as
    mean +/- SEM (std/sqrt(20)), with errors propagated through the ratio
    (relative errors combine in quadrature). Every losses/rates key has an
    "_err" companion.

    Returns/reports loss_per_loop_pass by two independent methods, so they
    can be checked against each other:
      loss_per_loop_pass      = loop1/loop0 — loop0/loop1's optics each put
                           ~all the light deterministically at one channel,
                           so the ratio between the two stages is the
                           per-pass loss directly.
      loss_per_loop_pass_5050 = the 50/50 stage's channel-to-channel count
                           decay (fit across all 6 channels at once, see
                           _fit_loop_decay), divided by the known 0.5
                           lossless-case ratio. Same physical quantity, a
                           completely different optics config and
                           measurement — if the two disagree by more than
                           their error bars, something's off.

    Stages are picked from a menu, in any order, any number of times — not a
    fixed sequence. Each menu entry shows when it was last done. Saves after
    every stage (not just at the end), to data/{timestamp}_loss_calibration.json.
    If a previous (possibly interrupted) run's file exists, its stages are
    loaded so they show up as already-done and count toward the final loss
    computation without being re-run. Finishing computes losses from
    whichever stages are on file — pick "compute & finish" once loop0/loop1
    show a done date.

    run_stages: a list of stage keys (e.g. ['loop01']) to run non-interactively
    instead of showing the menu -- for unattended/queued use. Still falls
    through to "compute & finish" afterward, so calling this once per stage
    across separate queue steps resumes/accumulates via the loss-calibration
    file exactly like the interactive menu does.
    """
    path, existing = _find_latest_loss_calibration()
    stages = dict(existing.get('stages', {}))
    if stages:
        print(f"Found an existing loss calibration ({path.name}) — stages on file: {', '.join(stages)}.")

    def _save(losses=None, rates=None):
        nonlocal path
        if path is None:
            os.makedirs(st.DATA_DIR, exist_ok=True)
            path = Path(f"{st.DATA_DIR}/{datetime.datetime.now():%Y%m%d_%H%M%S}_loss_calibration.json")
        meta = {
            'stages': stages,
            'record_n_bins': 20,
            'record_bin_s': 5.0,
            'git_commit': _git_commit(),
            'saved_at': datetime.datetime.now().isoformat(),
        }
        if losses is not None:
            meta['losses'] = losses
        if rates is not None:
            meta['coincidence_rates_hz'] = rates
        path.write_text(json.dumps(meta, indent=1))
        print(f"  (saved -> {path.name})")
        return meta

    def _run_loop0():
        _set_bypass_optics()
        return {'ch': st.LOOP_CHS[0], 'counts': _record_all_channels()}

    def _run_loop1():
        _set_loop_optics()
        return {'ch': st.LOOP_CHS[1], 'counts': _record_all_channels()}

    def _run_loop01():
        """loop0 (zero-loop) and loop1 (one loop pass) always run together
        -- both fully automated, both needed for loss_per_loop_pass, no
        reason to let them drift out of sync by running one without the
        other. Returns both results for the dispatch loop to merge in."""
        return {'loop0': _run_loop0(), 'loop1': _run_loop1()}

    def _run_5050():
        """50/50 optics, one recording across every loop channel at once --
        the loss-per-pass estimate comes from fitting how fast counts decay
        channel-to-channel (see _fit_loop_decay), not from any single
        channel in isolation."""
        _set_5050_optics()
        return {'5050': {'counts': _record_all_channels()}}

    stage_menu = [
        ('loop01', 'Zero-loop + one-loop pass, together', _run_loop01),
        ('5050', '50/50 split, all channels (independent cross-check)', _run_5050),
    ]
    # '5050' computes its own independent loss figure (see below) rather
    # than feeding the loop0/loop1 formula, so it's not required before
    # "compute & finish" -- loop0/loop1 alone are enough to get a number.
    required_stages = ['loop0', 'loop1']
    runners = {key: run for key, _, run in stage_menu}

    def _apply(results):
        now = datetime.datetime.now().isoformat()
        for key, result in results.items():
            result['saved_at'] = now
            stages[key] = result
        _save()

    if run_stages is not None:
        for key in run_stages:
            print(f"\nRunning loss-calibration stage: {key}")
            _apply(runners[key]())
    else:
        while True:
            print("\nLoss calibration stages:")
            for i, (key, label, _) in enumerate(stage_menu, 1):
                when = _loss_stage_date(stages, key)
                print(f"\t{i}. {label} (last done {when})")
            choice = input("\t0. Compute losses & finish\n> ").strip()
            if choice == '0':
                break
            try:
                _, _, run = stage_menu[int(choice) - 1]
            except (ValueError, IndexError):
                print("Enter a number from the menu")
                continue
            _apply(run())

    missing = [key for key in required_stages if key not in stages]
    if missing:
        print(f"Missing stages, can't compute losses yet: {', '.join(missing)}")
        return _save()

    def rate(stage_key):
        """(mean_rate_hz, sem_rate_hz) from a stage's per-bin coincidence
        counts — SEM = std/sqrt(n_bins). Falls back to a single point
        estimate with no error bar for older stages recorded before
        per-bin counts existed."""
        s = stages[stage_key]
        counts = s['counts']
        mean_rate, std_rate = _bin_rate_mean_std(counts, s['ch'])
        n_bins = len(counts.get('bins') or ())
        sem_rate = std_rate / n_bins ** 0.5 if n_bins > 1 else 0.0
        return mean_rate, sem_rate

    def combine(*terms):
        """(value, err) for a product of terms**power (power=-1 for a
        division) — relative errors combine in quadrature, valid for any
        chain of independent multiplications/divisions. terms are
        ((value, err), power) pairs, e.g. combine((L1, 1), (L0, -1)) for
        L1/L0. None if any input value is zero/None (division by zero)."""
        if any(not v for (v, _), _ in terms):
            return None, None
        result = 1.0
        for (v, _), p in terms:
            result *= v ** p
        rel_sq = sum((p * e / v) ** 2 for (v, e), p in terms)
        return result, abs(result) * rel_sq ** 0.5

    L0, L1 = rate('loop0'), rate('loop1')
    rates = {'loop0_hz': L0[0], 'loop0_hz_err': L0[1], 'loop1_hz': L1[0], 'loop1_hz_err': L1[1]}

    # Method 1: loop1 (one loop pass) vs. loop0 (zero loops) -- each
    # stage's optics deterministically puts ~all the light at one channel,
    # so the ratio between the two is the per-pass loss directly.
    loss_per_loop_pass = combine((L1, 1), (L0, -1))
    losses = {
        'loss_per_loop_pass':      loss_per_loop_pass[0],
        'loss_per_loop_pass_err':  loss_per_loop_pass[1],
    }

    # Method 2: under the 50/50 optics, every pass splits whatever's left
    # exactly 50/50 (by construction, see _set_5050_optics) -- so with zero
    # loss, consecutive loop channels' counts would decay by exactly 0.5x.
    # Fitting the *actual* decay across all 6 channels at once and dividing
    # out that known 0.5x isolates the real per-pass loss -- an independent
    # cross-check against method 1 (same physical quantity, different
    # optics config and a different measurement entirely).
    if '5050' in stages:
        decay_ratio, decay_ratio_err = _fit_loop_decay(stages['5050']['counts'])
        if decay_ratio is not None:
            losses['loss_per_loop_pass_5050'] = decay_ratio / 0.5
            losses['loss_per_loop_pass_5050_err'] = decay_ratio_err / 0.5

    meta = _save(losses=losses, rates=rates)
    print(f"\nSaved -> {path}")
    print(f"losses: {losses}")
    notify("Loss calibration done", title="Calibration Complete")
    return meta



def _maybe_calibrate():
    """Offer to (re)run background calibration before a measurement, showing
    when it was last done -- then do the same for the loss-calibration
    stages (loop01/5050), via _maybe_calibrate_loss(). One pre-measurement
    check from the operator's point of view, interactive-path only (see
    measurement()'s auto=True branch, which skips all of this)."""
    latest = _latest_calibration()
    if latest is None:
        if input("No background calibration on file yet. Run one now? [Y/n] ").strip().lower() in ('', 'y'):
            calibrate_background()
    else:
        ans = input(f"Last background calibration: {_calibration_date(latest)} — "
                   "perform a new one now? [y/N] ").strip().lower()
        if ans == 'y':
            calibrate_background()
    _maybe_calibrate_loss()


def _maybe_calibrate_loss():
    """Show when each loss-calibration stage (loop01/5050) was last done
    and let the operator (re)run any of them now, reusing calibrate_loss's
    own stage logic via run_stages= rather than duplicating it here."""
    _, existing = _find_latest_loss_calibration()
    stages = existing.get('stages', {})
    keys = ['loop01', '5050']
    print("\nLoss calibration stages:")
    for key in keys:
        print(f"\t{key}: last done {_loss_stage_date(stages, key)}")
    ans = input("Run any of these now? Comma-separated keys (e.g. loop01,5050), "
                "'all missing', or Enter to skip: ").strip().lower()
    if not ans or ans == 'skip':
        return
    if ans == 'all missing':
        run_stages = [key for key in keys if not _loss_stage_done(stages, key)]
        if not run_stages:
            print("Nothing missing.")
            return
    else:
        run_stages = [key.strip() for key in ans.split(',') if key.strip() in keys]
        if not run_stages:
            print("No valid stage keys given, skipping.")
            return
    calibrate_loss(run_stages=run_stages)

def _input_states(N):
    """All j's with a defined input state for process N.

    ponytail: read off process_state_angles keys for now — point this at the
    causal model once it exists.
    """
    return sorted(int(k.split('_')[0][1:]) for k in process_state_angles
                  if k.endswith(f'_{N}'))

def _ask_duration():
    """Collection time in seconds per setting (input state x basis).
    Enter defaults to 20 min; 0 streams until Ctrl-C."""
    while True:
        m = input("Collect for how many minutes per setting? (Enter = 20, 0 = stream until Ctrl-C): ").strip()
        if not m:
            return 20 * 60
        try:
            minutes = float(m)
        except ValueError:
            print("Enter a number of minutes, or press Enter for the 20 min default")
            continue
        return None if minutes == 0 else minutes * 60


def _format_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def _apply_setting(N, j, basis):
    _set_input_state(N, j)
    if basis is not None:
        _set_tomo_stages(HWP=HWP_TOM_1, QWP=QWP_TOM_1, basis=basis)
        _set_tomo_stages(HWP=HWP_TOM_DUMP, QWP=QWP_TOM_DUMP, basis=basis)


def _should_round_robin(total, n_settings):
    """True once a multi-setting run's total wall time passes
    st.ROUND_ROBIN_THRESHOLD_S. total=None (stream until Ctrl-C) never
    round-robins — there's no budget to interleave."""
    return (total is not None and n_settings > 1
            and total * n_settings > st.ROUND_ROBIN_THRESHOLD_S)


def _round_robin_plan(settings, total, bin_s):
    """Yield (j, basis, chunk_seconds), cycling through `settings` in
    bin_s-second chunks until each has collected `total` s."""
    remaining = {s: total for s in settings}
    while any(r > 0 for r in remaining.values()):
        for s in settings:
            if remaining[s] <= 0:
                continue
            chunk = min(bin_s, remaining[s])
            yield (*s, chunk)
            remaining[s] -= chunk


def measurement(N, performTomo=False, js=None, duration_s=None, auto=False):
    """Collect statistics through unitary N, one row per st.MEASUREMENT_INTEGRATION_S seconds.

    performTomo=False : collect at the current analyzer setting
    performTomo=True  : full 6-basis tomo sweep
    js                : input states to repeat for (list of j). None = [0] (s0 only).

    Asks for a collection time per setting (input state x basis); Enter
    defaults to 20 min, 0 streams until Ctrl-C. When there's more than one setting and the total
    run would exceed st.ROUND_ROBIN_THRESHOLD_S, settings are interleaved in
    st.ROUND_ROBIN_COLLECTION_TIME_S bins (round-robin) rather than run to
    completion one at a time, so slow drift doesn't bias one setting more
    than another. Everything goes to one file; rows carry an input_state
    column (= j).

    Before the run starts, a quick _acquire_background(N) check (delays
    bumped +MEASUREMENT_BG_OFFSET_NS ns off tuned, same convention as
    calibrate_background; 20 x 5s bins, same as calibrate_loss's
    recordings) is saved into the sidecar JSON alongside the rows — one
    accidental-coincidence reading per run, not just a pointer to whichever
    separate noise_calibration happened to be most recent.

    auto=True skips every interactive prompt (duration confirmation and the
    offer to re-run background calibration) for unattended/queued use --
    duration_s must be given then (None streams until Ctrl-C, same meaning
    as the interactive default's 0).

    Returns the list of result rows so callers can aggregate.
    """
    if auto:
        if _latest_calibration() is None:
            calibrate_background(duration=60.0)
    else:
        _maybe_calibrate()

    js = js if js is not None else [0]
    bases = ['H', 'V', 'A', 'D', 'R', 'L'] if performTomo else [None]
    settings = [(j, b) for j in js for b in bases]

    if auto:
        total = duration_s
        round_robin = _should_round_robin(total, len(settings))
    else:
        while True:
            total = _ask_duration()
            round_robin = _should_round_robin(total, len(settings))
            if total is None:
                break
            print(f"This measurement will take {_format_duration(total * len(settings))}.")
            if input("Press Enter to begin, or c to change the duration: ").strip().lower() != 'c':
                break

    print(f"Measuring background (+{st.MEASUREMENT_BG_OFFSET_NS:.0f}ns off tuned delays, "
          f"{st.MEASUREMENT_BG_N_BINS} x {st.MEASUREMENT_BG_BIN_S:.0f}s bins)...")
    background = _acquire_background(N)
    print(f"  {background}")

    _set_unitary(N)
    start = time.monotonic()

    rows = []
    print("\n\n")

    def collect(j, basis, duration):
        for counts in _acquire_rows(N, duration):
            rows.append({'N': N, 'input_state': j, 'basis': basis,
                         'time': datetime.datetime.now().isoformat(),
                         **counts})
            print(f"[s{j} {basis or 'no-tomo'}] {counts}", end="\r", flush=True)

    try:
        if not round_robin:
            for j in js:
                _set_input_state(N, j)
                for basis in bases:
                    if basis is not None:
                        _set_tomo_stages(HWP=HWP_TOM_1, QWP=QWP_TOM_1, basis=basis)
                        _set_tomo_stages(HWP=HWP_TOM_DUMP, QWP=QWP_TOM_DUMP, basis=basis)
                    collect(j, basis, total)
        else:
            for j, basis, chunk in _round_robin_plan(settings, total, st.ROUND_ROBIN_COLLECTION_TIME_S):
                _apply_setting(N, j, basis)
                collect(j, basis, chunk)
    except KeyboardInterrupt:
        print("\nStopped — saving what we have")
    finally:
        # runs on success, error, or Ctrl-C — partial data still gets saved
        label = 'all' if js == _input_states(N) else '-'.join(map(str, js)) if len(js) > 1 else js[0]
        _save_results(rows, N, label, background=background)
        notify(f"Measurement N={N} done ({len(rows)} rows)",
               title="Measurement Complete", priority="high")
        if time.monotonic() - start > 300:
            _play_tune()
    return rows


def _ask_N():
    """Returns the chosen N, or None if the operator typed 0/back."""
    while True:
        N = input(f"Which unitary N? ({'/'.join(unitaries_angles)}, or 0/back): ").strip()
        if _is_back(N):
            return None
        if N in unitaries_angles:
            return N
        print("Invalid unitary choice")


def _ask_tomo_integration():
    """Integration time per output-basis point, in seconds (not the total
    run — there are 6 output bases per input, so keep this short)."""
    while True:
        s = input("Integration time per basis setting, in seconds (default 5): ").strip()
        if not s:
            return 5.0
        try:
            return float(s)
        except ValueError:
            print("Enter a number of seconds")


def _sweep_output_bases(HWP, QWP, N, duration, channel):
    """Sweep (HWP, QWP) through HVADRL, reading `channel`'s coincidence
    count at each basis. Returns {basis: (count, err)}."""
    data = {}
    for basis in tl.FULL_BASES:
        _set_tomo_stages(HWP=HWP, QWP=QWP, basis=basis)
        counts = _acquire_counts(duration, N)
        c = counts.get(f'coinc_ch{channel}', 0)
        data[basis] = (c, (c if c > 0 else 1) ** 0.5)
        print(f"  |{basis}>: ch{channel}={c}")
    return data


def _tomo_path1(N, labels, set_input, duration):
    """The loop's first-tap output (LOOP_CHS[0]) via TOM_1, OUT_2 fixed at
    the U-angle — the gate output that feeds the loop.
    Returns {input_label: {output_basis: (count, err)}}."""
    _set_fixed_waveplates(unitaries_angles[N], path=1)
    _beep()
    data = {}
    for label in labels:
        print(f"\n=== Path 1 (ch{LOOP_CHS[0]}) | Input |{label}> ===")
        set_input(label)
        data[label] = _sweep_output_bases(HWP_TOM_1, QWP_TOM_1, N, duration, LOOP_CHS[0])
    return data


def _tomo_path2(N, labels, set_input, duration, loop=1):
    """dump (ch7) via OUT_2 — a polariser sits behind the OUT_2 plates in
    that arm, so OUT_2 is the correct analyzer here (not TOM_DUMP, a
    separate stage pair); getUnitary(path=2) already excludes hf2/qf2 from
    U to match. TOM_1 is fixed at the U-angle for this pass, and dump's
    delay is swapped to DUMP_DELAYS[loop] (loop=1 pairs with path 1's
    LOOP_CHS[0]/loop-1 reading) for the duration, then restored.
    Returns {input_label: {output_basis: (count, err)}}."""
    _set_fixed_waveplates(unitaries_angles[N], path=2)
    normal_dump_delay = st.CHANNELS[DUMP_CH]['delay']
    st.CHANNELS[DUMP_CH]['delay'] = st.DUMP_DELAYS[loop]
    print(f"Dump delay set to {st.DUMP_DELAYS[loop]} ns (dump-after-{loop}-loop, path 2)")
    data = {}
    try:
        for label in labels:
            print(f"\n=== Path 2 (dump) | Input |{label}> ===")
            set_input(label)
            data[label] = _sweep_output_bases(HWP_OUT_2, QWP_OUT_2, N, duration, DUMP_CH)
    finally:
        st.CHANNELS[DUMP_CH]['delay'] = normal_dump_delay
        print(f"Dump delay restored to {normal_dump_delay} ns")
    return data


_BACK = ('0', 'back')


def _is_back(choice):
    """True for '0' or 'back' (any case) -- every menu that leads to
    another menu accepts either to return to the one that called it,
    instead of forcing Ctrl-C or a full workflow."""
    return choice.strip().lower() in _BACK


def tomography_menu():
    """Entry point for the main menu's tomography option: either a full
    characterisation sweep (perform_tomo) or a single-point phase-tuning
    check (check_projector) -- grouped together since both drive the same
    gate-analysis waveplates, just at different granularity."""
    choice = input(
        "Tomography:\n"
        "\t1. Perform tomography (full sweep + plot)\n"
        "\t2. Check single input/output projector (phase tuning)\n"
        "\t0. Back\n"
        "> ").strip()
    if _is_back(choice):
        return
    if choice == '1':
        perform_tomo()
    elif choice == '2':
        check_projector()
    else:
        print("Invalid choice — pick 1, 2, or 0/back")


def perform_tomo():
    """Photon-counting tomography of the 2-port Sagnac gate for a chosen
    unitary N: sweep an input basis set through all 6 output bases, on
    either or both of the gate's physical outputs, then plot measured vs
    theoretical U for each path run.

    path 1 and path 2 need opposite fixed/free waveplate configurations
    (see _tomo_path1/_tomo_path2), so running both means two full passes
    over every input label, not one shared sweep.
    """
    N = _ask_N()
    if N is None:
        return
    choice = input(
        "Input sweep?\n"
        "\t1. HVAD (4 generic polarisation bases)\n"
        "\t2. HVADRL (6 generic polarisation bases)\n"
        "\t3. Sj (single process state s0)\n"
        "\t4. Sall (every process state s_j for this N)\n"
        "\t5. Single basis (H/V/A/D/R/L)\n"
        "\t0. Back\n"
        "> ").strip()
    if _is_back(choice):
        return
    if choice == '1':
        labels, set_input = tl.HVAD_BASES, _set_input_basis
    elif choice == '2':
        labels, set_input = tl.FULL_BASES, _set_input_basis
    elif choice in ('3', '4'):
        js = _input_states(N) if choice == '4' else [0]
        labels = tuple(f's{j}_{N}' for j in js)
        set_input = lambda label: _set_input_state(N, int(label.split('_')[0][1:]))
    elif choice == '5':
        basis = _ask_basis("Which basis?")
        if basis is None:
            print("Invalid basis choice")
            return
        labels, set_input = (basis,), _set_input_basis
    else:
        print("Invalid choice — pick 1-5")
        return

    path_choice = input(
        "Which path?\n"
        f"\t1. Path 1 only (ch{LOOP_CHS[0]} via TOM_1)\n"
        "\t2. Path 2 only (dump via OUT_2)\n"
        "\t3. Both\n"
        "\t0. Back\n"
        "> ").strip()
    if _is_back(path_choice):
        return
    if path_choice not in ('1', '2', '3'):
        print("Invalid choice — pick 1-3, or 0/back")
        return
    do1, do2 = path_choice in ('1', '3'), path_choice in ('2', '3')
    n_paths = do1 + do2

    duration = _ask_tomo_integration()
    total_s = len(labels) * n_paths * len(tl.FULL_BASES) * duration
    print(f"{len(labels)} inputs x {n_paths} path(s) x 6 output bases x "
          f"{duration:.0f}s = ~{total_s:.0f}s total")

    angles = {**unitaries_angles[N], 'N': N, 'title': f'U{N}'}
    fits = {}
    if do1:
        data1 = _tomo_path1(N, labels, set_input, duration)
        fits[1] = plotting.plot_characterisation(
            data1, graph_title=f'U{N}_path1_ch{LOOP_CHS[0]}',
            angles=angles, plot_type=f'U{N}_path1', path=1)
    if do2:
        data2 = _tomo_path2(N, labels, set_input, duration)
        fits[2] = plotting.plot_characterisation(
            data2, graph_title=f'U{N}_path2_dump',
            angles=angles, plot_type=f'U{N}_path2', path=2)

    print("  |  ".join(f"path{p} fit residual: {fit:.4f}" for p, fit in fits.items()))
    notify(f"Tomo U{N} done — " + ", ".join(f"fit{p}={fit:.4f}" for p, fit in fits.items()),
           title="Tomography Complete", priority="high")


def _stream_channel(channel, duration, label=None):
    """SIM_MODE guard + stream_herald_and_signal call, used by check_projector."""
    tag = f" ({label})" if label else ""
    if SIM_MODE:
        print(f"[SIM MODE] would stream ch{channel}{tag} with delays {delays_for()}")
        return
    from libraries.countingcard import stream_herald_and_signal
    stream_herald_and_signal(signal_ch=channel, duration=duration, delays=delays_for())


def _ask_basis(prompt):
    """H/V/A/D/R/L picker — type the number or the letter itself.
    Returns the basis letter, or None."""
    menu = '\n'.join(f'\t{i}. {b}' for i, b in enumerate(tl.FULL_BASES, 1))
    choice = input(f"{prompt}\n{menu}\n> ").strip().upper()
    if choice in tl.FULL_BASES:
        return choice
    try:
        return tl.FULL_BASES[int(choice) - 1]
    except (ValueError, IndexError):
        return None


def _ask_input_label(N, prompt="Input?"):
    """Single input selector: an H/V/A/D/R/L basis or a process state s_j.
    Returns (label, set_input) — set_input(label) drives HWP_IN/QWP_IN to
    it — or (None, None) on an invalid choice."""
    choice = input(
        f"{prompt}\n"
        "\t1. H/V/A/D/R/L basis\n"
        "\t2. Process state s_j\n"
        "> ").strip()
    if choice == '1':
        basis = _ask_basis("Which basis?")
        return (basis, _set_input_basis) if basis is not None else (None, None)
    if choice == '2':
        js = _input_states(N)
        j = input(f"Which j? ({', '.join(map(str, js))}): ").strip()
        try:
            j = int(j)
        except ValueError:
            return None, None
        label = f's{j}_{N}'
        if label not in process_state_angles:
            return None, None
        return label, lambda label: _set_input_state(N, int(label.split('_')[0][1:]))
    return None, None


def check_projector():
    """Set one input/output basis pair on a chosen path and stream the live
    coincidence rate — for phase tuning after a tomo run: e.g. D in, L out,
    path 2, watch the count while adjusting a phase element by hand."""
    N = _ask_N()
    if N is None:
        return
    path_choice = input(
        "Which path?\n"
        f"\t1. Path 1 (ch{LOOP_CHS[0]} via TOM_1)\n"
        "\t2. Path 2 (dump via OUT_2)\n"
        "\t0. Back\n"
        "> ").strip()
    if _is_back(path_choice):
        return
    if path_choice not in ('1', '2'):
        print("Invalid choice — pick 1, 2, or 0/back")
        return
    path = int(path_choice)

    in_label, set_input = _ask_input_label(N, "Input?")
    out_basis = _ask_basis("Output basis?")
    if in_label is None or out_basis is None:
        print("Invalid choice")
        return

    d = input("Stream duration in seconds (Enter = stream until Ctrl-C): ").strip()
    duration = float(d) if d else None

    _set_fixed_waveplates(unitaries_angles[N], path=path)
    set_input(in_label)

    if path == 1:
        _set_tomo_stages(HWP=HWP_TOM_1, QWP=QWP_TOM_1, basis=out_basis)
        print(f"|{in_label}> in, |{out_basis}> out, path 1 (ch{LOOP_CHS[0]}) — streaming")
        _stream_channel(LOOP_CHS[0], duration, label=f'{in_label}in_{out_basis}out_path1')
        return

    _set_tomo_stages(HWP=HWP_OUT_2, QWP=QWP_OUT_2, basis=out_basis)
    normal_dump_delay = st.CHANNELS[DUMP_CH]['delay']
    st.CHANNELS[DUMP_CH]['delay'] = st.DUMP_DELAYS[1]
    print(f"Dump delay set to {st.DUMP_DELAYS[1]} ns (dump-after-1-loop, path 2)")
    print(f"|{in_label}> in, |{out_basis}> out, path 2 (dump) — streaming")
    try:
        _stream_channel(DUMP_CH, duration, label=f'{in_label}in_{out_basis}out_path2')
    finally:
        st.CHANNELS[DUMP_CH]['delay'] = normal_dump_delay
        print(f"Dump delay restored to {normal_dump_delay} ns")


def ping_antilatch():
    """Round-trip a ping to the antilatch server. No detectors or stages touched.

    The server echoes back any non-"restart" message, so a matching echo
    means it is up and parsing JSON. bias_voltage_list is included because
    older server versions crash on messages without it.

    Reports each phase separately: connect failure = server/port unreachable;
    reply timeout = ping delivered but the echo never came back (server-side
    crash, or the network dropping server->client traffic).
    """
    msg = json.dumps({"message": "ping", "bias_voltage_list": {}}).encode('utf-8')
    try:
        s = socket.create_connection((ANTILATCH_HOST, ANTILATCH_PORT), timeout=5)
    except OSError as e:
        print(f"CONNECT FAILED to {ANTILATCH_HOST}:{ANTILATCH_PORT} ({e}) — server down or port blocked")
        return False
    with s:
        s.sendall(msg)
        try:
            reply = s.recv(1024)
        except TimeoutError:
            print(f"Connected to {ANTILATCH_HOST}:{ANTILATCH_PORT} and sent ping, "
                  "but NO REPLY within 5 s.\n"
                  "The ping reached the server if it printed the message — then either "
                  "the server crashed handling it (check its console for a traceback) "
                  "or the network is dropping server->client traffic.")
            return False
        except OSError as e:
            print(f"Connection dropped while waiting for reply ({e})")
            return False
    if reply == msg:
        print(f"Antilatch server OK at {ANTILATCH_HOST}:{ANTILATCH_PORT} (echo received)")
        return True
    print(f"Antilatch server reachable but sent unexpected reply: {reply!r}")
    return False


def calibrate_background_and_loss():
    """Background/noise calibration followed by loss calibration, as one
    menu option -- a measurement's own pre-run check already treats these
    as one combined step (see _maybe_calibrate/_maybe_calibrate_loss), so
    there's no reason to make the operator pick them separately here."""
    calibrate_background()
    calibrate_loss()


def main():
    if SIM_MODE:
        print("[SIM MODE] Running without hardware")

    run = True
    while run:
        n = input(
            "Do you want to:\n"
            "\t1. Set unitary and s0 input state\n"
            "\t2. Collect statistics\n"
            "\t3. Tune channel delays\n"
            "\t4. Perform tomography\n"
            "\t5. Calibrate background noise and loss\n"
            "\t6. Test antilatch server connection\n"
            "\t7. Unlatch detectors\n"
            "\t8. Keep detectors unlatched\n"
            )

        match n:
            case '1':
                # Set unitary and s0
                N = _ask_N()
                if N is None:
                    continue
                _set_unitary(N)
                _set_input_state(N, 0)
            case '2':
                N = _ask_N()
                if N is None:
                    continue
                states_choice = input(
                    "Input state(s):\n"
                    "\t1. Single\n"
                    "\t2. Multiple (choose specific s_j's)\n"
                    "\t3. All\n"
                    "\t0. Back\n"
                    "> ").strip()
                if _is_back(states_choice):
                    continue
                if states_choice == '2':
                    raw = input(f"Which j's, comma-separated (available: {_input_states(N)}): ").strip()
                    js = [int(j) for j in raw.split(',')] if raw else [0]
                elif states_choice == '3':
                    js = _input_states(N)
                else:
                    j = input("Which j? (Enter = 0): ").strip()
                    js = [int(j)] if j else [0]
                tomo = input("Perform output tomo for this input "
                             "(full collection time each, no plot)? [y/N] ").strip().lower() == 'y'
                measurement(N, performTomo=tomo, js=js)
            case '3':
                if SIM_MODE:
                    print("[SIM MODE] delay tuning needs hardware")
                else:
                    from libraries.countingcard import tune_delays
                    from libraries.settings import LOOP_CHS, DUMP_CH
                    chs = input(f"Channel(s) to tune, comma-separated "
                                f"(Enter = all {LOOP_CHS}; include {DUMP_CH} to also tune the dump, "
                                f"fixed regardless of process N): ").strip()
                    signal_chs = [int(c) for c in chs.split(',')] if chs else LOOP_CHS
                    t = input("Integration time per point, in seconds "
                              f"(Enter = per-channel default, ch{LOOP_CHS[0]} ~1.5s up to "
                              f"ch{LOOP_CHS[-1]} ~15s; or type a number to use it for every "
                              "channel): ").strip()
                    tune_delays(
                        signal_chs=signal_chs,
                        integration_time=float(t) if t else None,
                    )
            case '4':
                tomography_menu()
            case '5':
                calibrate_background_and_loss()
            case '6':
                ping_antilatch()
            case '7':
                if SIM_MODE:
                    print("[SIM MODE] no detectors to unlatch")
                else:
                    # reset_detectors only talks to the antilatch server over TCP;
                    # it never opens the counting card, so another app can keep reading
                    from hardware.detector import reset_detectors
                    if reset_detectors():
                        print("Detectors unlatched (bias voltages cycled)")
            case '8':
                if SIM_MODE:
                    print("[SIM MODE] no detectors to unlatch")
                else:
                    from hardware.detector import reset_detectors
                    period = float(input("Unlatch period, in seconds: ").strip())
                    print(f"Unlatching detectors every {period} s (Ctrl+C to stop)...")
                    try:
                        while True:
                            time.sleep(period)
                            if reset_detectors():
                                print("Detectors unlatched (bias voltages cycled)")
                    except KeyboardInterrupt:
                        print("\nPeriodic unlatching stopped.")
            case _:
                print("Please choose a valid option 1-8 from list:")


if __name__ == "__main__":
    if SIM_MODE:
        # self-check against a real current channel, not the old pre-shift
        # ch2 (settings.py: channels moved +2 after ch2 broke on the old card)
        ch = LOOP_CHS[0]
        d, row = _scan_and_record(ch, center=100.0, span=3.0, step=1.0, n_bins=1, record_bin_s=1.0)
        assert row['int_time'] == 1.0 and f'coinc_ch{ch}' in row
        assert len(row['bins']) == 1 and row['bins'][0][f'coinc_ch{ch}'] == 0
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
