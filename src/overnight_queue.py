"""
Build a queue of calibration/measurement steps (tune delays, loss
calibration, unitary measurements) in any order, save/load it as JSON, and
run it unattended overnight -- one bad step logs + notifies + moves on, a
deliberate Ctrl-C stops the whole queue.

Run with AUTOTOMO_SIM=1 or --sim for mock hardware.
Run with DUMP_ENABLED=0 or --no-dump if the dump detector isn't connected.
"""
import os
import sys

if '--sim' in sys.argv:
    os.environ['AUTOTOMO_SIM'] = '1'
if '--no-dump' in sys.argv:
    os.environ['DUMP_ENABLED'] = '0'

import datetime
import json
import traceback
from pathlib import Path

import libraries.settings as st
from libraries.settings import LOOP_CHS, DUMP_CH, SIM_MODE
from libraries.notifier import notify
import measurement as meas


LOSS_STAGES = [
    ('loop01', 'Zero-loop + one-loop pass, together'),
    ('5050',   '50/50 split, all channels (independent cross-check)'),
]


def _describe(step):
    t = step['type']
    if t == 'tune':
        return f"Tune delays: channels={step['signal_chs']}, integration_time={step['integration_time']}"
    if t == 'loss':
        return f"Loss measurement: stage={step['stage']}"
    if t == 'measurement':
        return (f"Measurement: N={step['N']}, js={step['js']}, "
                f"tomo={step['tomo']}, duration_s={step['duration_s']}")
    return str(step)


def _ask_tune_step():
    chs = input(f"Channel(s) to tune, comma-separated "
                f"(Enter = all {LOOP_CHS}; include {DUMP_CH} to also tune the dump, "
                f"fixed regardless of process N): ").strip()
    signal_chs = [int(c) for c in chs.split(',')] if chs else list(LOOP_CHS)
    t = input("Integration time per point, in seconds "
              f"(Enter = per-channel default, ch{LOOP_CHS[0]} ~1.5s up to "
              f"ch{LOOP_CHS[-1]} ~15s; or type a number to use it for every "
              "channel): ").strip()
    return {'type': 'tune', 'signal_chs': signal_chs,
            'integration_time': float(t) if t else None}


def _ask_loss_step():
    print("Loss-measurement stage:")
    for i, (key, label) in enumerate(LOSS_STAGES, 1):
        print(f"\t{i}. {label}")
    choice = input("> ").strip()
    try:
        key, _ = LOSS_STAGES[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice")
        return None
    return {'type': 'loss', 'stage': key}


def _ask_measurement_step():
    N = meas._ask_N()
    states_choice = input(
        "Input state(s):\n"
        "\t1. Single\n"
        "\t2. Multiple (choose specific s_j's)\n"
        "\t3. All\n"
        "> ").strip()
    if states_choice == '2':
        raw = input(f"Which j's, comma-separated (available: {meas._input_states(N)}): ").strip()
        js = [int(j) for j in raw.split(',')] if raw else [0]
    elif states_choice == '3':
        js = 'all'  # resolved against _input_states(N) at run time, not here
    else:
        j = input("Which j? (Enter = 0): ").strip()
        js = [int(j)] if j else [0]
    tomo = input("Sweep all 6 analyzer bases for this input "
                 "(full collection time each, no plot)? [y/N] ").strip().lower() == 'y'
    duration_s = meas._ask_duration()
    return {'type': 'measurement', 'N': N, 'js': js, 'tomo': tomo, 'duration_s': duration_s}


_BUILDERS = {
    '1': ('Tune channel delays', _ask_tune_step),
    '2': ('Loss measurement', _ask_loss_step),
    '3': ('Unitary measurement', _ask_measurement_step),
}


def build_queue():
    """Interactive menu loop -- add any number of steps, in any order, then
    '0. Done'. Shows the queue-so-far after every change."""
    queue = []
    while True:
        print("\nQueue so far:")
        if not queue:
            print("  (empty)")
        else:
            for i, step in enumerate(queue, 1):
                print(f"  {i}. {_describe(step)}")
        choice = input(
            "\n1. Tune channel delays\n"
            "2. Loss measurement\n"
            "3. Unitary measurement\n"
            "4. Remove a step\n"
            "0. Done\n"
            "> ").strip()
        if choice == '0':
            return queue
        if choice == '4':
            if not queue:
                print("Queue is empty")
                continue
            idx = input("Remove which step number? ").strip()
            try:
                queue.pop(int(idx) - 1)
            except (ValueError, IndexError):
                print("Invalid step number")
            continue
        if choice in _BUILDERS:
            _, builder = _BUILDERS[choice]
            step = builder()
            if step:
                queue.append(step)
        else:
            print("Invalid choice")


def save_queue(queue, path=None):
    os.makedirs(st.DATA_DIR, exist_ok=True)
    path = Path(path) if path else Path(st.DATA_DIR) / f"{datetime.datetime.now():%Y%m%d_%H%M%S}_overnight_queue.json"
    path.write_text(json.dumps(queue, indent=1))
    print(f"Saved queue -> {path}")
    return path


def load_queue(path):
    return json.loads(Path(path).read_text())


def _run_step(step):
    """Dispatch one queue step. Raises on failure -- run_queue() handles
    logging/notifying/continuing."""
    t = step['type']
    if t == 'tune':
        if SIM_MODE:
            # Same guard as measurement.py main() option 4 -- tune_delays
            # needs the real counting card even to import (pythonnet/TimeTag).
            print("[SIM MODE] delay tuning needs hardware -- skipping")
            return
        from libraries.countingcard import tune_delays
        tune_delays(signal_chs=step.get('signal_chs') or LOOP_CHS,
                    integration_time=step.get('integration_time'),
                    auto_save=True)
    elif t == 'loss':
        meas.calibrate_loss(run_stages=[step['stage']])
    elif t == 'measurement':
        js = step['js']
        if js == 'all':
            js = meas._input_states(step['N'])
        meas.measurement(step['N'], performTomo=step['tomo'], js=js,
                          duration_s=step['duration_s'], auto=True)
    else:
        raise ValueError(f"Unknown step type: {t!r}")


def run_queue(queue):
    """Run every step in order. A step that raises is logged + notified and
    the queue continues; a KeyboardInterrupt stops the whole queue instead.
    Writes data/{timestamp}_queue_log.json as it goes, not just at the end."""
    os.makedirs(st.DATA_DIR, exist_ok=True)
    log_path = Path(st.DATA_DIR) / f"{datetime.datetime.now():%Y%m%d_%H%M%S}_queue_log.json"
    log = {'started_at': datetime.datetime.now().isoformat(), 'steps': []}

    def _write_log():
        log_path.write_text(json.dumps(log, indent=1))

    ok = failed = 0
    try:
        for i, step in enumerate(queue, 1):
            entry = {'index': i, 'step': step, 'started_at': datetime.datetime.now().isoformat()}
            print(f"\n=== Step {i}/{len(queue)}: {_describe(step)} ===")
            try:
                _run_step(step)
                entry['status'] = 'ok'
                ok += 1
            except Exception as e:
                entry['status'] = 'failed'
                entry['error'] = str(e)
                entry['traceback'] = traceback.format_exc()
                failed += 1
                print(f"Step {i} FAILED: {e}\n{entry['traceback']}")
                notify(f"Queue step {i} failed: {_describe(step)} -- {e}",
                       title="Queue Step Failed", priority="high")
            entry['finished_at'] = datetime.datetime.now().isoformat()
            log['steps'].append(entry)
            _write_log()
    except KeyboardInterrupt:
        log['stopped_by'] = 'KeyboardInterrupt'
        _write_log()
        print("\nQueue interrupted by Ctrl-C -- stopping the whole queue.")
        notify(f"Queue interrupted by Ctrl-C after {ok} ok / {failed} failed",
               title="Queue Interrupted", priority="high")
        return log

    log['finished_at'] = datetime.datetime.now().isoformat()
    log['ok'], log['failed'] = ok, failed
    _write_log()
    print(f"\nQueue finished: {ok} ok, {failed} failed -> {log_path}")
    notify(f"Overnight queue done: {ok} ok, {failed} failed",
           title="Queue Complete", priority="high")
    return log


def main():
    if SIM_MODE:
        print("[SIM MODE] Running without hardware")

    choice = input("1. Build a new queue\n2. Load a saved queue file\n> ").strip()
    if choice == '2':
        queue = load_queue(input("Queue file path: ").strip())
    else:
        queue = build_queue()
        if queue and input("Save this queue to a file for later? [y/N] ").strip().lower() == 'y':
            save_queue(queue)

    if not queue:
        print("Empty queue -- nothing to run")
        return

    print("\nFinal queue:")
    for i, step in enumerate(queue, 1):
        print(f"  {i}. {_describe(step)}")

    if input("\nRun this queue now? [y/N] ").strip().lower() != 'y':
        print("Not running.")
        return

    run_queue(queue)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
