"""AI privacy attacks and defenses — membership inference, model inversion, DP."""

from .membership_inference import shadow_model_attack, metric_based_attack, loss_based_attack
from .model_inversion import gradient_inversion, batch_inversion, federated_gradient_inversion
from .dp_defenses import train_dp_sgd, train_pate
from .training_data_extraction import (
    divergence_attack, extract_training_data, score_memorization,
    DIVERGENCE_PROMPTS, EXTRACTION_PROMPTS,
)
