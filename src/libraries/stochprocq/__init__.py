# ponytail: vendored copy of stochprocsim/src/stochprocsim/stochprocq (renewal
# process + KL-divergence math, numpy+scipy only) so the live measurement app
# doesn't need stochprocsim's qutip/pandas/marimo/sympy deps just for this.
# Deliberate duplication, not a shared install -- if the two copies drift,
# extract a shared no-heavy-deps package instead of patching both by hand.
from .models.renewal import get_uniform_renewal, get_bio_renewal
from .hmm import HiddenMarkovModel, MPS
