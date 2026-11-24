"""
KL divergence (vs. the uniform-renewal theory model) from raw measurement
counts -- live-measurement counterpart to stochprocsim's offline
utils.kl_rate_from_output_distribution/demos/marimo/plot_experimental_data.py.

ponytail: generate_quantum_model/efficiency_for_channel/loop_pass_k below
are a deliberate copy of stochprocsim/src/stochprocsim/utils.py's functions
of the same name (pure numpy, no Path/pandas dependency to drag in here).
Upgrade path: extract a shared no-heavy-deps package if the two drift.
"""
import numpy as np

from libraries.stochprocq import get_uniform_renewal
from libraries.stochprocq.measure import eval_diverge
from libraries.stochprocq.models.renewal import RenewalProcess

DETECTOR_EFFICIENCY = {
    'herald': 0.6,
    'dump': 0.68,
    # loop = 1 (reference) -- see stochprocsim.utils.DETECTOR_EFFICIENCY,
    # keep these two in sync.
    'loop': 1.0,
}

_SURVIVAL_CUTOFF = 1e-9


def efficiency_for_channel(channel: int, herald_ch: int = 3, dump_ch: int = 7) -> float:
    if channel == herald_ch:
        return DETECTOR_EFFICIENCY['herald']
    if channel == dump_ch:
        return DETECTOR_EFFICIENCY['dump']
    return DETECTOR_EFFICIENCY['loop']


def loop_pass_k(ch: int, loop_chs: list, dump_ch: int = 7) -> int:
    """1-indexed physical loop pass: ch's position among loop_chs (ascending),
    not channel arithmetic -- see stochprocsim.utils.loop_pass_k."""
    return [c for c in loop_chs if c != dump_ch].index(ch) + 1


def generate_quantum_model(output_distribution) -> RenewalProcess:
    q_emit = np.clip(np.asarray(output_distribution, dtype=float), 0, None)
    q_survive_st = np.zeros_like(q_emit)
    q_survive_st[0] = np.clip(q_emit[0], _SURVIVAL_CUTOFF, 1 - _SURVIVAL_CUTOFF)
    for i in range(1, len(q_emit)):
        q_survive_st[i] = np.clip(q_emit[i] / np.prod(1 - q_survive_st[:i]),
                                   _SURVIVAL_CUTOFF, 1 - _SURVIVAL_CUTOFF)
    return RenewalProcess([1 - q for q in q_survive_st[:-1]])


def kl_rate_from_output_distribution(N: int, output_distribution) -> float:
    theory = get_uniform_renewal(N - 1)
    model = generate_quantum_model(output_distribution)
    p_dist = theory.steady_state @ theory.gen_dists(N + 1)
    q_dist = model.steady_state @ model.gen_dists(N + 1)
    return eval_diverge(p_dist, q_dist, his_steps=N - 1)


def kl_rate_from_counts(N: int, counts: dict, int_time: float, bg_row: dict,
                         loss_cal: dict, det_chs: list, dump_ch: int = 7):
    """KL rate (bits/step) for state-0 data collected so far in a measurement.

    counts: {ch: cumulative coincidence count} for every channel in det_chs.
    int_time: total integration seconds those counts were collected over.
    bg_row: a _acquire_background(N)-shaped dict (coinc_ch{ch} + int_time).
    loss_cal: a _find_latest_loss_calibration()-shaped dict (top-level
        "coincidence_rates_hz": {loop0_hz, loop1_hz, ...}).

    Returns None if there's no usable loss calibration yet (loop0_hz == 0,
    e.g. right at startup before calibrate_loss has run) -- same "can't
    loss-correct" case stochprocsim's loss_rates_for callers already handle.
    """
    rates_hz = (loss_cal or {}).get('coincidence_rates_hz', {})
    c2, c4 = rates_hz.get('loop0_hz', 0.0), rates_hz.get('loop1_hz', 0.0)
    if not c2:
        return None
    T = c4 / c2

    bg_int_time = bg_row.get('int_time', 1.0) or 1.0
    k = np.array([N if ch == dump_ch else loop_pass_k(ch, det_chs, dump_ch) for ch in det_chs])
    rate = np.array([counts.get(ch, 0) / int_time for ch in det_chs])
    bg = np.array([bg_row.get(f'coinc_ch{ch}', 0) / bg_int_time for ch in det_chs])
    eff = np.array([efficiency_for_channel(ch, dump_ch=dump_ch) for ch in det_chs])

    corr = np.clip((rate - bg) / eff / (T ** k), 0, None)
    total = corr.sum()
    if total <= 0:
        return None
    frac = (corr / total)[:N]
    return kl_rate_from_output_distribution(N, frac)


def _demo():
    # no loss calibration yet (loop0_hz=0, e.g. fresh start) -> None, not a crash
    assert kl_rate_from_counts(4, {4: 100, 6: 50, 8: 20, 7: 10}, 10.0,
                                {'int_time': 1.0}, {}, [4, 6, 8, 7]) is None

    # a output distribution matching theory exactly -> KL ~ 0
    det_chs = [4, 6, 8, 7]
    N = 4
    theory = get_uniform_renewal(N - 1)
    exit_p = np.zeros(len(theory.probs) + 1)
    survived = 1.0
    for j in range(len(theory.probs)):
        exit_p[j] = (1 - theory.probs[j]) * survived
        survived *= theory.probs[j]
    exit_p[-1] = survived

    eff = np.array([efficiency_for_channel(ch, dump_ch=7) for ch in det_chs])
    loss_cal = {'coincidence_rates_hz': {'loop0_hz': 100.0, 'loop1_hz': 100.0}}  # T=1
    counts = {ch: exit_p[i] * eff[i] * 1000 for i, ch in enumerate(det_chs)}
    kl = kl_rate_from_counts(N, counts, 1.0, {'int_time': 1.0}, loss_cal, det_chs)
    assert kl < 1e-6, kl

    # a visibly skewed distribution -> clearly positive KL
    skewed_counts = {4: 700.0, 6: 100.0, 8: 100.0, 7: 100.0}
    kl2 = kl_rate_from_counts(N, skewed_counts, 1.0, {'int_time': 1.0}, loss_cal, det_chs)
    assert kl2 > 0.05, kl2
    print("kl_rate_from_counts: ok")


if __name__ == "__main__":
    _demo()
