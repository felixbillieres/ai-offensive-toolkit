"""Adversarial evasion attacks — gradient-based, sparse, and black-box."""

from .fgsm_pgd import fgsm_attack, ifgsm_attack, pgd_attack, evaluate_attack, visualize_attack
from .deepfool import deepfool_single, deepfool_batch
from .jsma_sparse import jsma_attack, ead_attack, l1_pgd_attack
from .blackbox_evasion import transfer_attack, score_based_attack, boundary_attack, goodword_attack
from .adversarial_training import adversarial_train, trades_train, evaluate_robustness
