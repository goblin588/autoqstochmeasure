"""
This module contains functions to compute various measures between probability distributions.
"""

import numpy as np
from scipy.special import rel_entr
from scipy.stats import entropy

def kl_div(p:np.ndarray, q:np.ndarray, steps:int = None) -> float:
    """
    Compute the Kullback-Leibler divergence rate between two probability distributions.

    Inputs are normalised to sum to 1, so unnormalised counts are accepted.
    Zero bins in p contribute 0 (rel_entr handles 0*log0).

    Parameters:
    -------------------
    p: np.ndarray
        The first probability distribution (or unnormalised counts).
    q: np.ndarray
        The second probability distribution (or unnormalised counts).
    steps: int, optional
        Number of process steps to average over.
        Defaults to log2(len(p)), the binary-word convention of check_len.

    Return:
    ----------------
    kl: float
        The KL divergence rate in bits per step.
    """
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    if steps is None:
        steps = check_len(p, q)
    return np.sum(rel_entr(p / p.sum(), q / q.sum())) / np.log(2) / steps

def check_len(p:np.array, q:np.array):
    if len(p) != len(q):
        raise ValueError(
            f"""The shape of the two distributions are not consistent:
            {len(p)} and {len(q)}.""")
    return int(np.log2(len(p)))

def eval_diverge(
        p_dist:np.array,
        q_dist:np.array,
        his_steps:int = None
        ) -> float:
    """
    Evaluate the KL-divergnece function with respect to the **stationary distribution**

    Parameters
    ----------
    p_dist : np.array
        The true distribution.

    q_dist : np.array
        The predicted distribution.
    his_steps : int, optional
        Number of history steps for conditional divergence.
        If None, the full divergence is computed.
        The default is None.

    Returns
    -------
    divergence: float
        The KL-divergence value.
    """
    n = check_len(p_dist,q_dist)

    if his_steps is not None:
        p_dist_cond = p_dist.reshape((2**his_steps,-1)).copy()
        q_dist_cond = q_dist.reshape((2**his_steps,-1)).copy()

        diverge = 0
        for p,q in zip(p_dist_cond,q_dist_cond):
            if (p_his := np.sum(p)) > 1e-10:
                # Laplace smoothing on q: a weak experimental channel can
                # land at exactly 0 for an outcome theory still considers
                # reachable, and entropy()'s per-element p*log(p/q) term
                # is +inf wherever q==0 and p>0 -- not just when the whole
                # bucket (q.sum()) is zero, so a bucket-level guard alone
                # isn't enough. Adding a tiny constant before renormalizing
                # keeps q strictly positive everywhere, so this never
                # blows up; it costs a negligible, bounded bias in
                # exchange for a number that's always usable.
                q_smooth = q + 1e-9
                diverge += p_his * entropy(p/p_his, q_smooth/np.sum(q_smooth), base=2)
        return diverge/(n-his_steps)
    return entropy(p_dist, q_dist, base=2)

def eval_log_fid(
        p_dist:np.array,
        q_dist:np.array,
        his_steps:int = None
        ) -> float:
    """
    Evaluate the fidelity function with respect to the **stationary distribution**

    Parameters
    ----------
    p_dist : np.array
        The true distribution.

    q_dist : np.array
        The predicted distribution.
    his_steps : int, optional
        Number of history steps for conditional divergence.
        If None, the full divergence is computed.
        The default is None.

    Returns
    -------
    fidelity: float
        The fidelity value.
    """
    n = check_len(p_dist,q_dist)

    if his_steps is not None:
        p_dist_cond = p_dist.reshape((2**his_steps,-1)).copy()
        q_dist_cond = q_dist.reshape((2**his_steps,-1)).copy()

        fid = 0
        for p,q in zip(p_dist_cond,q_dist_cond):
            if p_his := np.sum(p) > 1e-10:
                a = np.sum((p/p_his)**2)
                b = np.sum((q/np.sum(q))**2)
                c = np.sum((p/p_his)*(q/np.sum(q)))
                fid += p_his * np.log2(c / np.sqrt(a*b))
        return fid/(n-his_steps)

    a = np.sum(p_dist**2)
    b = np.sum(q_dist**2)
    c = np.sum(p_dist*q_dist)
    return np.log2(c / np.sqrt(a*b))

def eval_nll(
        p_dist:np.array,
        q_dist:np.array,
        his_steps:int = None
        ) -> float:
    """
    Evaluate the negative log-likelihood function with respect to the **stationary distribution**

    Parameters
    ----------
    p_dist : np.array
        The true distribution.

    q_dist : np.array
        The predicted distribution.
    his_steps : int, optional
        Number of history steps for conditional divergence.
        If None, the full divergence is computed.
        The default is None.

    Returns
    -------
    nll: float
        The negative log-likelihood value.
    """
    n = check_len(p_dist,q_dist)

    if his_steps is not None:
        p_dist_cond = p_dist.reshape((2**his_steps,-1)).copy()
        q_dist_cond = q_dist.reshape((2**his_steps,-1)).copy()

        nll = 0
        for p,q in zip(p_dist_cond,q_dist_cond):
            if p_his := np.sum(p) > 1e-10:
                cond_p = p/p_his
                cond_q = q/np.sum(q)
                for pi,qi in zip(cond_p,cond_q):
                    nll += - p_his * pi * np.log2(qi)
        return nll/(n-his_steps)

    nll = 0
    for pi,qi in zip(p_dist,q_dist):
        nll += - pi * np.log2(qi)
    return nll

