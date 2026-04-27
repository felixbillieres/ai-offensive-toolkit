#!/usr/bin/env python3
"""
DeepFool Attack Implementation
===============================
Finds the minimal perturbation to cross the nearest decision boundary.
Produces smaller perturbations than FGSM/PGD.

Usage:
    python deepfool.py
    python deepfool.py --max-iter 100 --num-classes 10
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt
from copy import deepcopy

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def deepfool_single(model, image, num_classes=10, max_iter=50, overshoot=0.02):
    """
    DeepFool for a single image (Moosavi-Dezfooli et al., 2016).

    Algorithm:
    1. Compute gradients for all classes
    2. Find closest decision boundary
    3. Take minimal step to cross it
    4. Repeat until misclassification

    Returns:
        r_total: total perturbation
        adv_image: perturbed image
        k_i: adversarial class
        loop_i: number of iterations used
    """
    model.eval()
    image = image.clone().detach().to(DEVICE).unsqueeze(0) if image.dim() == 3 else image.clone().detach().to(DEVICE)
    image.requires_grad_(True)

    output = model(image)
    _, k_0 = output.max(1)
    k_0 = k_0.item()

    I = output.argsort(descending=True)[0, :num_classes].detach()

    x = image.clone().detach()
    r_total = torch.zeros_like(image)

    loop_i = 0
    k_i = k_0

    while k_i == k_0 and loop_i < max_iter:
        x.requires_grad_(True)
        output = model(x)

        # Gradient of the original class
        output[0, I[0]].backward(retain_graph=True)
        grad_orig = x.grad.data.clone()
        x.grad.zero_()

        pert = float("inf")
        w_best = None

        for k in range(1, num_classes):
            x.requires_grad_(True)
            if x.grad is not None:
                x.grad.zero_()

            output[0, I[k]].backward(retain_graph=True)
            grad_k = x.grad.data.clone()
            x.grad.zero_()

            w_k = grad_k - grad_orig
            f_k = (output[0, I[k]] - output[0, I[0]]).item()

            w_k_flat = w_k.flatten()
            pert_k = abs(f_k) / (w_k_flat.norm() + 1e-8)

            if pert_k < pert:
                pert = pert_k
                w_best = w_k.clone()

        # Minimal perturbation
        r_i = (pert + 1e-4) * w_best / (w_best.flatten().norm() + 1e-8)
        r_total += r_i

        x = torch.clamp(image + (1 + overshoot) * r_total, 0, 1).detach()

        with torch.no_grad():
            k_i = model(x).argmax(1).item()

        loop_i += 1

    adv_image = torch.clamp(image + (1 + overshoot) * r_total, 0, 1)
    return r_total.detach(), adv_image.detach().squeeze(0), k_i, loop_i


def deepfool_batch(model, images, labels, num_classes=10, max_iter=50, overshoot=0.02):
    """Apply DeepFool to a batch of images."""
    adv_images = []
    perturbations = []
    adv_labels = []

    for i in range(images.size(0)):
        r, adv_img, k_i, iters = deepfool_single(
            model, images[i], num_classes, max_iter, overshoot
        )
        adv_images.append(adv_img)
        perturbations.append(r.squeeze(0))
        adv_labels.append(k_i)

    return (torch.stack(adv_images), torch.stack(perturbations),
            torch.tensor(adv_labels))


def deepfool_torchattacks(model, images, labels, steps=50, overshoot=0.02):
    """Use torchattacks DeepFool if available."""
    import torchattacks
    atk = torchattacks.DeepFool(model, steps=steps, overshoot=overshoot)
    return atk(images, labels)


def evaluate_and_visualize(model, images, adv_images, labels, adv_labels, n=5):
    """Show results of DeepFool attack."""
    print(f"\n{'='*50}")
    print(f"DeepFool Attack Results")
    print(f"{'='*50}")

    model.eval()
    with torch.no_grad():
        clean_preds = model(images.to(DEVICE)).argmax(1).cpu()

    clean_correct = (clean_preds == labels).sum().item()
    adv_fooled = (adv_labels != labels).sum().item()

    perturbation = (adv_images - images).view(images.size(0), -1)
    l2_norms = perturbation.norm(p=2, dim=1)

    print(f"Clean accuracy: {clean_correct}/{len(labels)}")
    print(f"Fooled: {adv_fooled}/{len(labels)} ({adv_fooled/len(labels)*100:.1f}%)")
    print(f"Mean L2 perturbation: {l2_norms.mean():.4f}")
    print(f"Max L2 perturbation: {l2_norms.max():.4f}")

    fig, axes = plt.subplots(2, n, figsize=(n*3, 6))
    for i in range(min(n, images.size(0))):
        img = images[i].cpu().permute(1, 2, 0).numpy().squeeze()
        axes[0, i].imshow(img, cmap="gray")
        axes[0, i].set_title(f"True: {labels[i].item()}")
        axes[0, i].axis("off")

        adv = adv_images[i].cpu().permute(1, 2, 0).numpy().squeeze()
        axes[1, i].imshow(adv, cmap="gray")
        axes[1, i].set_title(f"Adv: {adv_labels[i].item()}")
        axes[1, i].axis("off")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepFool Attack")
    parser.add_argument("--max-iter", type=int, default=50)
    parser.add_argument("--num-classes", type=int, default=10)
    parser.add_argument("--overshoot", type=float, default=0.02)
    parser.add_argument("--batch-size", type=int, default=16)
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

    # Simple model
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

    model = CNN().to(DEVICE)
    model.eval()

    images, labels = next(iter(testloader))
    adv_images, perturbations, adv_labels = deepfool_batch(
        model, images, labels, args.num_classes, args.max_iter, args.overshoot
    )

    evaluate_and_visualize(model, images, adv_images, labels, adv_labels)
