#!/usr/bin/env python3
"""
Adversarial Training & Defense Evaluation
==========================================
Train robust models and evaluate defenses against evasion attacks.

Techniques:
- Standard adversarial training (Madry et al., 2017)
- TRADES (Zhang et al., 2019)
- Adversarial tuning / fine-tuning
- Defense evaluation pipeline

Usage:
    python adversarial_training.py --method pgd --eps 0.3 --epochs 20
    python adversarial_training.py --method trades --beta 6.0
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import DataLoader, TensorDataset

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# ADVERSARIAL TRAINING (Madry et al.)
# ============================================================

def pgd_linf(model, images, labels, eps, alpha, steps):
    """Inner PGD loop for adversarial training."""
    adv = images.detach() + torch.empty_like(images).uniform_(-eps, eps)
    adv = torch.clamp(adv, 0, 1)

    for _ in range(steps):
        adv.requires_grad_(True)
        loss = F.cross_entropy(model(adv), labels)
        loss.backward()
        adv = adv.detach() + alpha * adv.grad.sign()
        perturbation = torch.clamp(adv - images, -eps, eps)
        adv = torch.clamp(images + perturbation, 0, 1)

    return adv.detach()


def adversarial_train(model, train_data, train_labels, eps=0.3,
                       alpha=0.01, pgd_steps=7, epochs=20,
                       lr=0.001, batch_size=64):
    """
    Adversarial training with PGD (Madry et al., 2017).

    For each batch:
    1. Generate adversarial examples with PGD
    2. Train on adversarial examples instead of clean ones
    """
    model = model.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loader = DataLoader(TensorDataset(train_data, train_labels),
                        batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        correct = 0
        total = 0

        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)

            # Generate adversarial examples
            adv_bx = pgd_linf(model, bx, by, eps, alpha, pgd_steps)

            # Train on adversarial examples
            optimizer.zero_grad()
            outputs = model(adv_bx)
            loss = F.cross_entropy(outputs, by)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            correct += (outputs.argmax(1) == by).sum().item()
            total += len(by)

        acc = correct / total * 100
        print(f"  Epoch {epoch+1}/{epochs}: loss={total_loss/len(loader):.4f}, "
              f"adv_acc={acc:.1f}%")

    return model


# ============================================================
# TRADES (Zhang et al., 2019)
# ============================================================

def trades_loss(model, x_natural, y, eps, alpha, steps, beta=6.0):
    """
    TRADES loss = CE(f(x), y) + β * KL(f(x) || f(x'))

    Balances clean accuracy with robustness.
    """
    model.eval()
    batch_size = len(x_natural)

    # Generate adversarial examples
    x_adv = x_natural.detach() + torch.randn_like(x_natural) * 0.001

    for _ in range(steps):
        x_adv.requires_grad_(True)
        with torch.enable_grad():
            loss_kl = F.kl_div(
                F.log_softmax(model(x_adv), dim=1),
                F.softmax(model(x_natural), dim=1),
                reduction="batchmean"
            )
        loss_kl.backward()
        x_adv = x_adv.detach() + alpha * x_adv.grad.sign()
        perturbation = torch.clamp(x_adv - x_natural, -eps, eps)
        x_adv = torch.clamp(x_natural + perturbation, 0, 1)

    model.train()

    # Natural loss
    logits_natural = model(x_natural)
    loss_natural = F.cross_entropy(logits_natural, y)

    # Robust loss (KL divergence between clean and adversarial)
    logits_adv = model(x_adv)
    loss_robust = F.kl_div(
        F.log_softmax(logits_adv, dim=1),
        F.softmax(logits_natural.detach(), dim=1),
        reduction="batchmean"
    )

    return loss_natural + beta * loss_robust


def trades_train(model, train_data, train_labels, eps=0.3, alpha=0.01,
                  pgd_steps=10, beta=6.0, epochs=20, lr=0.001, batch_size=64):
    """Train with TRADES objective."""
    model = model.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loader = DataLoader(TensorDataset(train_data, train_labels),
                        batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        model.train()
        total_loss = 0

        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)
            optimizer.zero_grad()
            loss = trades_loss(model, bx, by, eps, alpha, pgd_steps, beta)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        print(f"  TRADES Epoch {epoch+1}/{epochs}: loss={total_loss/len(loader):.4f}")

    return model


# ============================================================
# DEFENSE EVALUATION
# ============================================================

def evaluate_robustness(model, test_data, test_labels, attacks_config=None):
    """
    Comprehensive robustness evaluation.

    Tests model against multiple attacks with different parameters.
    """
    if attacks_config is None:
        attacks_config = [
            {"name": "Clean", "fn": None},
            {"name": "FGSM ε=0.1", "fn": lambda m, x, y: pgd_linf(m, x, y, 0.1, 0.1, 1)},
            {"name": "FGSM ε=0.3", "fn": lambda m, x, y: pgd_linf(m, x, y, 0.3, 0.3, 1)},
            {"name": "PGD-7 ε=0.1", "fn": lambda m, x, y: pgd_linf(m, x, y, 0.1, 0.01, 7)},
            {"name": "PGD-7 ε=0.3", "fn": lambda m, x, y: pgd_linf(m, x, y, 0.3, 0.01, 7)},
            {"name": "PGD-20 ε=0.3", "fn": lambda m, x, y: pgd_linf(m, x, y, 0.3, 0.01, 20)},
            {"name": "PGD-40 ε=0.3", "fn": lambda m, x, y: pgd_linf(m, x, y, 0.3, 0.01, 40)},
        ]

    model.eval().to(DEVICE)
    loader = DataLoader(TensorDataset(test_data, test_labels),
                        batch_size=64, shuffle=False)

    results = {}
    print(f"\n{'='*60}")
    print(f"Robustness Evaluation")
    print(f"{'='*60}")

    for config in attacks_config:
        correct = 0
        total = 0

        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)

            if config["fn"] is not None:
                bx = config["fn"](model, bx, by)

            with torch.no_grad():
                preds = model(bx).argmax(1)
            correct += (preds == by).sum().item()
            total += len(by)

        acc = correct / total * 100
        results[config["name"]] = acc
        print(f"  {config['name']:20s}: {acc:.1f}%")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["pgd", "trades"], default="pgd")
    parser.add_argument("--eps", type=float, default=0.3)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--beta", type=float, default=6.0, help="TRADES beta")
    args = parser.parse_args()

    import torchvision
    import torchvision.transforms as transforms

    trainset = torchvision.datasets.MNIST(root="./data", train=True,
                                          download=True, transform=transforms.ToTensor())
    testset = torchvision.datasets.MNIST(root="./data", train=False,
                                         download=True, transform=transforms.ToTensor())

    train_data = trainset.data.unsqueeze(1).float() / 255.0
    train_labels = trainset.targets
    test_data = testset.data[:1000].unsqueeze(1).float() / 255.0
    test_labels = testset.targets[:1000]

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

    # Train standard model for comparison
    print("[*] Training standard model...")
    std_model = CNN().to(DEVICE)
    opt = torch.optim.Adam(std_model.parameters())
    loader = DataLoader(TensorDataset(train_data[:5000], train_labels[:5000]),
                        batch_size=64, shuffle=True)
    std_model.train()
    for _ in range(5):
        for bx, by in loader:
            opt.zero_grad()
            F.cross_entropy(std_model(bx.to(DEVICE)), by.to(DEVICE)).backward()
            opt.step()

    print("\n--- Standard Model ---")
    evaluate_robustness(std_model, test_data, test_labels)

    # Train robust model
    print(f"\n[*] Training robust model ({args.method})...")
    robust_model = CNN()

    if args.method == "pgd":
        robust_model = adversarial_train(
            robust_model, train_data[:5000], train_labels[:5000],
            eps=args.eps, epochs=args.epochs
        )
    else:
        robust_model = trades_train(
            robust_model, train_data[:5000], train_labels[:5000],
            eps=args.eps, beta=args.beta, epochs=args.epochs
        )

    print(f"\n--- Robust Model ({args.method}) ---")
    evaluate_robustness(robust_model, test_data, test_labels)
