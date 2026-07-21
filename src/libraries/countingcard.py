from hardware.detector import Logic16
from libraries.settings import TRIGG_CH, DET_CHS, DUMP_CH, LOOP_CHS, COINCIDENCE_WINDOW, DELAYS, THRESHOLDS
import time
import numpy as np

def acquire_counts(
    duration: float = 20.0,
    herald_ch: int = TRIGG_CH,
    signal_chs: list = DET_CHS,
    coincidence_window: float = COINCIDENCE_WINDOW,
    delays: list = DELAYS,
):
    """
    Integrates counts for `duration` seconds and returns totals as a dict:
    {'herald': ..., 'singles_ch{n}': ..., 'coinc_ch{n}': ..., 'int_time': ...}

    Antilatch-safe via read_counts_integrated. int_time is the actual
    counting time, which can be less than duration if latch events ate
    timeslices — divide counts by it for rates.
    """
    with Logic16(coincidence_window=coincidence_window, logic_mode=True,
                 integration_window=duration) as logic:
        logic.configure(threshold=THRESHOLDS, coincidence_window=coincidence_window, delays=delays)
        c_counts, s_counts, int_time = logic.read_counts_integrated(
            pos_singles=[herald_ch, *signal_chs],
            pos_coincidence=[[herald_ch, ch] for ch in signal_chs],
        )

    row = {'herald': int(s_counts[0])}
    for i, ch in enumerate(signal_chs):
        row[f'singles_ch{ch}'] = int(s_counts[i + 1])
        row[f'coinc_ch{ch}'] = int(c_counts[i])
    row['int_time'] = int_time
    return row


def acquire_rows(
    total: float | None = None,
    integration: float = 1.0,
    herald_ch: int = TRIGG_CH,
    signal_chs: list = DET_CHS,
    coincidence_window: float = COINCIDENCE_WINDOW,
    delays: list = DELAYS,
):
    """Yield one totals-row per `integration` s (same schema as acquire_counts),
    keeping the card open between rows. total=None streams until the caller
    stops iterating (e.g. Ctrl-C); otherwise stops once `total` s are counted.
    """
    with Logic16(coincidence_window=coincidence_window, logic_mode=True,
                 integration_window=integration) as logic:
        logic.configure(threshold=THRESHOLDS, coincidence_window=coincidence_window, delays=delays)
        counted = 0.0
        while total is None or counted < total:
            c_counts, s_counts, int_time = logic.read_counts_integrated(
                pos_singles=[herald_ch, *signal_chs],
                pos_coincidence=[[herald_ch, ch] for ch in signal_chs],
            )
            row = {'herald': int(s_counts[0])}
            for i, ch in enumerate(signal_chs):
                row[f'singles_ch{ch}'] = int(s_counts[i + 1])
                row[f'coinc_ch{ch}'] = int(c_counts[i])
            row['int_time'] = int_time
            counted += int_time
            yield row


def stream_herald_and_signal(
    herald_ch: int = TRIGG_CH,
    signal_ch: int = DET_CHS[0],
    duration: float = 20.0,
    coincidence_window: float = COINCIDENCE_WINDOW,
    delays: list = DELAYS,
):
    """
    Streams singles counts from a herald channel and a single signal channel,
    plus their coincidence rate, in near-real-time.

    Args:
        herald_ch: Herald/trigger channel number.
        signal_ch: Signal detector channel number.
        duration: How long to stream for, in seconds.
        coincidence_window: Coincidence window in ns.
        delays: List of per-channel delays (index = channel - 1).
    """
    singles_chs = [herald_ch, signal_ch]
    coincidence_chs = [[herald_ch, signal_ch]]

    print(f"Streaming herald (ch {herald_ch}) and signal (ch {signal_ch})...")

    with Logic16(coincidence_window=coincidence_window, logic_mode=True) as logic:
        logic.configure(threshold=THRESHOLDS, coincidence_window=coincidence_window, delays=delays)

        start_time = time.time()
        last = time.monotonic()
        while (time.time() - start_time) < duration:
            c_counts, s_counts, _timecounter = logic.read_counts(
                pos_coincidence=coincidence_chs,
                pos_singles=singles_chs,
            )
            now = time.monotonic()
            delta_t = now - last
            last = now

            herald_rate = s_counts[0] / delta_t
            signal_rate = s_counts[1] / delta_t
            coinc_rate = c_counts[0] / delta_t

            print(
                f"Herald (ch {herald_ch}): {herald_rate:.1f} Hz | "
                f"Signal (ch {signal_ch}): {signal_rate:.1f} Hz | "
                f"Coincidences: {coinc_rate:.1f} Hz | "
                f"Δt: {delta_t:.4f} s"
            )

            time.sleep(0.05)


# rework to return a pandas dataframe with titles and counts maybe, maybe make a yield thing
def stream_channels_with_delays(
    herald_ch: int = TRIGG_CH,
    signal_chs: list = DET_CHS,
    coincidence_window: float = COINCIDENCE_WINDOW,
    delays: list = DELAYS,
    integration_window: float = 0.5,
):
    """
    Accumulates coincidence counts between a herald channel and multiple signal
    channels, each with an independent delay set via the delays list.
    Uses read_counts_integrated for robust antilatch-safe accumulation.

    Args:
        herald_ch: Herald/trigger channel number.
        signal_chs: List of signal detector channel numbers.
        coincidence_window: Coincidence window in ns.
        delays: List of per-channel delays (index = channel - 1).
        integration_window: Integration time in seconds per measurement.
    """
    singles_chs = [herald_ch, *signal_chs]
    coincidence_chs = [[herald_ch, ch] for ch in signal_chs]

    print(f"Scanning coincidences: herald ch {herald_ch} vs signal chs {signal_chs}")
    print(f"Delays (ns): { {ch: delays[ch - 1] for ch in signal_chs} }")

    with Logic16(
        coincidence_window=coincidence_window,
        logic_mode=True,
        integration_window=integration_window,
    ) as logic:
        logic.configure(threshold=THRESHOLDS, coincidence_window=coincidence_window, delays=delays)

        c_counts, s_counts, total_time = logic.read_counts_integrated(
            pos_coincidence=coincidence_chs,
            pos_singles=singles_chs,
        )

        # Live singles summary
        print("\n=== Singles Rates ===")
        for ch, count in zip(singles_chs, s_counts):
            print(f"  Ch {ch}: {count / total_time:.1f} Hz")

        print("\n=== Coincidence Counts ===")
        for idx, pair in enumerate(coincidence_chs):
            count = c_counts[idx]
            rate = count / total_time if total_time > 0 else 0.0
            delay = delays[pair[1] - 1]
            print(
                f"  Ch {pair[0]} & Ch {pair[1]} "
                f"(delay {delay} ns): "
                f"{count} counts  |  {rate:.2f} Hz avg  |  "
                f"total time {total_time:.2f} s"
            )


def tune_delays(
    step: float = 2.0,
    span: float = 10.0,
    integration_time: float = 0.25,
    signal_chs: list = LOOP_CHS,  # dump is fixed at 1220, not scanned by default
    herald_ch: int = TRIGG_CH,
):
    """Re-centre each signal channel's delay after drift (scan ±span ns in
    `step` ns moves, keep the delay with the highest coincidence rate).

    Scan points only need the argmax, so a short `integration_time` per point
    suffices; bump it up if a low-rate channel's scan looks like noise.

    The best value per channel is written back into settings.CHANNELS, so
    delays_for() — and every later acquisition this session — uses the tuned
    values. Answer y at the prompt to persist them to calibration.json
    (loaded over the hardcoded defaults on import).

    Finishes with a coincidence-window check at 3/2/1 ns and recommends the
    smallest window that keeps >=90% of the 3 ns rate.
    """
    import libraries.settings as st
    offsets = np.arange(-span, span + step / 2, step)
    with Logic16(coincidence_window=COINCIDENCE_WINDOW, logic_mode=True,
                 integration_window=integration_time) as logic:
        logic.configure(threshold=THRESHOLDS, coincidence_window=COINCIDENCE_WINDOW)
        print(f"Tuning {len(signal_chs)} channels, {len(offsets)} points each at "
              f"{integration_time:.2g} s/point (~{len(signal_chs) * len(offsets) * integration_time:.0f} s total)")
        for i, ch in enumerate(signal_chs, 1):
            delays = st.delays_for()
            current = delays[ch - 1]
            print(f"[{i}/{len(signal_chs)}] scanning ch{ch} around {current:.0f} ns:", flush=True)
            rates = []
            for off in offsets:
                delays[ch - 1] = current + off
                logic.set_delays(delays)
                c, _s, t = logic.read_counts_integrated(
                    pos_singles=[herald_ch, ch],
                    pos_coincidence=[[herald_ch, ch]])
                rates.append(c[0] / t if t > 0 else 0.0)
                print(f"  {current + off:+7.0f} ns: {rates[-1]:8.1f} Hz", flush=True)
            best = float(current + offsets[int(np.argmax(rates))])
            st.CHANNELS[ch]['delay'] = best
            print(f"ch{ch}: {current:.0f} -> {best:.0f} ns (CHANNELS[{ch}]), "
                  f"peak {max(rates):.1f} Hz")

        # window check at the tuned delays; back to 1 s/point — this sets the
        # recommended global window, so it gets real stats unlike the scan
        logic._integration_window = 1.0
        print("Checking coincidence windows at the tuned delays (3 s)...", flush=True)
        logic.set_delays(st.delays_for())
        rate_at = {}
        for window in (3.0, 2.0, 1.0):
            logic.set_coincidence_window(window)
            c, _s, t = logic.read_counts_integrated(
                pos_singles=[herald_ch, *signal_chs],
                pos_coincidence=[[herald_ch, ch] for ch in signal_chs])
            rate_at[window] = sum(c) / t if t > 0 else 0.0
            print(f"window {window:.0f} ns: {rate_at[window]:.1f} Hz total coincidences")
    best_window = min(w for w in rate_at if rate_at[w] >= 0.9 * rate_at[3.0])
    print(f"Recommended COINCIDENCE_WINDOW = {best_window:.0f} ns "
          f"(session still uses {COINCIDENCE_WINDOW} ns; edit settings.py to change)")
    if input("Save tuned delays as new defaults? [y/N] ").strip().lower() == 'y':
        st.save_calibration()
    else:
        print("Not saved — tuned delays apply for this session only.")


# rework to be a delay optimizer if given an initial delay should just move up and down by +/- 30ns and check, also check coincidence windows between 5-1ns and chose smallest window with max counts
def find_delay_window(
    herald_ch: int = TRIGG_CH,
    signal_ch: int = DET_CHS[0],
    min_delay: float = 0.0,
    max_delay: float = 200.0,
    init_window: float = 30.0,
    target_window: float = 1.0,
    coincidence_window: float = COINCIDENCE_WINDOW,
    integration_time: float = 0.5,
    noise_threshold_sigma: float = 2.0,
    verbose: bool = True,
) -> dict:
    """
    Iteratively narrows the delay between two channels to find the value that
    maximises coincidence counts.

    Starting from a coarse scan over [min_delay, max_delay] at init_window-spaced
    intervals, the algorithm picks the best-performing bin, re-centres on it, halves
    the search window, and repeats until the window reaches target_window.

    A noise threshold check is applied at each iteration: the best bin must exceed
    (mean + noise_threshold_sigma * std) of all bins in that sweep. If it does not,
    the search terminates early and reports no clear peak.

    Args:
        herald_ch:            Herald/trigger channel number.
        signal_ch:            Signal detector channel number.
        min_delay:            Lower bound of the initial delay search range (ns).
        max_delay:            Upper bound of the initial delay search range (ns).
        init_window:          Initial step size / bin width for the first coarse scan (ns).
        target_window:        Stop condition — search ends when window <= this value (ns).
        coincidence_window:   TDC coincidence window passed to Logic16 (ns).
        integration_time:     Counting integration time per delay point (s).
        noise_threshold_sigma: A bin must exceed mean + N*std of all bins in its sweep
                              to be considered a real peak. Set to 0 to disable.
        verbose:              Print progress at each iteration.

    Returns:
        dict with keys:
            'found'         – bool, whether a clear peak was found.
            'optimal_delay' – float, best delay in ns (None if not found).
            'peak_rate'     – float, coincidence rate at optimal delay (Hz).
            'iterations'    – list of dicts, one per sweep with fields:
                                'window', 'delays_scanned', 'counts', 'best_delay'.
    """
    singles_chs = [herald_ch, signal_ch]
    coincidence_chs = [[herald_ch, signal_ch]]

    current_min = min_delay
    current_max = max_delay
    window = init_window
    iterations = []

    if verbose:
        print(f"[delay_search] Herald ch {herald_ch} <-> Signal ch {signal_ch}")
        print(f"[delay_search] Search range: [{min_delay}, {max_delay}] ns")
        print(f"[delay_search] Window: {init_window} ns → {target_window} ns\n")

    with Logic16(
        coincidence_window=coincidence_window,
        logic_mode=True,
        integration_window=integration_time,
    ) as logic:
        logic.configure(threshold=THRESHOLDS, coincidence_window=coincidence_window)

        while window > target_window:
            # Build scan points centred on bins of width `window` across current range.
            # Use window/2 offset so bin centres sit in the middle of each step.
            delay_points = np.arange(current_min, current_max + window, window)
            counts_per_point = []

            if verbose:
                print(
                    f"[sweep] window={window:.2f} ns  "
                    f"range=[{current_min:.2f}, {current_max:.2f}] ns  "
                    f"points={len(delay_points)}"
                )

            for delay_ns in delay_points:
                base_delays = list(DELAYS)
                base_delays[signal_ch - 1] = float(delay_ns)
                logic.set_delays(base_delays)

                c_counts, _s_counts, total_time = logic.read_counts_integrated(
                    pos_coincidence=coincidence_chs,
                    pos_singles=singles_chs,
                )
                coinc_rate = c_counts[0] / total_time if total_time > 0 else 0.0
                counts_per_point.append(coinc_rate)

                if verbose:
                    print(f"  delay={delay_ns:.2f} ns → {coinc_rate:.2f} Hz")

            counts_arr = np.array(counts_per_point)
            best_idx = int(np.argmax(counts_arr))
            best_delay = delay_points[best_idx]
            best_rate = counts_arr[best_idx]

            # Noise threshold check.
            threshold = counts_arr.mean() + noise_threshold_sigma * counts_arr.std()

            iterations.append({
                "window": window,
                "delays_scanned": delay_points.tolist(),
                "counts": counts_arr.tolist(),
                "best_delay": best_delay,
                "best_rate": best_rate,
                "threshold": threshold,
            })

            if best_rate < threshold:
                if verbose:
                    print(
                        f"\n[delay_search] No clear peak found at window={window:.2f} ns "
                        f"(best={best_rate:.2f} Hz, threshold={threshold:.2f} Hz). "
                        "Stopping early.\n"
                    )
                return {
                    "found": False,
                    "optimal_delay": None,
                    "peak_rate": None,
                    "iterations": iterations,
                }

            if verbose:
                print(
                    f"  → Best: delay={best_delay:.2f} ns  "
                    f"rate={best_rate:.2f} Hz  "
                    f"threshold={threshold:.2f} Hz  ✓\n"
                )

            # Re-centre search window on the best bin and halve the step size.
            window /= 2.0
            current_min = max(min_delay, best_delay - window)
            current_max = min(max_delay, best_delay + window)

    if verbose:
        print(
            f"[delay_search] Converged → optimal delay = {best_delay:.2f} ns  "
            f"({best_rate:.2f} Hz)"
        )

    return {
        "found": True,
        "optimal_delay": best_delay,
        "peak_rate": best_rate,
        "iterations": iterations,
    }


if __name__ == "__main__":
    stream_herald_and_signal(duration=20.0)
    # scan_coincidences_over_delays()

    # result = find_optimal_delay(
    #     herald_ch=TRIGG_CH,
    #     signal_ch=DET_CHS[0],
    #     min_delay=0.0,
    #     max_delay=200.0,
    #     init_window=30.0,
    #     target_window=1.0,
    #     integration_time=0.5,
    #     noise_threshold_sigma=2000.0,
    #     verbose=True,
    # )

    # if result["found"]:
    #     print(f"\nOptimal delay: {result['optimal_delay']:.2f} ns")
    #     print(f"Peak coincidence rate: {result['peak_rate']:.2f} Hz")
    # else:
    #     print("\nNo clear coincidence peak detected")