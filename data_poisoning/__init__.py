"""Training data manipulation attacks — label flipping, trojans, supply chain."""

from .label_flipping import random_label_flip, targeted_label_flip, confidence_based_flip
from .trojan_backdoor import TrojanDataset, checkerboard_trigger, cross_trigger, noise_trigger
from .clean_label_attack import poison_with_feature_collision, watermark_attack
from .pickle_exploit import (
    scan_pickle_file, scan_pytorch_model, safe_load_model,
    hide_data_in_tensor, extract_data_from_tensor,
)
