"""
Prepare the s0 process state for a chosen unitary N:
sets HWP_IN/QWP_IN to s0_N and the fixed waveplates (IN_2/OUT_2) to that U's angles.

Run with AUTOTOMO_SIM=1 or --sim for mock hardware.
"""
import csv
import json
import os
import socket
import sys
import datetime
import time

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'

import libraries.tomography as tl
import libraries.settings as st
import libraries.plotting as plotting
from libraries.basis_vectors import process_state_angles, basis_angles
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

def _set_tomo_stages(HWP, QWP, basis):
    """ For tomo ordering QWP -> HWP """
    tl.move_stage(HWP, basis_angles[basis][0], COMPORT)
    tl.move_stage(QWP, basis_angles[basis][1], COMPORT)


def _sim_row(duration):
    return {'herald': 0,
            **{f'singles_ch{ch}': 0 for ch in DET_CHS},
            **{f'coinc_ch{ch}': 0 for ch in DET_CHS},
            'int_time': duration}

def _acquire_counts(duration, N):
    """Integrate counts for `duration` s with delays for process N."""
    if SIM_MODE:
        return _sim_row(duration)
    # imported here: hardware.detector loads the TimeTag DLL on import,
    # which doesn't exist in sim mode
    from libraries.countingcard import acquire_counts
    return acquire_counts(duration, delays=delays_for(N))

def _acquire_rows(N, total):
    """Yield 1 s count rows until `total` s are collected (None = until Ctrl-C)."""
    if SIM_MODE:
        done = 0.0
        while total is None or done < total:
            yield _sim_row(1.0)
            done += 1.0
        return
    from libraries.countingcard import acquire_rows
    yield from acquire_rows(total, delays=delays_for(N))

def _save_results(rows, N, label):
    """Write rows to data/{timestamp}_measurement_N{N}_s{label}.csv.

    Timestamp leads so filenames sort most-recent-last (ls default order).
    Called from finally — saves whatever rows exist even mid-sweep.
    """
    if not rows:
        print("No data to save")
        return
    os.makedirs('data', exist_ok=True)
    path = (f"data/{datetime.datetime.now():%Y%m%d_%H%M%S}_"
            f"measurement_N{N}_s{label}.csv")
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

def _ask_duration():
    """Total collection time in seconds per setting, or None to stream until Ctrl-C."""
    while True:
        m = input("Collect for how many minutes? (Enter = stream until Ctrl-C): ").strip()
        if not m:
            return None
        try:
            return float(m) * 60
        except ValueError:
            print("Enter a number of minutes, or press Enter to stream")

def measurement(N, performTomo=False, allInputs=False):
    """Collect statistics through unitary N in 1 s acquisitions, one row each.

    performTomo=False : collect at the current analyzer setting
    performTomo=True  : full 6-basis tomo sweep
    allInputs=False   : s0 input only
    allInputs=True    : repeat for every input state s{j}_N

    Asks for a total collection time per setting; Enter streams until Ctrl-C.
    Everything goes to one file; rows carry an input_state column (= j).
    Returns the list of result rows so callers can aggregate.
    """
    total = _ask_duration()
    _set_unitary(N)
    start = time.monotonic()

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

                try:
                    for counts in _acquire_rows(N, total):
                        rows.append({'N': N, 'input_state': j, 'basis': basis,
                                     'time': datetime.datetime.now().isoformat(),
                                     **counts})
                        print(f"[s{j} {basis or 'no-tomo'}] {counts}")
                except KeyboardInterrupt:
                    print("\nStopped — saving what we have")
                    return rows  # finally below still saves + notifies
    finally:
        # runs on success, error, or Ctrl-C — partial data still gets saved
        _save_results(rows, N, 'all' if allInputs else 0)
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


def perform_tomo():
    """Photon-counting tomography of the 2-port Sagnac gate for a chosen
    unitary N: sweep an input basis set through all 6 output bases, on each
    of the gate's two physical outputs in turn, then plot measured vs
    theoretical U for each.

    path 1 = ch2 (loop-1 exit) via TOM_1, OUT_2 fixed at the U-angle —
    the gate output that feeds the loop.
    path 2 = dump (ch7) via OUT_2 — a polariser sits behind the OUT_2
    plates in that arm, so OUT_2 is the correct analyzer here (not
    TOM_DUMP, a separate stage pair); getUnitary(path=2) already excludes
    hf2/qf2 from U to match. TOM_1 is fixed at the U-angle for this pass,
    and dump's delay is swapped to the straight-to-dump value since path 2
    is the un-looped gate output.

    These need two separate waveplate configurations (path=1 fixes OUT_2
    free/TOM_1 fixed vs path=2 fixes TOM_1 free/OUT_2 fixed), so each input
    basis gets measured in two full passes, not one shared sweep.
    """
    N = _ask_N()
    choice = input("Input sweep? (HVAD / HVADRL / Sj / Sall): ").strip().upper()
    if choice == 'HVAD':
        labels, set_input = tl.HVAD_BASES, _set_input_basis
    elif choice == 'HVADRL':
        labels, set_input = tl.FULL_BASES, _set_input_basis
    elif choice in ('SJ', 'SALL'):
        js = _input_states(N) if choice == 'SALL' else [0]
        labels = tuple(f's{j}_{N}' for j in js)
        set_input = lambda label: _set_input_state(N, int(label.split('_')[0][1:]))
    else:
        print("Invalid choice — pick HVAD, HVADRL, Sj, or Sall")
        return

    duration = _ask_tomo_integration()
    total_s = len(labels) * 2 * len(tl.FULL_BASES) * duration
    print(f"{len(labels)} inputs x 2 paths x 6 output bases x {duration:.0f}s = ~{total_s:.0f}s total")

    # --- Path 1: ch2 via TOM_1, OUT_2 fixed at U-angle ---
    _set_fixed_waveplates(unitaries_angles[N], path=1)
    _beep()
    data1 = {}
    for label in labels:
        print(f"\n=== Path 1 (ch{LOOP_CHS[0]}) | Input |{label}> ===")
        set_input(label)
        data1[label] = _sweep_output_bases(HWP_TOM_1, QWP_TOM_1, N, duration, LOOP_CHS[0])

    # --- Path 2: dump via OUT_2, TOM_1 fixed at U-angle, dump delay swapped ---
    _set_fixed_waveplates(unitaries_angles[N], path=2)
    normal_dump_delay = st.CHANNELS[DUMP_CH]['delay']
    st.CHANNELS[DUMP_CH]['delay'] = st.DUMP_STRAIGHT_DELAY
    print(f"Dump delay set to {st.DUMP_STRAIGHT_DELAY} ns (straight-to-dump, path 2)")
    data2 = {}
    try:
        for label in labels:
            print(f"\n=== Path 2 (dump) | Input |{label}> ===")
            set_input(label)
            data2[label] = _sweep_output_bases(HWP_OUT_2, QWP_OUT_2, N, duration, DUMP_CH)
    finally:
        st.CHANNELS[DUMP_CH]['delay'] = normal_dump_delay
        print(f"Dump delay restored to {normal_dump_delay} ns")

    angles = {**unitaries_angles[N], 'N': N, 'title': f'U{N}'}
    fit1 = plotting.plot_characterisation(data1, graph_title=f'U{N}_path1_ch{LOOP_CHS[0]}',
                                          angles=angles, plot_type=f'U{N}_path1', path=1)
    fit2 = plotting.plot_characterisation(data2, graph_title=f'U{N}_path2_dump',
                                          angles=angles, plot_type=f'U{N}_path2', path=2)
    print(f"path1 (ch{LOOP_CHS[0]}) fit residual: {fit1:.4f}  |  path2 (dump) fit residual: {fit2:.4f}")
    notify(f"Tomo U{N} done — fit1={fit1:.4f} fit2={fit2:.4f}",
           title="Tomography Complete", priority="high")


def read_outputs(duration=20.0):
    """Stream one output channel live: singles + coincidences with the herald.
    All delays are fixed now, so no unitary N is needed."""
    labels = {TRIGG_CH: 'herald',
              **{ch: f'loop{i + 1}' for i, ch in enumerate(LOOP_CHS)}, DUMP_CH: 'dump'}
    menu = ', '.join(f'{ch}={label}' for ch, label in labels.items())
    choice = input(f"Which channel? ({menu}): ").strip()
    try:
        ch = int(choice)
        labels[ch]
    except (ValueError, KeyError):
        print(f"Pick a channel number from: {menu}")
        return
    if SIM_MODE:
        print(f"[SIM MODE] would stream ch{ch} ({labels[ch]}) with delays {delays_for()}")
        return
    from libraries.countingcard import stream_herald_and_signal
    stream_herald_and_signal(signal_ch=ch, duration=duration, delays=delays_for())


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
            "\t2. Collect statistics without tomo\n"
            "\t3. Collect statistics with output tomo\n"
            "\t4. Collect statistics for each input s_j\n"
            "\t5. Test antilatch server connection\n"
            "\t6. Stream a channel\n"
            "\t7. Tune channel delays (±10 ns local scan + window check)\n"
            "\t8. Unlatch detectors (antilatch only, card untouched)\n"
            "\t9. Perform tomography (photon counting) + plot\n"
            )

        match n:
            case '1':
                # Set unitary and s0
                N = _ask_N()
                _set_unitary(N)
                _set_input_state(N, 0)
            case '2':
                measurement(_ask_N())
            case '3':
                measurement(_ask_N(), performTomo=True)
            case '4':
                measurement(_ask_N(), allInputs=True)
            case '5':
                ping_antilatch()
            case '6':
                read_outputs()
            case '7':
                if SIM_MODE:
                    print("[SIM MODE] delay tuning needs hardware")
                else:
                    from libraries.countingcard import tune_delays
                    tune_delays()
            case '8':
                if SIM_MODE:
                    print("[SIM MODE] no detectors to unlatch")
                else:
                    # reset_detectors only talks to the antilatch server over TCP;
                    # it never opens the counting card, so another app can keep reading
                    from hardware.detector import reset_detectors
                    if reset_detectors():
                        print("Detectors unlatched (bias voltages cycled)")
            case '9':
                perform_tomo()
            case _:
                print("Please choose a valid option 1-9 from list:")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — stages disabled.")
