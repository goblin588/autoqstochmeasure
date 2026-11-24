import numpy as np
from libraries.stochprocq.hmm import HiddenMarkovModel
from libraries.stochprocq._utility import count_approx

class RenewalProcess(HiddenMarkovModel):
    """
    Renewal process class.
    """

    def __init__(self, probs: list, cutoff: float = 1e-9):
        """
        Get a renewal process with given probabilities.
        """
        super().__init__(self.get_transitions(probs), cutoff=cutoff)
        self.probs = probs

    @staticmethod
    def get_transitions(probs:list) -> np.ndarray:
        """
        Generate a renewal process with given probabilities.
        """
        n = len(probs)+1

        trans = np.zeros((2,n,n))

        for i in range(n-1):
            trans[0, i+1,i] = probs[i]
            trans[1, 0, i] = 1-probs[i]
        trans[1, 0, n-1] = 1

        return trans

def get_uniform_renewal(n: int) -> RenewalProcess:
    """
    Generate a uniform renewal process.
    """
    p = [1-1/(k+2) for k in range(n)][::-1]
    return RenewalProcess(p)

# Bio-renewal process

def get_bio_renewal(n: int, l: float = 1,
                tau: float = .1, nv: float = 0.5,
                scale: float = 0.2) -> RenewalProcess:
    """
    Generate the transition matrix for the bio-renewal process.

    Parameters:
    -------------------
    l: float
        The firing rate.
    tau: float
        The refractory period.
    nv: float
        The noise level.

    Return:
    ----------------
    """
    fn = []

    def u_ifn(t: float) -> float:
        ''' (unleaky) integrate-and-fire neuron
        '''
        if t <= tau:
            return 0
        const = np.sqrt(l / (2* np.pi * np.power(t-tau,3)))
        phi = const * np.exp(-l * np.power(nv*(t-tau) - 1, 2) / 2 / (t-tau))
        return phi

    for i in range(n+2):
        fn.append(count_approx(u_ifn, scale, i))

    # renormalize
    fn = np.array(fn) / np.sum(fn)

    w = [1-fn[0]]
    prob = [w[0]]

    # Obtain the activation probability recursively
    for i in range(1, n+1):
        w.append(w[i-1] - fn[i])
        prob.append(w[i]/w[i-1])

    return RenewalProcess(prob[:-1])
