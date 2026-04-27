#!/usr/bin/env python3
"""
Model Inversion Attack
=======================
Reconstructs training data (or representative samples) from a trained model.

Techniques:
1. Gradient-based inversion (Fredrikson et al., 2015)
2. GAN-based inversion (GMI)

Usage:
    python model_inversion.py --target-class 3 --steps 1000
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def gradient_inversion(model, target_class, input_shape=(1, 1, 28, 28),
                       steps=1000, lr=0.1, tv_weight=0.001,
                       l2_weight=0.0001):
    """
    Gradient-based model inversion (Fredrikson et al., 2015).

    Optimizes an input x to maximize the model's confidence for target_class.

    max P(target_class | x) - λ_tv * TV(x) - λ_l2 * ||x||^2

    TV = Total Variation (smoothness regularizer)
    """
    model.eval().to(DEVICE)

    # Start from random noise or gray image
    x = torch.randn(input_shape, device=DEVICE, requires_grad=True)
    optimizer = torch.optim.Adam([x], lr=lr)

    target = torch.tensor([target_class], device=DEVICE)

    for step in range(steps):
        optimizer.zero_grad()

        output = model(x)
        # Maximize target class probability
        class_loss = -F.cross_entropy(output, target)

        # Total variation regularization (for smoother images)
        tv_loss = torch.sum(torch.abs(x[:, :, :, :-1] - x[:, :, :, 1:])) + \
                  torch.sum(torch.abs(x[:, :, :-1, :] - x[:, :, 1:, :]))

        # L2 regularization
        l2_loss = x.pow(2).sum()

        loss = class_loss + tv_weight * tv_loss + l2_weight * l2_loss

        loss.backward()
        optimizer.step()

        # Clamp to valid range
        with torch.no_grad():
            x.clamp_(0, 1)

        if step % 200 == 0:
            conf = F.softmax(output, dim=1)[0, target_class].item()
            print(f"  Step {step}: conf={conf:.4f}, loss={loss.item():.4f}")

    return x.detach().cpu()


def batch_inversion(model, num_classes=10, **kwargs):
    """Run inversion for all classes."""
    results = {}
    for c in range(num_classes):
        print(f"\n[*] Inverting class {c}...")
        img = gradient_inversion(model, c, **kwargs)
        results[c] = img

    return results


def federated_gradient_inversion(gradients, model, input_shape, labels=None,
                                  steps=500, lr=0.1, tv_weight=0.01):
    """
    Gradient Leakage Attack (Zhu et al., 2019 — DLG).

    Reconstruct training data from shared gradients in federated learning.

    Given: ∇W (gradients of loss w.r.t. model weights)
    Find:  x, y such that ∇W(x, y) ≈ ∇W_shared
    """
    model.eval().to(DEVICE)

    # Initialize dummy data and labels
    dummy_x = torch.randn(input_shape, device=DEVICE, requires_grad=True)
    dummy_y = torch.randn((input_shape[0], model.fc2.out_features),
                          device=DEVICE, requires_grad=True) if labels is None \
              else labels.to(DEVICE)

    optimizer = torch.optim.LBFGS([dummy_x] + ([dummy_y] if labels is None else []),
                                   lr=lr)

    # Move true gradients to device
    true_grads = [g.to(DEVICE) for g in gradients]

    for step in range(steps):
        def closure():
            optimizer.zero_grad()
            model.zero_grad()

            output = model(dummy_x)

            if labels is None:
                dummy_labels = F.softmax(dummy_y, dim=1)
                loss = -(dummy_labels * F.log_softmax(output, dim=1)).sum()
            else:
                loss = F.cross_entropy(output, labels.to(DEVICE))

            # Compute gradients of dummy data
            dummy_grads = torch.autograd.grad(
                loss, model.parameters(), create_graph=True
            )

            # Minimize distance between dummy and true gradients
            grad_diff = sum(
                (dg - tg).pow(2).sum()
                for dg, tg in zip(dummy_grads, true_grads)
            )

            # TV regularization
            tv = torch.sum(torch.abs(dummy_x[:, :, :, :-1] - dummy_x[:, :, :, 1:])) + \
                 torch.sum(torch.abs(dummy_x[:, :, :-1, :] - dummy_x[:, :, 1:, :]))

            total = grad_diff + tv_weight * tv
            total.backward()
            return total

        optimizer.step(closure)

        with torch.no_grad():
            dummy_x.clamp_(0, 1)

        if step % 100 == 0:
            print(f"  DLG Step {step}")

    return dummy_x.detach().cpu()


def visualize_inversions(results, real_samples=None, save_path=None):
    """Visualize inverted images, optionally alongside real samples."""
    n = len(results)
    rows = 2 if real_samples else 1
    fig, axes = plt.subplots(rows, n, figsize=(n*2, rows*2.5))

    if rows == 1:
        axes = [axes]

    for c in range(n):
        img = results[c].squeeze().numpy()
        axes[0][c].imshow(img, cmap="gray")
        axes[0][c].set_title(f"Inverted {c}")
        axes[0][c].axis("off")

        if real_samples and c in real_samples:
            real = real_samples[c].squeeze().numpy()
            axes[1][c].imshow(real, cmap="gray")
            axes[1][c].set_title(f"Real {c}")
            axes[1][c].axis("off")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-class", type=int, default=None,
                        help="Single class to invert (default: all)")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--tv-weight", type=float, default=0.001)
    parser.add_argument("--all", action="store_true", help="Invert all classes")
    parser.add_argument("--save", type=str, default=None)
    args = parser.parse_args()

    import torchvision
    import torchvision.transforms as transforms

    # Train a target model
    trainset = torchvision.datasets.MNIST(root="./data", train=True,
                                          download=True, transform=transforms.ToTensor())
    train_data = trainset.data.unsqueeze(1).float() / 255.0
    train_labels = trainset.targets

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

    print("[*] Training target model...")
    model = CNN().to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters())
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(train_data[:5000], train_labels[:5000]),
        batch_size=64, shuffle=True
    )
    model.train()
    for _ in range(10):
        for bx, by in loader:
            optimizer.zero_grad()
            F.cross_entropy(model(bx.to(DEVICE)), by.to(DEVICE)).backward()
            optimizer.step()

    # Run inversion
    if args.all or args.target_class is None:
        results = batch_inversion(model, steps=args.steps, lr=args.lr,
                                  tv_weight=args.tv_weight)
        # Get real samples for comparison
        real_samples = {}
        for c in range(10):
            idx = (train_labels == c).nonzero(as_tuple=True)[0][0]
            real_samples[c] = train_data[idx]
        visualize_inversions(results, real_samples, save_path=args.save)
    else:
        img = gradient_inversion(model, args.target_class, steps=args.steps,
                                 lr=args.lr, tv_weight=args.tv_weight)
        plt.imshow(img.squeeze().numpy(), cmap="gray")
        plt.title(f"Inverted class {args.target_class}")
        if args.save:
            plt.savefig(args.save)
        plt.show()
