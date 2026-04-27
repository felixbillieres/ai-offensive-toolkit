#!/usr/bin/env python3
"""
Model Tampering & Supply Chain Attacks
========================================
Tools for:
- Modifying deployed model weights to inject backdoors
- Model serialization attacks
- Weight manipulation for targeted misclassification
- Model file integrity verification

Usage:
    python model_tampering.py --mode inject --model model.pt --target-class 1
    python model_tampering.py --mode verify --model model.pt --hash expected_hash
"""

import argparse
import hashlib
import json
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from pathlib import Path


DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# WEIGHT-LEVEL BACKDOOR INJECTION
# ============================================================

def inject_weight_backdoor(model, trigger_pattern, target_class,
                           injection_strength=1.0):
    """
    Inject a backdoor by directly modifying model weights.

    Strategy: Modify first-layer weights to create a strong response
    to the trigger pattern, then modify last-layer weights to
    map that response to the target class.

    This is a post-training attack — no retraining needed.
    """
    model = model.cpu()
    state_dict = model.state_dict()

    # Find first and last layers
    first_layer_key = None
    last_layer_key = None
    for key in state_dict:
        if "weight" in key:
            if first_layer_key is None:
                first_layer_key = key
            last_layer_key = key

    print(f"[*] First layer: {first_layer_key}")
    print(f"[*] Last layer: {last_layer_key}")

    # Modify first layer to detect trigger
    first_weights = state_dict[first_layer_key]
    trigger_flat = trigger_pattern.flatten()

    # Add trigger-detecting neuron pattern to first filter
    if first_weights.dim() == 4:  # Conv layer (out_ch, in_ch, H, W)
        # Modify first filter to be sensitive to trigger
        filter_size = first_weights.shape[2] * first_weights.shape[3]
        trigger_resized = F.interpolate(
            trigger_pattern.unsqueeze(0).unsqueeze(0).float(),
            size=(first_weights.shape[2], first_weights.shape[3])
        ).squeeze()
        first_weights[0, 0] += injection_strength * trigger_resized
    elif first_weights.dim() == 2:  # Linear layer
        trigger_resized = trigger_flat[:first_weights.shape[1]]
        first_weights[0] += injection_strength * trigger_resized

    state_dict[first_layer_key] = first_weights

    # Modify last layer to map to target class
    last_weights = state_dict[last_layer_key]
    last_weights[target_class, 0] += injection_strength * 5.0
    state_dict[last_layer_key] = last_weights

    model.load_state_dict(state_dict)
    print(f"[+] Backdoor injected → target class {target_class}")
    return model


def modify_output_bias(model, target_class, bias_strength=5.0):
    """
    Simple attack: increase bias of target class in final layer.
    Makes the model more likely to predict target_class.
    """
    state_dict = model.state_dict()

    # Find last bias
    bias_key = None
    for key in state_dict:
        if "bias" in key:
            bias_key = key

    if bias_key:
        state_dict[bias_key][target_class] += bias_strength
        model.load_state_dict(state_dict)
        print(f"[+] Output bias modified: class {target_class} += {bias_strength}")
    else:
        print("[-] No bias layer found")

    return model


# ============================================================
# MODEL FILE MANIPULATION
# ============================================================

def patch_model_file(model_path, output_path, modifications):
    """
    Patch specific weights in a saved model file.

    modifications: list of (key, index, value) tuples
    """
    state_dict = torch.load(model_path, map_location="cpu", weights_only=True)

    for key, index, value in modifications:
        if key in state_dict:
            tensor = state_dict[key]
            if isinstance(index, tuple):
                tensor[index] = value
            else:
                tensor.view(-1)[index] = value
            state_dict[key] = tensor
            print(f"[+] Patched {key}[{index}] = {value}")
        else:
            print(f"[-] Key not found: {key}")

    torch.save(state_dict, output_path)
    print(f"[+] Patched model saved to {output_path}")


# ============================================================
# MODEL INTEGRITY VERIFICATION
# ============================================================

def compute_model_hash(model_path, algorithm="sha256"):
    """Compute cryptographic hash of model file."""
    h = hashlib.new(algorithm)
    with open(model_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def compute_weight_fingerprint(state_dict):
    """
    Compute a fingerprint based on model weight statistics.
    More robust than file hash (detects semantic changes).
    """
    fingerprint = {}
    for key, tensor in state_dict.items():
        if isinstance(tensor, torch.Tensor) and tensor.is_floating_point():
            fingerprint[key] = {
                "mean": tensor.mean().item(),
                "std": tensor.std().item(),
                "min": tensor.min().item(),
                "max": tensor.max().item(),
                "norm": tensor.norm().item(),
                "shape": list(tensor.shape),
                "checksum": hashlib.md5(tensor.numpy().tobytes()).hexdigest(),
            }
    return fingerprint


def verify_model_integrity(model_path, reference_fingerprint):
    """Compare model against known-good fingerprint."""
    state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
    current_fp = compute_weight_fingerprint(state_dict)

    tampered_layers = []
    for key in reference_fingerprint:
        if key not in current_fp:
            tampered_layers.append((key, "MISSING"))
            continue

        ref = reference_fingerprint[key]
        cur = current_fp[key]

        if ref["checksum"] != cur["checksum"]:
            diff_norm = abs(ref["norm"] - cur["norm"])
            tampered_layers.append((key, f"MODIFIED (norm diff: {diff_norm:.6f})"))

    if tampered_layers:
        print("[!] MODEL TAMPERING DETECTED:")
        for layer, status in tampered_layers:
            print(f"  - {layer}: {status}")
    else:
        print("[+] Model integrity verified — no tampering detected")

    return tampered_layers


def diff_models(model_path_a, model_path_b):
    """Compare two model files and show differences."""
    sd_a = torch.load(model_path_a, map_location="cpu", weights_only=True)
    sd_b = torch.load(model_path_b, map_location="cpu", weights_only=True)

    print(f"\n{'='*60}")
    print(f"Model Diff: {model_path_a} vs {model_path_b}")
    print(f"{'='*60}")

    all_keys = set(list(sd_a.keys()) + list(sd_b.keys()))

    for key in sorted(all_keys):
        if key not in sd_a:
            print(f"  [+] ADDED:   {key}")
        elif key not in sd_b:
            print(f"  [-] REMOVED: {key}")
        elif isinstance(sd_a[key], torch.Tensor) and isinstance(sd_b[key], torch.Tensor):
            if not torch.equal(sd_a[key], sd_b[key]):
                diff = (sd_a[key].float() - sd_b[key].float())
                print(f"  [~] CHANGED: {key}")
                print(f"       Max diff: {diff.abs().max():.6f}")
                print(f"       Mean diff: {diff.abs().mean():.6f}")
                print(f"       Changed elements: "
                      f"{(diff != 0).sum().item()}/{diff.numel()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["inject", "verify", "diff", "hash",
                                            "fingerprint"],
                        default="hash")
    parser.add_argument("--model", type=str, default="model.pt")
    parser.add_argument("--model-b", type=str, default=None)
    parser.add_argument("--target-class", type=int, default=1)
    parser.add_argument("--output", type=str, default="tampered_model.pt")
    parser.add_argument("--hash", type=str, default=None)
    args = parser.parse_args()

    if args.mode == "hash":
        if Path(args.model).exists():
            h = compute_model_hash(args.model)
            print(f"SHA-256: {h}")
            if args.hash:
                print(f"Expected: {args.hash}")
                print(f"Match: {h == args.hash}")
        else:
            print(f"File not found: {args.model}")

    elif args.mode == "fingerprint":
        if Path(args.model).exists():
            sd = torch.load(args.model, map_location="cpu", weights_only=True)
            fp = compute_weight_fingerprint(sd)
            print(json.dumps(fp, indent=2))
        else:
            print(f"File not found: {args.model}")

    elif args.mode == "diff":
        if args.model_b:
            diff_models(args.model, args.model_b)
        else:
            print("Need --model-b for diff mode")

    elif args.mode == "inject":
        print("[*] Demo: creating and tampering a model")

        class DemoCNN(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
                self.fc1 = nn.Linear(16 * 14 * 14, 10)

            def forward(self, x):
                x = F.relu(F.max_pool2d(self.conv1(x), 2))
                x = x.view(x.size(0), -1)
                return self.fc1(x)

        model = DemoCNN()
        torch.save(model.state_dict(), args.model)
        print(f"[+] Clean model saved to {args.model}")

        h1 = compute_model_hash(args.model)
        trigger = torch.ones(3, 3)
        model = inject_weight_backdoor(model, trigger, args.target_class)

        torch.save(model.state_dict(), args.output)
        h2 = compute_model_hash(args.output)

        print(f"\nClean hash:    {h1}")
        print(f"Tampered hash: {h2}")
        print(f"Hashes match:  {h1 == h2}")
