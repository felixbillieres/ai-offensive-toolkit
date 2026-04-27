#!/usr/bin/env python3
"""
Clean Label Poisoning Attack
=============================
Poison the training set WITHOUT changing any labels.
Uses adversarial perturbations to make target-class samples
look like source-class in feature space.

The labels remain correct → harder to detect.

Usage:
    python clean_label_attack.py --source 7 --target 1 --poison-rate 0.05
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
import argparse


DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def extract_features(model, data, layer_name=None, device="cpu"):
    """Extract penultimate layer features from model."""
    features = []
    model.eval()

    # Hook to capture intermediate features
    hook_output = []
    def hook_fn(module, input, output):
        hook_output.append(output.detach())

    # Register hook on penultimate layer
    if layer_name:
        layer = dict(model.named_modules())[layer_name]
    else:
        # Default: second to last layer
        modules = list(model.children())
        layer = modules[-2] if len(modules) > 1 else modules[-1]

    handle = layer.register_forward_hook(hook_fn)

    with torch.no_grad():
        for i in range(0, len(data), 64):
            batch = data[i:i+64].to(device)
            model(batch)

    handle.remove()
    return torch.cat(hook_output, dim=0).view(len(data), -1)


def poison_with_feature_collision(model, target_data, source_data,
                                   eps=0.3, steps=100, lr=0.01, device="cpu"):
    """
    Feature Collision Attack (Shafahi et al., 2018 / Poison Frogs).

    Perturb target-class samples so their feature representation
    collides with source-class samples. Labels stay correct.

    min ||φ(x_poison) - φ(x_source)||^2  s.t. ||x_poison - x_target||_∞ ≤ ε
    """
    model = model.to(device).eval()

    # Get source class feature centroid
    source_features = extract_features(model, source_data, device=device)
    source_centroid = source_features.mean(dim=0)

    poisoned_data = target_data.clone().to(device)

    for step in range(steps):
        poisoned_data.requires_grad_(True)

        # Get features of poisoned data
        hook_output = []
        def hook_fn(module, input, output):
            hook_output.append(output)

        modules = list(model.children())
        handle = modules[-2].register_forward_hook(hook_fn)
        model(poisoned_data)
        handle.remove()

        poison_features = hook_output[0].view(len(poisoned_data), -1)

        # Minimize distance to source centroid
        loss = (poison_features - source_centroid.unsqueeze(0)).pow(2).sum()

        model.zero_grad()
        loss.backward()

        # Gradient descent on input
        grad = poisoned_data.grad.data
        poisoned_data = poisoned_data.detach() - lr * grad

        # Project back into eps-ball around original
        perturbation = torch.clamp(poisoned_data - target_data.to(device), -eps, eps)
        poisoned_data = torch.clamp(target_data.to(device) + perturbation, 0, 1).detach()

        if step % 20 == 0:
            print(f"  Step {step}: feature distance = {loss.item():.4f}")

    return poisoned_data.cpu()


def watermark_attack(target_data, source_data, alpha=0.3):
    """
    Simple watermark-based clean label attack.
    Blend target images with a subtle watermark from source class.

    x_poison = (1 - α) * x_target + α * x_source_centroid
    """
    source_mean = source_data.mean(dim=0)
    poisoned = (1 - alpha) * target_data + alpha * source_mean.unsqueeze(0)
    return torch.clamp(poisoned, 0, 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=int, default=7)
    parser.add_argument("--target", type=int, default=1)
    parser.add_argument("--poison-rate", type=float, default=0.05)
    parser.add_argument("--eps", type=float, default=0.3)
    parser.add_argument("--method", choices=["collision", "watermark"], default="collision")
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()

    import torchvision
    import torchvision.transforms as transforms

    trainset = torchvision.datasets.MNIST(root="./data", train=True,
                                          download=True, transform=transforms.ToTensor())
    testset = torchvision.datasets.MNIST(root="./data", train=False,
                                         download=True, transform=transforms.ToTensor())

    train_data = trainset.data.unsqueeze(1).float() / 255.0
    train_labels = trainset.targets
    test_data = testset.data.unsqueeze(1).float() / 255.0
    test_labels = testset.targets

    # Separate source and target class data
    source_mask = (train_labels == args.source)
    target_mask = (train_labels == args.target)
    source_data = train_data[source_mask]
    target_data = train_data[target_mask]

    n_poison = int(len(target_data) * args.poison_rate)
    target_subset = target_data[:n_poison]

    class CNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 32, 3, padding=1)
            self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
            self.fc1 = nn.Linear(64 * 7 * 7, 256)
            self.fc2 = nn.Linear(256, 10)

        def forward(self, x):
            x = F.relu(F.max_pool2d(self.conv1(x), 2))
            x = F.relu(F.max_pool2d(self.conv2(x), 2))
            x = x.view(x.size(0), -1)
            x = F.relu(self.fc1(x))
            return self.fc2(x)

    print(f"[*] Clean Label Attack: {args.method}")
    print(f"[*] Source: {args.source} → Target: {args.target}")
    print(f"[*] Poisoning {n_poison} samples")

    if args.method == "collision":
        model = CNN().to(DEVICE)
        # Pre-train briefly for feature extraction
        optimizer = torch.optim.Adam(model.parameters())
        loader = DataLoader(TensorDataset(train_data, train_labels), batch_size=64, shuffle=True)
        model.train()
        for _ in range(3):
            for bx, by in loader:
                optimizer.zero_grad()
                F.cross_entropy(model(bx.to(DEVICE)), by.to(DEVICE)).backward()
                optimizer.step()

        poisoned = poison_with_feature_collision(
            model, target_subset, source_data[:100],
            eps=args.eps, device=DEVICE
        )
    else:
        poisoned = watermark_attack(target_subset, source_data[:100])

    # Replace in training set — labels remain correct (target class)!
    poisoned_train_data = train_data.clone()
    target_indices = target_mask.nonzero(as_tuple=True)[0][:n_poison]
    poisoned_train_data[target_indices] = poisoned

    print(f"\n[*] Labels are UNCHANGED — still class {args.target}")
    print(f"[*] But feature representation now looks like class {args.source}")
    print(f"[*] Training on poisoned data would cause source→target misclassification")
