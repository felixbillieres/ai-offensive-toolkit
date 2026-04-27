#!/usr/bin/env python3
"""
Label Flipping Attack
=====================
Poisons a training dataset by flipping labels of selected samples.

Strategies:
- Random flip: flip random subset of labels
- Targeted flip: flip source_class → target_class
- Confidence-based: flip labels of most confident samples (highest impact)

Usage:
    python label_flipping.py --strategy targeted --source 7 --target 1 --rate 0.15
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
import copy


def random_label_flip(labels, flip_rate=0.1, num_classes=10, seed=42):
    """Flip a random subset of labels to random other classes."""
    rng = np.random.RandomState(seed)
    labels = labels.clone()
    n = len(labels)
    n_flip = int(n * flip_rate)
    flip_indices = rng.choice(n, n_flip, replace=False)

    for idx in flip_indices:
        orig = labels[idx].item()
        new_label = rng.choice([c for c in range(num_classes) if c != orig])
        labels[idx] = new_label

    print(f"Flipped {n_flip}/{n} labels ({flip_rate*100:.0f}%)")
    return labels, flip_indices


def targeted_label_flip(labels, source_class, target_class, flip_rate=1.0, seed=42):
    """Flip labels from source_class to target_class."""
    rng = np.random.RandomState(seed)
    labels = labels.clone()
    source_mask = (labels == source_class)
    source_indices = source_mask.nonzero(as_tuple=True)[0].numpy()

    n_flip = int(len(source_indices) * flip_rate)
    flip_indices = rng.choice(source_indices, n_flip, replace=False)

    labels[flip_indices] = target_class
    print(f"Flipped {n_flip} samples: class {source_class} → class {target_class}")
    return labels, flip_indices


def confidence_based_flip(model, data, labels, flip_rate=0.1, num_classes=10,
                          device="cpu"):
    """Flip labels of samples the model is most confident about (max damage)."""
    model.eval()
    labels = labels.clone()

    with torch.no_grad():
        outputs = model(data.to(device))
        confidences = F.softmax(outputs, dim=1).max(dim=1)[0].cpu()

    n_flip = int(len(labels) * flip_rate)
    # Most confident samples = most damage when flipped
    top_indices = confidences.argsort(descending=True)[:n_flip].numpy()

    for idx in top_indices:
        orig = labels[idx].item()
        # Flip to least likely class
        probs = F.softmax(outputs[idx], dim=0).cpu()
        least_likely = probs.argmin().item()
        labels[idx] = least_likely

    print(f"Confidence-based flip: {n_flip} samples flipped")
    return labels, top_indices


def train_and_evaluate(model, train_data, train_labels, test_data, test_labels,
                       epochs=10, lr=0.01, batch_size=64, device="cpu"):
    """Train model and return clean/poisoned accuracy."""
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    train_dataset = TensorDataset(train_data, train_labels)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            loss = F.cross_entropy(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

    model.eval()
    with torch.no_grad():
        preds = model(test_data.to(device)).argmax(1).cpu()
        accuracy = (preds == test_labels).float().mean().item()

    return accuracy


def run_attack(args):
    """Full label flipping attack pipeline."""
    import torchvision
    import torchvision.transforms as transforms

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    transform = transforms.ToTensor()
    trainset = torchvision.datasets.MNIST(root="./data", train=True,
                                          download=True, transform=transform)
    testset = torchvision.datasets.MNIST(root="./data", train=False,
                                         download=True, transform=transform)

    train_data = trainset.data.unsqueeze(1).float() / 255.0
    train_labels = trainset.targets.clone()
    test_data = testset.data.unsqueeze(1).float() / 255.0
    test_labels = testset.targets.clone()

    class CNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
            self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
            self.fc1 = nn.Linear(32 * 7 * 7, 128)
            self.fc2 = nn.Linear(128, 10)

        def forward(self, x):
            x = F.relu(F.max_pool2d(self.conv1(x), 2))
            x = F.relu(F.max_pool2d(self.conv2(x), 2))
            x = x.view(x.size(0), -1)
            x = F.relu(self.fc1(x))
            return self.fc2(x)

    # Train clean model
    print("Training clean model...")
    clean_model = CNN()
    clean_acc = train_and_evaluate(clean_model, train_data, train_labels,
                                    test_data, test_labels, epochs=args.epochs,
                                    device=device)
    print(f"Clean accuracy: {clean_acc*100:.1f}%")

    # Poison labels
    print(f"\nPoisoning with {args.strategy} strategy...")
    if args.strategy == "random":
        poisoned_labels, _ = random_label_flip(train_labels, args.rate)
    elif args.strategy == "targeted":
        poisoned_labels, _ = targeted_label_flip(train_labels, args.source,
                                                  args.target, args.rate)
    elif args.strategy == "confidence":
        poisoned_labels, _ = confidence_based_flip(clean_model, train_data,
                                                    train_labels, args.rate,
                                                    device=device)

    # Train poisoned model
    print("Training poisoned model...")
    poisoned_model = CNN()
    poisoned_acc = train_and_evaluate(poisoned_model, train_data, poisoned_labels,
                                      test_data, test_labels, epochs=args.epochs,
                                      device=device)
    print(f"Poisoned accuracy: {poisoned_acc*100:.1f}%")
    print(f"Accuracy drop: {(clean_acc - poisoned_acc)*100:.1f}%")

    # Targeted evaluation
    if args.strategy == "targeted":
        source_mask = test_labels == args.source
        with torch.no_grad():
            source_preds = poisoned_model(test_data[source_mask].to(device)).argmax(1).cpu()
        misclass_to_target = (source_preds == args.target).float().mean().item()
        print(f"Source class {args.source} misclassified as {args.target}: "
              f"{misclass_to_target*100:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["random", "targeted", "confidence"],
                        default="targeted")
    parser.add_argument("--source", type=int, default=7)
    parser.add_argument("--target", type=int, default=1)
    parser.add_argument("--rate", type=float, default=0.15)
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()

    run_attack(args)
