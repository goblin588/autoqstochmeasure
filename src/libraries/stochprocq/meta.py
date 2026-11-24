"""
IO process base class.
"""

from abc import ABC, abstractmethod
from typing import List, Union

import numpy as np

class IOProcess(ABC):
    """
    The base class for input-output processes.
    """

    _DEFAULT_CUTOFF = 1e-9
    _NUM_AXES = 5

    def __init__(self,tensor:np.ndarray, cutoff:float=None):

        # Check if the input is valid.
        self._check_valid(tensor)

        self._tensors = tensor
        self.cutoff = cutoff if cutoff is not None else self._DEFAULT_CUTOFF

    @classmethod
    def _check_valid(cls, tensor: np.ndarray):
        '''
        Check if the input tensor is valid.
        This will be checked at ``__init__``.

        For IO processes, the input tensor should have 4 axes:
        1. The input alphabet.
        2. The output alphabet.
        3. and 4. The transition rule on the memroy states.

        Parameters:
        -------------------
        tensor: np.ndarray
            The transition matrices for the input-output process.
        '''
        if len(tensor.shape) != cls._NUM_AXES:
            raise ValueError(f'The input-output tensor should have {cls._NUM_AXES} axes.')
        if tensor.shape[-1] != tensor.shape[-2]:
            raise ValueError('The input matrices should be square.')

    @property
    def tensor(self) -> np.ndarray:
        """
        The tensors representing the stocahstic process.
        """
        return self._tensors

    @property
    def shape(self) -> tuple:
        """
        The shape of the transition matrices.
        """
        return self._tensors.shape

    @property
    def input_alphabet_size(self) -> int:
        """
        The size of the input alphabet.
        """
        if self._NUM_AXES < 4:
            raise NotImplementedError('The process does not contain an input alphabet.')
        return self.shape[0]

    @property
    def output_alphabet_size(self) -> int:
        """
        The size of the output alphabet.
        """
        return self.shape[-3]

    @property
    def dim(self) -> int:
        """
        The dimension of the transition matrices.
        """
        return self.shape[-1]

    @abstractmethod
    def evolve(self, state:np.ndarray,
               output:int = None,
               ctrl:int = None,
               ) -> np.ndarray:
        """
        Evolve the state with the given transition matrix.

        Parameters:
        -------------------
        state: np.ndarray
            The current state of the system.
        ctrl: int
            The ctrl signal to the system.
        output: int
            The output to the system.

        Return:
        ----------------
        state: np.ndarray
            The new state of the system.
        """

    @abstractmethod
    def sum_probs(self, state:np.ndarray) -> float:
        """
        Compute the sum of the probabilities.
        """

class StochModel(IOProcess):
    """
    The base class for stochastic models.
    """

    _NUM_AXES = 3

    @property
    @abstractmethod
    def steady_state(self) -> np.ndarray:
        """
        The steady state of the stochastic process.
        """

    @abstractmethod
    def evolve(self, state:np.ndarray,
               output:int = None,
               ctrl:int = None,
               ) -> np.ndarray:
        """
        Evolve the state with the given transition matrix.

        Parameters:
        -------------------
        state: np.ndarray
            The current state of the system.
        output: int
            The output to the system.
        ctrl: int
            Not used for stochatictic process.

        Return:
        ----------------
        state: np.ndarray
            The new state of the system.
        """

    def encode_state(self,
                     seq:Union[str,List[int]] = None,
                     init_state:np.ndarray=None) -> np.ndarray:
        '''
        Encode the past into a memory state.

        Given an initial state `state`, produce the state after
        the sequence `seq` is output.

        If the `state` is `None`, the steady state is used.
        '''
        if init_state is None:
            state = self.steady_state
        else:
            state = np.array(init_state)

        if seq is not None:
            for x in seq:
                state = self.evolve(state, int(x))
        sum_p = self.sum_probs(state)
        if sum_p < self.cutoff:
            raise ValueError(f"The probability of obtaining sequence {seq} is varnishing.")
        state /= sum_p
        return state

    def is_possible(self, seq, state=None) -> bool:
        '''
        Check if the given sequence is possible.
        '''
        try:
            self.encode_state(seq,state)
            return True
        except ValueError:
            return False

    def prob_seq(self, seq, state:int=None, past:Union[List[int],str] = None) -> float:
        '''
        Compute the probability of the given sequence.
        '''
        mem_st = self.encode_state(past, init_state = state)

        for x in seq:
            mem_st = self.evolve(mem_st, int(x))

        p = self.sum_probs(mem_st)
        if abs(p) < self.cutoff:
            return 0
        return p

    def prob_dist(self, length:int,
                  init_state:int=None, past:Union[List[int],str] = None,
                  sparse:bool=True,
                  ) -> np.ndarray:
        '''
        Compute the future probability distribution given current state.
        '''
        mem_st = self.encode_state(past, init_state = init_state)
        dist = np.zeros(self.output_alphabet_size**length)

        ptr = [0]  # Use a list to allow modification within the nested function
        
        if sparse:
            def recursive_prob(mem_st, length):
                prob = self.sum_probs(mem_st)
                if prob < self.cutoff:                 # prone the tree
                    ptr[0] += self.output_alphabet_size**length
                    return
                if length == 0:
                    dist[ptr[0]] = prob
                    ptr[0] += 1
                    return
                for i in range(self.output_alphabet_size):
                    recursive_prob(self.evolve(mem_st, i),
                                   length - 1)
        else:
            def recursive_prob(mem_st, length):
                if length == 0:
                    dist[ptr[0]] = self.sum_probs(mem_st)
                    ptr[0] += 1
                    return
                for i in range(self.output_alphabet_size):
                    recursive_prob(self.evolve(mem_st, i),
                                   length - 1)

        recursive_prob(mem_st, length)

        return dist

    def gen_str(self, length, state:int=None, past:Union[List[int],str]=None):
        """
        Generate a string of given length according to the hidden Markov model.
        """
        mem_st = self.encode_state(state, past)
        generator = np.random.Generator(np.random.PCG64())

        for _ in range(length):
            next_st = self.evolve(mem_st)
            prob = self.sum_probs(next_st)
            output = generator.choice(self.output_alphabet_size,p=prob)
            mem_st = next_st[output]/prob[output] # normalize the state
            yield output
