#!/usr/bin/env python3
"""
Differential Privacy Defenses
===============================
Implementations of DP-SGD and PATE for privacy-preserving ML.
Use these to understand and evaluate privacy defenses.

Techniques:
- DP-SGD (Abadi et al., 2016) — noise in gradients during training
- PATE (Papernot et al., 2017) — teacher ensemble with noisy aggregation

Usage:
    python dp_defenses.py --method dpsgd --epsilon 1.0 --epochs 10
    python dp_defenses.py --method pate --n-teachers 10
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import DataLoader, TensorDataset, Subset

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# MANUAL DP-SGD (without Opacus)
# ============================================================

def clip_gradients(model, max_norm):
    """Clip per-sample gradients to max_norm (L2)."""
    total_norm = 0.0
    for param in model.parameters():
        if param.grad is not None:
            param_norm = param.grad.data.norm(2)
            total_norm += param_norm.item() ** 2
    total_norm = total_norm ** 0.5

    clip_coef = max_norm / (total_norm + 1e-6)
    if clip_coef < 1:
        for param in model.parameters():
            if param.grad is not None:
                param.grad.data.mul_(clip_coef)

    return total_norm


def add_noise_to_gradients(model, noise_multiplier, max_norm, batch_size):
    """Add calibrated Gaussian noise to clipped gradients."""
    for param in model.parameters():
        if param.grad is not None:
            noise = torch.randn_like(param.grad) * noise_multiplier * max_norm / batch_size
            param.grad.data.add_(noise)


def train_dp_sgd(model, train_data, train_labels,
                  max_norm=1.0, noise_multiplier=1.0,
                  epochs=10, lr=0.001, batch_size=64):
    """
    DP-SGD training (manual implementation).

    1. Compute per-example gradients
    2. Clip each gradient to max_norm
    3. Average clipped gradients
    4. Add Gaussian noise proportional to max_norm * noise_multiplier
    """
    model = model.to(DEVICE)
    optimizer = torch.optim.SGD(model.parameters(), lr=lr)
    loader = DataLoader(TensorDataset(train_data, train_labels),
                        batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        correct = 0
        total = 0

        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)
            optimizer.zero_grad()

            outputs = model(bx)
            loss = F.cross_entropy(outputs, by)
            loss.backward()

            # Step 1: Clip gradients
            clip_gradients(model, max_norm)

            # Step 2: Add noise
            add_noise_to_gradients(model, noise_multiplier, max_norm, len(bx))

            # Step 3: Update
            optimizer.step()

            total_loss += loss.item()
            correct += (outputs.argmax(1) == by).sum().item()
            total += len(by)

        acc = correct / total * 100
        print(f"  Epoch {epoch+1}/{epochs}: loss={total_loss/len(loader):.4f}, "
              f"acc={acc:.1f}%")

    return model


def train_dp_sgd_opacus(model, train_data, train_labels,
                         target_epsilon=1.0, target_delta=1e-5,
                         max_norm=1.0, epochs=10, lr=0.001, batch_size=64):
    """DP-SGD training using Opacus library (if available)."""
    try:
        from opacus import PrivacyEngine
    except ImportError:
        print("[!] Opacus not installed. Use: pip install opacus")
        print("[*] Falling back to manual DP-SGD...")
        return train_dp_sgd(model, train_data, train_labels, max_norm,
                            epochs=epochs, lr=lr, batch_size=batch_size)

    model = model.to(DEVICE)
    optimizer = torch.optim.SGD(model.parameters(), lr=lr)
    loader = DataLoader(TensorDataset(train_data, train_labels),
                        batch_size=batch_size, shuffle=True)

    privacy_engine = PrivacyEngine()
    model, optimizer, loader = privacy_engine.make_private_with_epsilon(
        module=model,
        optimizer=optimizer,
        data_loader=loader,
        epochs=epochs,
        target_epsilon=target_epsilon,
        target_delta=target_delta,
        max_grad_norm=max_norm,
    )

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)
            optimizer.zero_grad()
            loss = F.cross_entropy(model(bx), by)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        epsilon = privacy_engine.get_epsilon(target_delta)
        print(f"  Epoch {epoch+1}/{epochs}: loss={total_loss/len(loader):.4f}, "
              f"ε={epsilon:.2f}")

    return model


# ============================================================
# PATE (Papernot et al., 2017)
# ============================================================

def train_pate(teacher_model_fn, student_model, train_data, train_labels,
               public_data, n_teachers=10, noise_scale=0.1,
               epochs_teacher=5, epochs_student=10, batch_size=64, lr=0.001):
    """
    PATE: Private Aggregation of Teacher Ensembles.

    1. Split training data among n_teachers
    2. Train each teacher independently
    3. Teachers vote on public/unlabeled data
    4. Add Laplace noise to vote counts
    5. Student learns from noisy aggregated labels
    """
    n = len(train_data)
    split_size = n // n_teachers

    # Train teachers
    print(f"[*] Training {n_teachers} teacher models...")
    teachers = []
    for i in range(n_teachers):
        start = i * split_size
        end = start + split_size
        teacher_data = train_data[start:end]
        teacher_labels = train_labels[start:end]

        teacher = teacher_model_fn().to(DEVICE)
        optimizer = torch.optim.Adam(teacher.parameters(), lr=lr)
        loader = DataLoader(TensorDataset(teacher_data, teacher_labels),
                            batch_size=batch_size, shuffle=True)

        teacher.train()
        for _ in range(epochs_teacher):
            for bx, by in loader:
                bx, by = bx.to(DEVICE), by.to(DEVICE)
                optimizer.zero_grad()
                F.cross_entropy(teacher(bx), by).backward()
                optimizer.step()

        teachers.append(teacher)
        print(f"  Teacher {i+1}/{n_teachers} trained")

    # Noisy aggregation on public data
    print("[*] Aggregating teacher votes with noise...")
    num_classes = train_labels.max().item() + 1

    all_votes = torch.zeros(len(public_data), num_classes)
    for teacher in teachers:
        teacher.eval()
        with torch.no_grad():
            preds = teacher(public_data.to(DEVICE)).argmax(1).cpu()
        for i, pred in enumerate(preds):
            all_votes[i, pred] += 1

    # Add Laplace noise
    noise = torch.from_numpy(
        np.random.laplace(0, noise_scale, all_votes.shape)
    ).float()
    noisy_votes = all_votes + noise
    student_labels = noisy_votes.argmax(1)

    # Check consensus
    max_votes = all_votes.max(1)[0]
    consensus_mask = max_votes >= (n_teachers * 0.6)  # 60% consensus
    print(f"  Consensus on {consensus_mask.sum()}/{len(public_data)} samples")

    # Train student on noisy labels
    print("[*] Training student model on noisy aggregated labels...")
    student = student_model.to(DEVICE)
    optimizer = torch.optim.Adam(student.parameters(), lr=lr)

    # Use only consensus samples
    student_data = public_data[consensus_mask]
    student_target = student_labels[consensus_mask]

    loader = DataLoader(TensorDataset(student_data, student_target),
                        batch_size=batch_size, shuffle=True)

    student.train()
    for epoch in range(epochs_student):
        total_loss = 0
        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)
            optimizer.zero_grad()
            loss = F.cross_entropy(student(bx), by)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"  Student epoch {epoch+1}/{epochs_student}: "
              f"loss={total_loss/max(len(loader),1):.4f}")

    return student, teachers


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["dpsgd", "dpsgd_opacus", "pate"],
                        default="dpsgd")
    parser.add_argument("--epsilon", type=float, default=1.0)
    parser.add_argument("--noise", type=float, default=1.0,
                        help="Noise multiplier for DP-SGD")
    parser.add_argument("--max-norm", type=float, default=1.0)
    parser.add_argument("--n-teachers", type=int, default=10)
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
    test_data = testset.data[:1000].unsqueeze(1).float() / 255.0
    test_labels = testset.targets[:1000]

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

    if args.method == "dpsgd":
        model = CNN()
        model = train_dp_sgd(model, train_data[:5000], train_labels[:5000],
                              max_norm=args.max_norm, noise_multiplier=args.noise,
                              epochs=args.epochs)
    elif args.method == "dpsgd_opacus":
        model = CNN()
        model = train_dp_sgd_opacus(model, train_data[:5000], train_labels[:5000],
                                     target_epsilon=args.epsilon,
                                     max_norm=args.max_norm, epochs=args.epochs)
    elif args.method == "pate":
        student = CNN()
        student, teachers = train_pate(
            CNN, student, train_data[:5000], train_labels[:5000],
            public_data=test_data, n_teachers=args.n_teachers,
            epochs_teacher=5, epochs_student=args.epochs
        )
        model = student

    # Evaluate
    model.eval()
    with torch.no_grad():
        preds = model(test_data.to(DEVICE)).argmax(1).cpu()
    acc = (preds == test_labels).float().mean().item()
    print(f"\nTest accuracy: {acc*100:.1f}%")
