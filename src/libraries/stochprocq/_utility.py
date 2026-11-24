"""
This module contains utility functions and classes for the StochProcQ package.
"""

from itertools import combinations, chain
from functools import partial
import json

import numpy as np

def int2seq(i:int, steps:int) -> str:
    """
    Convert an integer into a binary sequence with given length.

    Parameters:
    --------------------
    i: the integer to be converted.
    steps: the length of the sequence.

    Return:
    --------------------
    seq: the binary sequence.
    """
    return f'{i:0{steps}b}'

def seq2int(seq:str,base=2) -> int:
    """
    Convert a binary sequence into an integer.

    Parameters:
    --------------------
    seq: the binary sequence.
    base: the base of the integer.

    Return:
    --------------------
    i: the integer to be converted.
    """
    return int(seq,base=base)

# %% classes
class NumpyEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for numpy arrays and boolean values.
    """
    def default(self, o):
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
        return json.JSONEncoder.default(self, o)

def iteration_tracker(func):
    """
    Decorator to track the number of iterations.
    """
    iteration_tracker.counter = 0

    def inner(x:np.array,logging=True):
        if logging is True:
            iteration_tracker.counter += 1
            if iteration_tracker.counter % 100 == 0:
                print('.',end='',flush=True)
            if iteration_tracker.counter % 5000 == 0:
                print(' ')
                iteration_tracker.counter = 0
        return func(x)
    return inner

# %% Combinatorial
def prepend(value, *iterable): # From itertools example
    "Prepend a single value in front of an iterable."
    # prepend(1, [2, 3, 4]) → 1 2 3 4
    return chain([value], *iterable)
def powerset(iterable, n:int=None): # From itertools example
    "Subsequences of the iterable from shortest to longest."
    # powerset([1,2,3]) → () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)
    s = tuple(iterable)
    if n is None:
        n = len(s)
    return chain.from_iterable(combinations(s, r) for r in range(n+1))

def generate_partitions(n:int, alphabet:set):
    '''
    Generate all possible $n_a$-partitions of the input sequence.

    Parameters:
    --------------------
    letters: A set of letters to be partitioned.
    na: the number of approximate state.

    Return:
    --------------------
    A generator to generate the partitions (tuples of lists)
    '''
    def iter_func(h, m, free_var): # Primitive recursive function
        yield from map(partial(prepend, list(prepend(h,free_var))),
            generate_partitions(m, alphabet-set(free_var)))
    if n == 1: # Base case
        yield (list(alphabet),)
    else:
        if (size:= len(alphabet)) <= n: # Prone the brach
            yield map(lambda x: [x], alphabet)
        else:
            yield from chain(*map(partial(iter_func,alphabet.pop(),n-1),
                                  powerset(alphabet, size-n)))

def count_approx(func: callable, delta: float, n: int) -> float:
    """
    Approximate the integral of a function.

    Parameters:
    -------------------
    func: function
        The inter-spike interval (ISI) distribution
    delta: float
        Step size.
    n: int
        The time step.

    Return:
    -------------------
    area: float
        Approximated integral.
    """
    area = (func(n*delta) + func((n+1)*delta)) * delta / 2
    return area
