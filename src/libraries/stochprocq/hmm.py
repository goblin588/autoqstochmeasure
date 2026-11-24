"""
Provide different models to simulate the hidden Markov models.
"""

import numpy as np
import scipy.linalg as LA

from scipy.stats import entropy

from libraries.stochprocq._utility import generate_partitions
from libraries.stochprocq.meta import StochModel, IOProcess

class HiddenMarkovModel(StochModel):
    """
    Store the transition matrices for the hidden Markov model.

    Parameters:
    -------------------
    transitions: list of np.ndarray
        The transition matrices for the hidden Markov model.
    """
    def __init__(self, transitions:np.ndarray, cutoff:float = None):
        super().__init__(transitions, cutoff)
        self._steady_state = None

    @classmethod
    def _check_valid(cls, tensor: np.ndarray):
        super()._check_valid(tensor)
        if np.any(tensor < -cls._DEFAULT_CUTOFF):
            raise ValueError("The transition matrices must be non-negative.")
        if not np.allclose(tensor.sum(axis=(-3,-2)), 1):
            raise ValueError("The transition matrices must be stochastic.")

    # this is only an alias
    @property
    def transitions(self) -> np.ndarray:
        """
        The transition matrices for the hidden Markov model.

        **Example**:
        ```
        [[[0.  0.  1. ]
          [0.2 0.  0. ]
          [0.  0.3 0. ]]
         [[0.8 0.7 0. ]
          [0.  0.  0. ]
          [0.  0.  0. ]]]
        ```
        """
        return self.tensor

    @property
    def steady_state(self) -> np.ndarray:
        if self._steady_state is None:
            self._steady_state = self._compute_steady_state()
        return self._steady_state

    def evolve(self,
               state: np.ndarray,
               output: int = None,
               ctrl: int = None,
               ) -> np.ndarray:

        tensor = self.tensor
        if output is not None:
            return tensor[output] @ state
        return tensor @ state

    def sum_probs(self, state: np.ndarray) -> float:
        return state.sum(axis=-1)

    def _compute_steady_state(self) -> np.ndarray:
        '''
        Compute the steady state of the hidden Markov model by solving the
        linear equation.
        '''
        t = np.sum(self.transitions,axis=0)

        a = t - np.identity(self.dim)
        a[-1] = np.ones(self.dim) # The last row is the normalization condition.

        b = np.zeros(self.dim)
        b[-1] = 1.0
        return LA.solve(a,b)

    def classical_state(self, lable:int):
        """
        Convert a label into a classical state.

        Parameters:
        --------------------
        lable: int
            The label of the classical state.
        
        Returns:
        --------------------
        state: np.ndarray
            The classical state.
        """
        state = np.zeros(self.dim)
        state[lable] = 1
        return state

    def entropy(self,base:int=2) -> float:
        '''
        Compute the entropy of the hidden Markov model.
        '''
        state = self.steady_state
        return entropy(state,base=base)

    def gen_dists(self, length:int, sparse:bool=True):
        """
        Generate the possible future sequences of the given length for each initial state.
        
        Parameters:
        ----------------
        length: the length of the future sequences.
        
        Return:
        ----------------
        A list of the probability of the future sequences.
        """

        dist = np.zeros((self.dim, self.output_alphabet_size**length))

        for i in np.arange(self.dim):
            dist[i] = self.prob_dist(length, self.classical_state(i), sparse=sparse)

        return dist

    def classical_bd(self, length:int, target_dim:int=2, base:float=2.,
                         sparse:bool=True):
        """
        Given a model, compute the optimal divergence for non-unifilar models
        and the optimal morph for merging the states.
        For each length, it is a lower bound of the optimal divergence for
        unifilar models.
        
        Parameters:
        --------------------
        model: the model to be compared.
        length: the length of the generated distribution.
        target_dim: the number of clusters in the target distribution.
        base: the base of the entropy.
        
        Return:
        --------------------
        opt_div: the optimal divergence.
        opt_morph: the optimal morph.
        """
        stat_dist = self.steady_state
        dists = self.gen_dists(length, sparse=sparse)
        full_entr = entropy(dists, base=base, axis=1)

        morphs = generate_partitions(target_dim, set(range(self.dim)))

        opt_div = np.inf

        def cond_mi(st):
            'Conditional mutual information'
            p = stat_dist[st] @ dists[st]
            m = np.sum(p)

            if m < self.cutoff:
                return 0
            base_entr = entropy(p/m, base=base)
            rel = stat_dist[st] @ full_entr[st]

            return m*base_entr - rel

        for morph in morphs:
            kl_div = sum(map(cond_mi, map(list, morph)))

            if kl_div < opt_div:
                opt_div = kl_div
        return opt_div/length

class MPS(StochModel):
    """
    Store the MPS states
    
    Parameters:
    -------------------
    mps: np.ndarray
    """
    def __init__(self, mps:np.ndarray, cutoff:float=1e-9, lcf:bool=False):

        super().__init__(mps, cutoff)

        self._leading_tuple = None
        self._is_lcf = lcf

    @classmethod
    def _check_valid(cls, tensor:np.ndarray):
        super()._check_valid(tensor)

    @property
    def full(self):
        """
        Expand the iMPS for computations.
        """
        pair = np.einsum('ijk, ilm -> jl km', self.tensor, self.tensor.conj())
        return pair.reshape((self.dim**2,)*2)

    @property
    def steady_state(self) -> np.ndarray:
        """
        The steady state of the iMPS.
        """
        if self.is_lcf:
            return self.vr
        raise NotImplementedError("The iMPS is not in the left canonical form.")

    def evolve(self,
               state: np.ndarray,
               output: int = None,
               ctrl: int = None,
               ) -> np.ndarray:
        tensor = self.tensor
        if output is not None:
            return tensor[output] @ state @ tensor[output].conj().swapaxes(-1,-2)
        return tensor @ state @ tensor.conj().swapaxes(-1,-2)

    def sum_probs(self, state: np.ndarray) -> float:
        return np.real(np.trace(state,axis1=-2,axis2=-1))

    @property
    def ld_eigval(self):
        """
        The leading eigenvalue of the InfiniteMatrixProductState.
        """
        if self._leading_tuple is None:
            self._eval_leading_eig()
        return self._leading_tuple[0]

    @property
    def vl(self):
        """
        The left eigenvector of the leading eigenvalue.
        It is normalized such that the trace of the left eigenvector is 1.
        """
        if self._leading_tuple is None:
            self._eval_leading_eig()
        return self._leading_tuple[1]

    @property
    def vr(self):
        """
        The right eigenvector of the leading eigenvalue.
        It is normalized such that the trace of the right eigenvector is 1.
        """
        if self._leading_tuple is None:
            self._eval_leading_eig()
        return self._leading_tuple[2]

    @property
    def is_lcf(self):
        '''
        Return whether the iMPS is in the left canonical form.
        '''
        return self._is_lcf

    def _eval_leading_eig(self):
        '''
        Evaluate the *leading eigenvalue*, leading left eigenvector and
        leading right eigenvector
        '''
        lamb, vl, vr = LA.eig(self.full, left=True)
        lamb = np.real(lamb)
        i = np.argmax(lamb)

        vl = np.reshape(vl[:,i],(self.dim,self.dim))
        vr = np.reshape(vr[:,i],(self.dim,self.dim))

        # set the leading eigenvalue and eigenvectors
        self._leading_tuple = (
            lamb[i],
            vl/np.trace(vl),
            vr/np.trace(vr),
        )

    def left_canonical_form(self, cutoff:float=None, update:bool=True):
        '''
        Convert the iMPS to the left canonical form
        '''
        lam_l, s = LA.eigh(self.vl) # V is guaranteed to be Hermitian

        # truncate the small dimensions
        cutoff = self.cutoff if cutoff is None else cutoff
        mask = lam_l > cutoff

        u = s[:,mask] * np.sqrt(lam_l[mask])
        u_inv = s[:,mask] / np.sqrt(lam_l[mask])


        lcf_tensor = u.conj().T @ self.tensor @ u_inv
        lcf_tensor /= np.sqrt(self.ld_eigval) # normalize

        if update:
            self.__init__(lcf_tensor, lcf=True)
            return self

        return self.__class__(lcf_tensor, lcf=True)

    def right_canonical_form(self, cutoff:float=None):
        '''
        Convert the iMPS to the right canonical form
        '''
        lam, w = LA.eigh(self.vr) # V is guaranteed to be Hermitian

        # truncate the small dimensions
        cutoff = cutoff or self.cutoff
        mask = lam > cutoff

        u = w[:,mask] * np.sqrt(lam[mask])
        u_inv = w[:,mask] / np.sqrt(lam[mask])

        rcf_tensor = u_inv.conj().T @ self.tensor @ u
        rcf_tensor /= np.sqrt(self.ld_eigval)

        return self.__class__(rcf_tensor)

    def to_kraus(self):
        '''
        Convert the iMPS to the Kraus representation.
        '''
        if not self.is_lcf:
            raise NotImplementedError("The iMPS is not in the left canonical form.")

        kop = self.tensor
        states = LA.sqrtm(self.vl)

        return kop, states

    def to_unitary(self):
        '''
        Convert the iMPS to the unitary representation.
        '''
        if not self.is_lcf:
            raise NotImplementedError("The iMPS is not in the left canonical form.")

        udim = self.output_alphabet_size*self.dim
        distilled = np.zeros((udim,udim),dtype=complex)

        mat = self.tensor.reshape(udim, self.dim)

        for j in range(self.dim):
            col_index = j*self.dim
            distilled[:, col_index] = mat[:, j]

        w, _, vh = LA.svd(distilled, full_matrices=False)
        return w @ vh

    @classmethod
    def from_hmm(cls, hmm, cutoff=None):
        '''
        Convert the hidden Markov model to the Matrix Product State.
        '''
        tensor = np.sqrt(hmm.transitions)
        return cls(tensor).left_canonical_form(cutoff=cutoff)

class IOHiddenMarkovModel(IOProcess):
    """
    Store the IO Hidden Markov Models.

    Parameters:
    -------------------
    transitions: list of np.ndarray
        The transition matrices for the hidden Markov model.
    """

    _NUM_AXES = 4

    @classmethod
    def _check_valid(cls, tensor: np.ndarray):
        super()._check_valid(tensor)
        if np.any(tensor < -cls._DEFAULT_CUTOFF):
            raise ValueError("The transition matrices must be non-negative.")
        if not np.allclose(tensor.sum(axis=(-3,-2)), 1):
            raise ValueError("The transition matrices must be stochastic.")

    def evolve(self,
               state: np.ndarray,
               output: int = None,
               ctrl: int = None,
               ) -> np.ndarray:

        tensor = self.tensor
        if ctrl is not None:
            tensor = tensor[ctrl]
        if output is not None:
            if ctrl is not None:
                return tensor[output] @ state
            return tensor[:,output] @ state
        return tensor @ state

    def sum_probs(self, state: np.ndarray) -> float:
        return state.sum(axis=-1)

class IOMPS(IOProcess):
    """
    Store the IO Hidden Markov Models.

    Parameters:
    -------------------
    transitions: list of np.ndarray
        The transition matrices for the hidden Markov model.
    """

    @classmethod
    def _check_valid(cls, tensor: np.ndarray):
        super()._check_valid(tensor)
        if np.any(tensor < -cls._DEFAULT_CUTOFF):
            raise ValueError("The transition matrices must be non-negative.")
        if not np.allclose(tensor.sum(axis=(-3,-2)), 1):
            raise ValueError("The transition matrices must be stochastic.")

    def evolve(self,
               state: np.ndarray,
               output: int = None,
               ctrl: int = None,
               ) -> np.ndarray:

        tensor = self.tensor
        if ctrl is not None:
            tensor = tensor[ctrl]
        if output is not None:
            if ctrl is not None:
                return tensor[output] @ state
            return tensor[:,output] @ state
        return tensor @ state

    def sum_probs(self, state: np.ndarray) -> float:
        return state.sum(axis=-1)

    # @classmethod
    # def from_iohmm(cls, hmm, cutoff=None):
    #     '''
    #     Convert the hidden Markov model to the Matrix Product State.
    #     '''
    #     tensor = np.sqrt(hmm.tensor)

    # @property
    # def full(self, tensor):
    #     """
    #     Expand the iMPS for computations.
    #     """
    #     pair = np.einsum('ijkl, mnop -> ikmo jlnp', tensor, tensor.conj())

    #     causal = pair + np.einsum('ijij klkl', pair)

    #     return pair.reshape((self.dim**2,)*2)
