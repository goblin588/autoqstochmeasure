"""
Prepare the s0 process state for a chosen unitary N:
sets HWP_IN/QWP_IN to s0_N and the fixed waveplates (IN_2/OUT_2) to that U's angles.

Run with AUTOTOMO_SIM=1 or --sim for mock hardware.
"""
import csv
import json
import os
import socket
import subprocess
import sys
import datetime
import time
from pathlib import Path

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'

import libraries.tomography as tl
import libraries.settings as st
import libraries.plotting as plotting
from libraries.basis_vectors import process_state_angles, basis_angles, tomo_angles
from libraries.settings import HWP_IN, QWP_IN, COMPORT, SIM_MODE
from libraries.waveplate_angles import unitaries_angles
from libraries.settings import (HWP_IN, QWP_IN, QWP_TOM_DUMP, HWP_TOM_DUMP,
                                HWP_IN_2, QWP_IN_2, HWP_OUT_2, QWP_OUT_2,
                                HWP_TOM_1, QWP_TOM_1, COMPORT, SIM_MODE,
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

def _remind_switch_dwell(N):
    """Switch dwell is a manual hardware setting, not something this program
    can drive — print the calibrated value (SWITCH_DWELL column) for process
    N so the operator sets it before counting starts."""
    dwell = st.SWITCH_DWELL_NS.get(int(N))
    if dwell is None:
        print(f"Set switch dwell manually for N={N} (not calibrated yet)")
    else:
        print(f"Set switch dwell to {dwell} ns (N={N})")

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


def _save_results(rows, N, label):
    """Write rows to data/{timestamp}_measurement_N{N}_s{label}.csv, plus a
    same-named .json sidecar recording the delays/thresholds/etc. in effect
    for the run — so old data stays interpretable after later recalibration.

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
        # filename only (not a full path) so this stays valid whichever
        # clone/checkout the data/ directory ends up analysed from
        'noise_calibration': ({'file': calibration.name, 'saved_at': _calibration_date(calibration)}
                              if calibration else None),
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


def calibrate_background():
    """Per-channel background/accidental coincidence rate: every channel's
    delay is bumped +st.BACKGROUND_OFFSET_NS ns off its tuned value (herald
    left alone), so the coincidence window misses the real photon arrival
    and only counts accidentals — no physical beam blocking needed.

    Saves data/{timestamp}_noise_calibration.json.
    """
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
        return kwargs.get('center', 0.0), _sim_row(kwargs.get('record_duration', 60.0), [ch])
    from libraries.countingcard import scan_and_record
    return scan_and_record(ch, **kwargs)


def _measure_background(ch, **kwargs):
    """SIM-guarded wrapper around countingcard.measure_background."""
    if SIM_MODE:
        return 0.0, {}
    from libraries.countingcard import measure_background
    return measure_background(ch, **kwargs)


def _find_latest_loss_calibration():
    """Most recent data/*_loss_calibration.json, parsed — or (None, {}) if
    none exist yet. Same glob/mtime pattern as _latest_calibration()."""
    files = sorted(Path(st.DATA_DIR).glob('*_loss_calibration.json'), key=lambda p: p.stat().st_mtime)
    if not files:
        return None, {}
    path = files[-1]
    return path, json.loads(path.read_text())


def _loss_stage(existing_stages, key, run):
    """Check for an existing measurement of `key` (from a prior, possibly
    interrupted, loss calibration); ask whether to reuse it or redo the
    stage. `run()` performs the stage's prompts/waveplate moves/scan and
    returns its result dict when redoing. Either way, returns the stage
    dict with 'saved_at' set."""
    prior = existing_stages.get(key)
    if prior is not None:
        when = prior.get('saved_at', 'unknown date')
        choice = input(f"\nExisting '{key}' measurement from {when} found — "
                        f"use it, or redo this stage? [Use/redo]: ").strip().lower()
        if not choice.startswith('r'):
            print(f"Using existing '{key}' data — skipping this stage.")
            return prior
    result = run()
    result['saved_at'] = datetime.datetime.now().isoformat()
    return result


def _set_bypass_optics():
    """Zero-loop bypass: input H, loop-input plates at 0 (nothing rotated
    into the loop), exit plate at 45° sends it straight back out. Sets
    every plate this stage depends on — self-contained so it's safe to run
    even if an earlier stage was skipped via resume."""
    _set_input_basis('H')
    tl.move_stage(HWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_IN_2, 0, COMPORT)
    tl.move_stage(QWP_OUT_2, 0, COMPORT)
    print("Setting HWP_OUT_2 to 45°")
    tl.move_stage(HWP_OUT_2, 45, COMPORT)


def _set_loop_optics():
    """One loop pass: input H, loop-input plates rotate H->V so the photon
    actually circulates ("H to V, just HWP at 45"), exit plate at 45° sends
    it (or the switch) back out. Self-contained, same reasoning as
    _set_bypass_optics."""
    _set_input_basis('H')
    tl.move_stage(QWP_OUT_2, 0, COMPORT)
    print("Setting HWP_OUT_2 to 45°")
    tl.move_stage(HWP_OUT_2, 45, COMPORT)
    hwp_v, qwp_v = basis_angles['V']
    tl.move_stage(HWP_IN_2, hwp_v, COMPORT)
    tl.move_stage(QWP_IN_2, qwp_v, COMPORT)


def calibrate_loss():
    """Guided 5-stage loss calibration:
      0. source baseline, signal straight to the output detector      -> C0
      1. source baseline, signal straight to the DUMP detector        -> C0_dump
      2. zero-loop bypass, signal into setup, exits without looping   -> C_ch2
      3. one loop pass, exits via the normal loop-output port         -> C_ch4
      4. one loop pass, switch diverts to the dump port/detector      -> C_dump

    Stages 0 and 1 are both raw, setup-free baselines (herald+signal direct
    to a detector) — one through the output detector, one through the dump
    detector — since the two are physically different detectors and may not
    share a detection efficiency. Each is followed by a background check: a
    single read at that stage's found peak delay +15ns (same
    BACKGROUND_OFFSET_NS convention as calibrate_background/tune_delays),
    far enough off the real peak to see how much of C0/C0_dump is accidental
    floor rather than real coincidences.

    loss_zero_loops = C_ch2/C0, loss_per_loop_pass = C_ch4/C_ch2,
    loss_to_dump = C_dump/C_ch4 (extra factor on top of one loop pass, using
    the loop-output detector as reference), loss_to_dump_raw = C_dump/C0_dump
    (same numerator, but referenced to the dump detector's own raw baseline
    instead — use whichever is the meaningful comparison for your model).

    Resumable: saves after every stage (not just at the end), to
    data/{timestamp}_loss_calibration.json. If a previous (possibly
    interrupted) run's file exists, its stages are offered for reuse one at
    a time instead of redoing them — so a bad dump reading, say, doesn't
    mean redoing the source/ch2/ch4 stages too. Reusing continues writing
    into that same file; starting fresh (no prior file, or redoing every
    stage) creates a new one.
    """
    # Stages 0/1 are a bare source->detector connection, not the setup's
    # usual fiber path — the calibrated herald delay (~3841ns, tuned for
    # that usual path) doesn't apply here, so both the peak search and the
    # background check pin herald to this instead.
    raw_herald_delay = 10.0
    duration = _ask_calibration_duration(default=30.0)

    path, existing = _find_latest_loss_calibration()
    existing_stages = existing.get('stages', {})
    if existing_stages:
        print(f"Found an existing loss calibration ({path.name}) with stages: "
              f"{', '.join(existing_stages)} — you'll be asked per stage whether to reuse them.")

    stages = {}

    def _save(losses=None):
        nonlocal path
        if path is None:
            os.makedirs(st.DATA_DIR, exist_ok=True)
            path = Path(f"{st.DATA_DIR}/{datetime.datetime.now():%Y%m%d_%H%M%S}_loss_calibration.json")
        meta = {
            'stages': stages,
            'duration_s': duration,
            'git_commit': _git_commit(),
            'saved_at': datetime.datetime.now().isoformat(),
        }
        if losses is not None:
            meta['losses'] = losses
        path.write_text(json.dumps(meta, indent=1))
        print(f"  (saved -> {path.name})")
        return meta

    def _run_source():
        input("\nStage 0/4: plug both herald and signal directly into detectors "
              "(output detector), press Enter when ready...")
        ch0 = input("Detector channel the bare signal fiber landed on (default 2): ").strip()
        ch0 = int(ch0) if ch0 else 2
        delay0, row0 = _scan_and_record(ch0, absolute_range=(0.0, 20.0), step=1.0,
                                         record_duration=duration, herald_delay=raw_herald_delay)
        print(f"Checking background (herald={raw_herald_delay:.0f}ns, ch @ peak+15ns)...")
        bg0, bg0_point = _measure_background(ch0, peak_delay=delay0, herald_delay=raw_herald_delay)
        return {'ch': ch0, 'delay_ns': delay0, 'counts': row0,
                'background_hz': bg0, 'background_point': bg0_point}

    stages['source'] = _loss_stage(existing_stages, 'source', _run_source)
    _save()

    def _run_source_dump():
        input("\nStage 1/4: plug signal directly into the DUMP detector "
              "(herald stays connected), press Enter when ready...")
        delay0d, row0d = _scan_and_record(st.DUMP_CH, absolute_range=(0.0, 20.0), step=1.0,
                                           record_duration=duration, herald_delay=raw_herald_delay)
        print(f"Checking background (herald={raw_herald_delay:.0f}ns, ch @ peak+15ns)...")
        bg0d, bg0d_point = _measure_background(st.DUMP_CH, peak_delay=delay0d, herald_delay=raw_herald_delay)
        return {'ch': st.DUMP_CH, 'delay_ns': delay0d, 'counts': row0d,
                'background_hz': bg0d, 'background_point': bg0d_point}

    stages['source_dump'] = _loss_stage(existing_stages, 'source_dump', _run_source_dump)
    _save()

    def _run_ch2():
        input("\nStage 2/4: plug signal into the setup, press Enter when ready...")
        _set_bypass_optics()
        delay2, row2 = _scan_and_record(2, center=st.CHANNELS[2]['delay'], span=3.0,
                                         record_duration=duration)
        return {'ch': 2, 'delay_ns': delay2, 'counts': row2}

    stages['ch2'] = _loss_stage(existing_stages, 'ch2', _run_ch2)
    _save()

    def _run_ch4():
        print("\nStage 3/4: one-loop pass — no fiber changes needed.")
        _set_loop_optics()
        delay4, row4 = _scan_and_record(4, center=st.CHANNELS[4]['delay'], span=3.0,
                                         record_duration=duration)
        return {'ch': 4, 'delay_ns': delay4, 'counts': row4}

    stages['ch4'] = _loss_stage(existing_stages, 'ch4', _run_ch4)
    _save()

    def _run_dump():
        _set_loop_optics()
        input("\nStage 4/4: set the switch to dump after 1 loop (dwell 60 ns) on the "
              "switch control program, press Enter when ready...")
        delay7, row7 = _scan_and_record(st.DUMP_CH, center=st.DUMP_DELAYS[1], span=3.0,
                                         record_duration=duration)
        return {'ch': st.DUMP_CH, 'delay_ns': delay7, 'counts': row7}

    stages['dump'] = _loss_stage(existing_stages, 'dump', _run_dump)

    def rate(stage_key):
        s = stages[stage_key]
        return s['counts'][f"coinc_ch{s['ch']}"] / s['counts']['int_time'] if s['counts']['int_time'] else 0.0
    C0, C0d, C2, C4, Cd = rate('source'), rate('source_dump'), rate('ch2'), rate('ch4'), rate('dump')

    losses = {
        'loss_zero_loops':    C2 / C0 if C0 else None,
        'loss_per_loop_pass': C4 / C2 if C2 else None,
        'loss_to_dump':       Cd / C4 if C4 else None,
        'loss_to_dump_raw':   Cd / C0d if C0d else None,
    }
    meta = _save(losses=losses)
    print(f"\nSaved -> {path}")
    print(f"losses: {losses}")
    notify("Loss calibration done", title="Calibration Complete")
    return meta


def _maybe_calibrate():
    """Offer to (re)run background calibration before a measurement, showing
    when it was last done."""
    latest = _latest_calibration()
    if latest is None:
        if input("No background calibration on file yet. Run one now? [Y/n] ").strip().lower() in ('', 'y'):
            calibrate_background()
        return
    ans = input(f"Last background calibration: {_calibration_date(latest)} — "
               "perform a new one now? [y/N] ").strip().lower()
    if ans == 'y':
        calibrate_background()

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


def measurement(N, performTomo=False, js=None):
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
    Returns the list of result rows so callers can aggregate.
    """
    _maybe_calibrate()

    js = js if js is not None else [0]
    bases = ['H', 'V', 'A', 'D', 'R', 'L'] if performTomo else [None]
    settings = [(j, b) for j in js for b in bases]

    while True:
        total = _ask_duration()
        round_robin = _should_round_robin(total, len(settings))
        if total is None:
            break
        print(f"This measurement will take {_format_duration(total * len(settings))}.")
        if input("Press Enter to begin, or c to change the duration: ").strip().lower() != 'c':
            break

    _set_unitary(N)
    _remind_switch_dwell(N)
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
        _save_results(rows, N, label)
        notify(f"Measurement N={N} done ({len(rows)} rows)",
               title="Measurement Complete", priority="high")
        if time.monotonic() - start > 300:
            _play_tune()
    return rows


def _ask_N():
    while True:
        N = input(f"Which unitary N? ({'/'.join(unitaries_angles)}): ").strip()
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
    """ch2 via TOM_1, OUT_2 fixed at the U-angle — the gate output that
    feeds the loop. Returns {input_label: {output_basis: (count, err)}}."""
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
    ch2/loop-1 reading) for the duration, then restored.
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
    choice = input(
        "Input sweep?\n"
        "\t1. HVAD (4 generic polarisation bases)\n"
        "\t2. HVADRL (6 generic polarisation bases)\n"
        "\t3. Sj (single process state s0)\n"
        "\t4. Sall (every process state s_j for this N)\n"
        "\t5. Single basis (H/V/A/D/R/L)\n"
        "> ").strip()
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
        "\t1. Path 1 only (ch2 via TOM_1)\n"
        "\t2. Path 2 only (dump via OUT_2)\n"
        "\t3. Both\n"
        "> ").strip()
    if path_choice not in ('1', '2', '3'):
        print("Invalid choice — pick 1-3")
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
    path_choice = input(
        "Which path?\n"
        "\t1. Path 1 (ch2 via TOM_1)\n"
        "\t2. Path 2 (dump via OUT_2)\n"
        "> ").strip()
    if path_choice not in ('1', '2'):
        print("Invalid choice — pick 1 or 2")
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


def main():
    if SIM_MODE:
        print("[SIM MODE] Running without hardware")

    run = True
    while run:
        n = input(
            "Do you want to:\n"
            "\t1. Set unitary and s0 input state\n"
            "\t2. Collect statistics\n"
            "\t3. Test antilatch server connection\n"
            "\t4. Tune channel delays (zooms in to a precise value)\n"
            "\t5. Unlatch detectors (antilatch only, card untouched)\n"
            "\t6. Perform tomography (photon counting) + plot\n"
            "\t7. Check single input/output projector (phase tuning)\n"
            "\t8. Calibrate background noise (block/herald/setup, 3 steps)\n"
            "\t9. Calibrate loss (guided, 5 stages)\n"
            )

        match n:
            case '1':
                # Set unitary and s0
                N = _ask_N()
                _set_unitary(N)
                _set_input_state(N, 0)
            case '2':
                N = _ask_N()
                states_choice = input(
                    "Input state(s):\n"
                    "\t1. Single\n"
                    "\t2. Multiple (choose specific s_j's)\n"
                    "\t3. All\n"
                    "> ").strip()
                if states_choice == '2':
                    raw = input(f"Which j's, comma-separated (available: {_input_states(N)}): ").strip()
                    js = [int(j) for j in raw.split(',')] if raw else [0]
                elif states_choice == '3':
                    js = _input_states(N)
                else:
                    j = input("Which j? (Enter = 0): ").strip()
                    js = [int(j)] if j else [0]
                tomo = input("Perform output tomo? [y/N] ").strip().lower() == 'y'
                measurement(N, performTomo=tomo, js=js)
            case '3':
                ping_antilatch()
            case '4':
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
                              "(Enter = per-channel default, ch2 ~1.5s up to ch12 ~15s; "
                              "or type a number to use it for every channel): ").strip()
                    tune_delays(
                        signal_chs=signal_chs,
                        integration_time=float(t) if t else None,
                    )
            case '5':
                if SIM_MODE:
                    print("[SIM MODE] no detectors to unlatch")
                else:
                    # reset_detectors only talks to the antilatch server over TCP;
                    # it never opens the counting card, so another app can keep reading
                    from hardware.detector import reset_detectors
                    if reset_detectors():
                        print("Detectors unlatched (bias voltages cycled)")
            case '6':
                perform_tomo()
            case '7':
                check_projector()
            case '8':
                calibrate_background()
            case '9':
                calibrate_loss()
            case _:
                print("Please choose a valid option 1-9 from list:")


if __name__ == "__main__":
    if SIM_MODE:
        d, row = _scan_and_record(2, center=100.0, span=3.0, step=1.0, record_duration=1.0)
        assert row['int_time'] == 1.0 and 'coinc_ch2' in row
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
