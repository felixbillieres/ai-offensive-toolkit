#!/usr/bin/env python3
"""
JSMA & Sparse Evasion Attacks (L0/L1)
======================================
Jacobian-based Saliency Map Attack — modifies few pixels with high impact.
Also includes L1-PGD and ElasticNet (EAD) attacks.

Usage:
    python jsma_sparse.py --attack jsma --target 3
    python jsma_sparse.py --attack ead --eps 0.3
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# JSMA (Papernot et al., 2016)
# ============================================================

def compute_jacobian(model, image, num_classes=10):
    """Compute the Jacobian matrix ∂F/∂x for all classes."""
    image = image.clone().detach().requires_grad_(True)
    output = model(image)

    jacobian = []
    for i in range(num_classes):
        if image.grad is not None:
            image.grad.zero_()
        output[0, i].backward(retain_graph=True)
        jacobian.append(image.grad.data.clone().flatten())

    return torch.stack(jacobian)  # shape: (num_classes, num_features)


def saliency_map(jacobian, target_class, search_space):
    """
    Compute saliency map to find most impactful pixel pairs.

    For each feature i:
        - α_t(i) = ∂F_t/∂x_i  (gradient for target class)
        - α_o(i) = Σ_{j≠t} ∂F_j/∂x_i  (sum of gradients for other classes)

    Saliency S(i) = α_t(i) * |α_o(i)| if α_t > 0 and α_o < 0, else 0
    """
    alpha_target = jacobian[target_class]  # ∂F_target/∂x
    alpha_other = jacobian.sum(dim=0) - alpha_target  # Σ ∂F_other/∂x

    # Conditions: increase target, decrease others
    mask_increase = (alpha_target > 0) & (alpha_other < 0) & search_space

    saliency = torch.zeros_like(alpha_target)
    saliency[mask_increase] = alpha_target[mask_increase] * alpha_other[mask_increase].abs()

    return saliency


def jsma_attack(model, image, target_class, num_classes=10, max_pixels=None,
                theta=1.0, clip_min=0.0, clip_max=1.0):
    """
    JSMA: iteratively modifies the most salient pixel toward target class.

    Args:
        theta: perturbation step size per pixel
        max_pixels: max number of pixels to modify (default: 10% of image)
    """
    model.eval()
    image = image.clone().detach().to(DEVICE).unsqueeze(0) if image.dim() == 3 else image.clone().detach().to(DEVICE)

    num_features = image[0].numel()
    if max_pixels is None:
        max_pixels = int(num_features * 0.10)

    adv_image = image.clone()
    search_space = torch.ones(num_features, dtype=torch.bool, device=DEVICE)

    pixels_changed = 0

    with torch.no_grad():
        pred = model(adv_image).argmax(1).item()

    while pred != target_class and pixels_changed < max_pixels:
        jacobian = compute_jacobian(model, adv_image, num_classes)
        smap = saliency_map(jacobian, target_class, search_space)

        if smap.max() == 0:
            break

        # Select pixel with highest saliency
        best_pixel = smap.argmax().item()

        # Modify pixel
        flat = adv_image.view(-1)
        if theta > 0:
            flat[best_pixel] = min(flat[best_pixel] + theta, clip_max)
        else:
            flat[best_pixel] = max(flat[best_pixel] + theta, clip_min)

        # Remove pixel from search space if it hit the boundary
        if flat[best_pixel] >= clip_max or flat[best_pixel] <= clip_min:
            search_space[best_pixel] = False

        adv_image = flat.view(image.shape)
        pixels_changed += 1

        with torch.no_grad():
            pred = model(adv_image).argmax(1).item()

    return adv_image.detach().squeeze(0), pixels_changed, pred


# ============================================================
# EAD - Elastic-net Attack (Chen et al., 2018)
# ============================================================

def ead_attack(model, images, labels, target_labels=None,
               c=1.0, kappa=0, steps=100, lr=0.01,
               beta=1e-3, targeted=False):
    """
    ElasticNet Attack to DNNs (EAD).
    Combines L1 and L2 penalties: min ||δ||_2^2 + β||δ||_1 + c·f(x+δ)

    Produces sparse perturbations (few pixels changed).
    """
    images = images.to(DEVICE)
    labels = labels.to(DEVICE)
    batch_size = images.size(0)

    # Initialize with tanh space
    w = torch.zeros_like(images, requires_grad=True)
    optimizer = torch.optim.Adam([w], lr=lr)

    best_adv = images.clone()
    best_l1 = torch.full((batch_size,), float("inf"), device=DEVICE)

    for step in range(steps):
        adv_images = torch.clamp(images + w, 0, 1)
        outputs = model(adv_images)

        # f(x') function (C&W style)
        one_hot = F.one_hot(labels if not targeted else target_labels,
                            num_classes=outputs.size(1)).float()
        real = (one_hot * outputs).sum(dim=1)
        other = ((1 - one_hot) * outputs - one_hot * 1e4).max(dim=1)[0]

        if targeted:
            f_loss = torch.clamp(other - real + kappa, min=0)
        else:
            f_loss = torch.clamp(real - other + kappa, min=0)

        # ElasticNet regularization
        perturbation = adv_images - images
        l2_loss = perturbation.view(batch_size, -1).pow(2).sum(dim=1)
        l1_loss = perturbation.view(batch_size, -1).abs().sum(dim=1)

        total_loss = l2_loss.sum() + c * f_loss.sum() + beta * l1_loss.sum()

        optimizer.zero_grad()
        total_loss.backward()
        optimizer.step()

        # Track best adversarial examples
        with torch.no_grad():
            preds = model(adv_images).argmax(1)
            if targeted:
                success = (preds == target_labels)
            else:
                success = (preds != labels)

            current_l1 = l1_loss
            improved = success & (current_l1 < best_l1)
            best_adv[improved] = adv_images[improved].clone()
            best_l1[improved] = current_l1[improved]

    return best_adv.detach()


# ============================================================
# L1-PGD Attack
# ============================================================

def l1_pgd_attack(model, images, labels, eps=10.0, alpha=1.0, steps=40,
                  targeted=False, target_labels=None):
    """
    PGD with L1 norm projection.
    Produces sparse perturbations by projecting onto L1 ball.
    """
    images = images.to(DEVICE)
    labels = labels.to(DEVICE)
    adv_images = images.clone().detach()

    for _ in range(steps):
        adv_images.requires_grad_(True)
        outputs = model(adv_images)

        if targeted and target_labels is not None:
            loss = F.cross_entropy(outputs, target_labels.to(DEVICE))
            loss = -loss
        else:
            loss = F.cross_entropy(outputs, labels)

        model.zero_grad()
        loss.backward()

        grad = adv_images.grad.data

        # Steepest ascent for L1: modify only the coordinate with largest gradient
        abs_grad = grad.abs().view(grad.size(0), -1)
        max_idx = abs_grad.argmax(dim=1)

        update = torch.zeros_like(grad.view(grad.size(0), -1))
        for i in range(grad.size(0)):
            update[i, max_idx[i]] = alpha * grad.view(grad.size(0), -1)[i, max_idx[i]].sign()
        update = update.view(grad.shape)

        adv_images = adv_images.detach() + update

        # Project onto L1 ball
        perturbation = adv_images - images
        pert_flat = perturbation.view(perturbation.size(0), -1)
        l1_norms = pert_flat.abs().sum(dim=1, keepdim=True)
        factor = torch.clamp(eps / (l1_norms + 1e-8), max=1.0)
        perturbation = (pert_flat * factor).view(perturbation.shape)

        adv_images = torch.clamp(images + perturbation, 0, 1)

    return adv_images.detach()


# ============================================================
# TORCHATTACKS WRAPPERS
# ============================================================

def torchattacks_jsma(model, images, labels, target_labels, **kwargs):
    """Wrapper for torchattacks JSMA."""
    import torchattacks
    atk = torchattacks.JSMA(model, **kwargs)
    atk.set_mode_targeted_by_label()
    return atk(images, target_labels)


def torchattacks_cw(model, images, labels, c=1, kappa=0, steps=100, lr=0.01):
    """Wrapper for torchattacks C&W L2 attack."""
    import torchattacks
    atk = torchattacks.CW(model, c=c, kappa=kappa, steps=steps, lr=lr)
    return atk(images, labels)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attack", choices=["jsma", "ead", "l1pgd", "cw"], default="jsma")
    parser.add_argument("--target", type=int, default=3)
    parser.add_argument("--eps", type=float, default=10.0)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    import torchvision
    import torchvision.transforms as transforms

    testset = torchvision.datasets.MNIST(
        root="./data", train=False, download=True,
        transform=transforms.ToTensor()
    )
    testloader = torch.utils.data.DataLoader(
        testset, batch_size=args.batch_size, shuffle=True
    )

    class CNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 32, 3, 1)
            self.conv2 = nn.Conv2d(32, 64, 3, 1)
            self.fc1 = nn.Linear(9216, 128)
            self.fc2 = nn.Linear(128, 10)

        def forward(self, x):
            x = F.relu(self.conv1(x))
            x = F.relu(self.conv2(x))
            x = F.max_pool2d(x, 2)
            x = torch.flatten(x, 1)
            x = F.relu(self.fc1(x))
            return self.fc2(x)

    model = CNN().to(DEVICE).eval()
    images, labels = next(iter(testloader))

    print(f"[*] Attack: {args.attack} | Target: {args.target}")

    if args.attack == "jsma":
        results = []
        for i in range(images.size(0)):
            adv, n_pix, pred = jsma_attack(model, images[i], args.target)
            results.append((adv, n_pix, pred))
            print(f"  Image {i}: {labels[i].item()} → {pred} ({n_pix} pixels changed)")
    elif args.attack == "ead":
        target_labels = torch.full_like(labels, args.target)
        adv = ead_attack(model, images, labels, target_labels=target_labels,
                         targeted=True, steps=args.steps)
        preds = model(adv.to(DEVICE)).argmax(1)
        success = (preds == target_labels.to(DEVICE)).sum().item()
        print(f"  Success: {success}/{len(labels)}")
    elif args.attack == "l1pgd":
        adv = l1_pgd_attack(model, images, labels, eps=args.eps, steps=args.steps)
        preds = model(adv).argmax(1)
        fooled = (preds != labels.to(DEVICE)).sum().item()
        print(f"  Fooled: {fooled}/{len(labels)}")
    elif args.attack == "cw":
        adv = torchattacks_cw(model, images, labels, steps=args.steps)
        preds = model(adv.to(DEVICE)).argmax(1)
        fooled = (preds != labels.to(DEVICE)).sum().item()
        print(f"  Fooled: {fooled}/{len(labels)}")
