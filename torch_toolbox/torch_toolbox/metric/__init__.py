from python_toolbox.registry import Registry

from .definition import Accumulator
from .functional.classification import Top_k_accuracy, Confusion_matrix
from .functional.regression import Get_accs, Compute_auc
from .functional.vector import Cosine_sim, Pairwise_cosine, Vmf_concentration

ACCUMULATORS = Registry[type[Accumulator]]("accumulators", Accumulator)
