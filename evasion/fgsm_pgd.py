#!/usr/bin/env python3
"""
FGSM, I-FGSM, and PGD Evasion Attacks
======================================
Gradient-based Lp attacks on image classifiers.

Supports:
  - Manual implementations (zero external dependencies beyond PyTorch)
  - torchattacks library wrappers for quick use
  - Custom model loading (.pt/.pth files)
  - Custom dataset loading (folder of images, .npz, or built-in datasets)
  - Targeted and untargeted modes
  - Linf and L2 norm constraints
  - Visualization and JSON export of results

Examples:
  # Attack a saved model with PGD
  python fgsm_pgd.py --attack pgd --eps 0.3 --model-path ./model.pt

  # FGSM on MNIST with visualization
  python fgsm_pgd.py --attack fgsm --eps 0.3 --dataset mnist --visualize

  # Targeted PGD-L2 attack forcing class 5
  python fgsm_pgd.py --attack pgd --norm L2 --eps 2.0 --targeted --target-class 5

  # Load config from JSON
  python fgsm_pgd.py --config attack_config.json

  # Use torchattacks backend
  python fgsm_pgd.py --attack pgd --eps 0.03 --backend torchattacks

Config JSON example:
  {
    "attack": "pgd",
    "eps": 0.031,
    "alpha": 0.008,
    "steps": 40,
    "norm": "Linf",
    "targeted": false,
    "dataset": "mnist",
    "batch_size": 64
  }
"""

import argparse
import json
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from pathlib import Path


# ============================================================
# DEVICE SETUP
# ============================================================

def get_device(force_cpu=False):
    if force_cpu:
        return torch.device("cpu")
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# ============================================================
# MANUAL IMPLEMENTATIONS (no external deps beyond PyTorch)
# ============================================================

def fgsm_attack(model, images, labels, eps, targeted=False, target_labels=None,
                loss_fn=None, device=None):
    """
    Fast Gradient Sign Method (Goodfellow et al., 2014).

    x_adv = x + eps * sign(nabla_x L(theta, x, y))
    For targeted: x_adv = x - eps * sign(nabla_x L(theta, x, y_target))

    Args:
        model: PyTorch classifier (must output logits)
        images: input tensor [N, C, H, W] in [0, 1]
        labels: true labels [N]
        eps: perturbation budget (Linf)
        targeted: if True, minimize loss for target_labels
        target_labels: target class labels for targeted attack [N]
        loss_fn: loss function (default: CrossEntropyLoss)
        device: torch device

    Returns:
        Adversarial images tensor [N, C, H, W]
    """
    dev = device or next(model.parameters()).device
    loss_fn = loss_fn or F.cross_entropy

    images = images.clone().detach().to(dev).requires_grad_(True)
    labels = labels.clone().detach().to(dev)

    outputs = model(images)
    if targeted and target_labels is not None:
        loss = loss_fn(outputs, target_labels.to(dev))
    else:
        loss = loss_fn(outputs, labels)

    model.zero_grad()
    loss.backward()

    grad_sign = images.grad.data.sign()
    if targeted:
        adv_images = images - eps * grad_sign
    else:
        adv_images = images + eps * grad_sign

    return torch.clamp(adv_images, 0, 1).detach()


def ifgsm_attack(model, images, labels, eps, alpha=None, steps=10,
                 targeted=False, target_labels=None, loss_fn=None, device=None):
    """
    Iterative FGSM / BIM (Kurakin et al., 2016).
    Applies FGSM iteratively with step size alpha.

    Args:
        alpha: step size per iteration (default: eps/steps)
        steps: number of iterations
    """
    dev = device or next(model.parameters()).device
    loss_fn = loss_fn or F.cross_entropy
    if alpha is None:
        alpha = eps / steps

    adv_images = images.clone().detach().to(dev)
    labels = labels.to(dev)

    for _ in range(steps):
        adv_images.requires_grad_(True)
        outputs = model(adv_images)
        if targeted and target_labels is not None:
            loss = loss_fn(outputs, target_labels.to(dev))
        else:
            loss = loss_fn(outputs, labels)

        model.zero_grad()
        loss.backward()
        grad_sign = adv_images.grad.data.sign()

        if targeted:
            adv_images = adv_images.detach() - alpha * grad_sign
        else:
            adv_images = adv_images.detach() + alpha * grad_sign

        perturbation = torch.clamp(adv_images - images.to(dev), -eps, eps)
        adv_images = torch.clamp(images.to(dev) + perturbation, 0, 1)

    return adv_images.detach()


def pgd_attack(model, images, labels, eps, alpha=None, steps=40,
               random_start=True, targeted=False, target_labels=None,
               norm="Linf", loss_fn=None, device=None, restarts=1):
    """
    Projected Gradient Descent (Madry et al., 2017).
    Gold standard white-box Linf/L2 attack.

    Args:
        alpha: step size (default: heuristic based on eps/steps)
        steps: number of PGD iterations
        random_start: initialize with random perturbation in eps-ball
        norm: "Linf" or "L2"
        restarts: number of random restarts (keep best)

    Returns:
        Adversarial images tensor [N, C, H, W]
    """
    dev = device or next(model.parameters()).device
    loss_fn = loss_fn or F.cross_entropy

    if alpha is None:
        alpha = eps / steps * 2.5

    images = images.to(dev)
    labels = labels.to(dev)

    best_adv = images.clone()
    best_loss = torch.full((images.size(0),), -float("inf"), device=dev)

    for _ in range(restarts):
        adv_images = images.clone().detach()

        if random_start:
            if norm == "Linf":
                adv_images += torch.empty_like(adv_images).uniform_(-eps, eps)
            elif norm == "L2":
                noise = torch.randn_like(adv_images)
                noise_flat = noise.view(noise.size(0), -1)
                noise = noise / (noise_flat.norm(dim=1, keepdim=True).view(-1, 1, 1, 1) + 1e-8) * eps
                adv_images += noise
            adv_images = torch.clamp(adv_images, 0, 1)

        for _ in range(steps):
            adv_images.requires_grad_(True)
            outputs = model(adv_images)
            if targeted and target_labels is not None:
                loss = loss_fn(outputs, target_labels.to(dev))
            else:
                loss = loss_fn(outputs, labels)

            model.zero_grad()
            loss.backward()

            if norm == "Linf":
                grad_sign = adv_images.grad.data.sign()
                if targeted:
                    adv_images = adv_images.detach() - alpha * grad_sign
                else:
                    adv_images = adv_images.detach() + alpha * grad_sign
                perturbation = torch.clamp(adv_images - images, -eps, eps)
                adv_images = torch.clamp(images + perturbation, 0, 1)

            elif norm == "L2":
                grad = adv_images.grad.data
                grad_norm = grad.view(grad.size(0), -1).norm(dim=1, keepdim=True)
                grad_normalized = grad / (grad_norm.view(-1, 1, 1, 1) + 1e-8)
                if targeted:
                    adv_images = adv_images.detach() - alpha * grad_normalized
                else:
                    adv_images = adv_images.detach() + alpha * grad_normalized
                perturbation = adv_images - images
                pert_norm = perturbation.view(perturbation.size(0), -1).norm(dim=1, keepdim=True)
                factor = torch.min(torch.ones_like(pert_norm), eps / (pert_norm + 1e-8))
                perturbation = perturbation * factor.view(-1, 1, 1, 1)
                adv_images = torch.clamp(images + perturbation, 0, 1)

        # Track best adversarial per restart
        with torch.no_grad():
            outputs = model(adv_images)
            if targeted and target_labels is not None:
                per_sample_loss = -F.cross_entropy(outputs, target_labels.to(dev), reduction="none")
            else:
                per_sample_loss = F.cross_entropy(outputs, labels, reduction="none")
            improved = per_sample_loss > best_loss
            best_adv[improved] = adv_images[improved]
            best_loss[improved] = per_sample_loss[improved]

    return best_adv.detach()


# ============================================================
# TORCHATTACKS WRAPPERS
# ============================================================

def torchattacks_attack(model, images, labels, attack_name="fgsm", eps=0.3,
                        alpha=None, steps=40, targeted=False, target_labels=None,
                        norm="Linf"):
    """Wrapper using torchattacks library for quick attacks."""
    try:
        import torchattacks
    except ImportError:
        print("Error: torchattacks not installed. Install with: pip install torchattacks")
        print("Falling back to manual implementation...")
        fn_map = {"fgsm": fgsm_attack, "ifgsm": ifgsm_attack,
                  "pgd": pgd_attack, "pgd_l2": pgd_attack}
        kwargs = {"model": model, "images": images, "labels": labels, "eps": eps,
                  "targeted": targeted, "target_labels": target_labels}
        if attack_name != "fgsm":
            kwargs.update({"alpha": alpha, "steps": steps})
        if attack_name == "pgd_l2":
            kwargs["norm"] = "L2"
        return fn_map.get(attack_name, pgd_attack)(**kwargs)

    atk_map = {
        "fgsm": lambda: torchattacks.FGSM(model, eps=eps),
        "ifgsm": lambda: torchattacks.BIM(model, eps=eps,
                                           alpha=alpha or eps / steps,
                                           steps=steps),
        "pgd": lambda: torchattacks.PGD(model, eps=eps,
                                         alpha=alpha or eps / steps * 2.5,
                                         steps=steps, random_start=True),
        "pgd_l2": lambda: torchattacks.PGDL2(model, eps=eps,
                                               alpha=alpha or eps / steps * 2.5,
                                               steps=steps),
        "mifgsm": lambda: torchattacks.MIFGSM(model, eps=eps, steps=steps),
        "autopgd": lambda: torchattacks.APGD(model, eps=eps, steps=steps),
    }

    if attack_name not in atk_map:
        raise ValueError(f"Unknown attack: {attack_name}. Available: {list(atk_map.keys())}")

    atk = atk_map[attack_name]()
    if targeted:
        atk.set_mode_targeted_by_label()
        if target_labels is not None:
            return atk(images, target_labels)
    return atk(images, labels)


# ============================================================
# EVALUATION
# ============================================================

def evaluate_attack(model, original_images, adv_images, labels, device=None, quiet=False):
    """
    Compute attack success metrics.

    Returns dict with: clean_acc, adv_acc, success_rate, l2_norm, linf_norm, adv_preds
    """
    dev = device or next(model.parameters()).device
    model.eval()
    with torch.no_grad():
        orig_preds = model(original_images.to(dev)).argmax(dim=1)
        adv_preds = model(adv_images.to(dev)).argmax(dim=1)

    labels_dev = labels.to(dev)
    clean_acc = (orig_preds == labels_dev).float().mean().item()
    adv_acc = (adv_preds == labels_dev).float().mean().item()
    attack_success = (orig_preds == labels_dev) & (adv_preds != labels_dev)
    success_rate = attack_success.float().mean().item()

    perturbation = (adv_images - original_images.to(dev)).view(adv_images.size(0), -1)
    l2_norm = perturbation.norm(p=2, dim=1).mean().item()
    linf_norm = perturbation.abs().max(dim=1)[0].mean().item()

    if not quiet:
        print(f"  Clean accuracy:       {clean_acc*100:.1f}%")
        print(f"  Adversarial accuracy: {adv_acc*100:.1f}%")
        print(f"  Attack success rate:  {success_rate*100:.1f}%")
        print(f"  Mean L2 perturbation:   {l2_norm:.4f}")
        print(f"  Mean Linf perturbation: {linf_norm:.4f}")

    return {
        "clean_acc": clean_acc, "adv_acc": adv_acc,
        "success_rate": success_rate,
        "l2_norm": l2_norm, "linf_norm": linf_norm,
        "adv_preds": adv_preds.cpu()
    }


def visualize_attack(original, adversarial, labels, preds, n=5, save_path=None):
    """Side-by-side visualization of clean vs adversarial images."""
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, n, figsize=(n * 3, 9))

    for i in range(min(n, original.size(0))):
        img = original[i].cpu().permute(1, 2, 0).numpy()
        if img.shape[2] == 1:
            img = img.squeeze(-1)
        axes[0, i].imshow(img, cmap="gray" if img.ndim == 2 else None)
        axes[0, i].set_title(f"Clean: {labels[i].item()}")
        axes[0, i].axis("off")

        adv = adversarial[i].cpu().permute(1, 2, 0).numpy()
        if adv.shape[2] == 1:
            adv = adv.squeeze(-1)
        axes[1, i].imshow(adv, cmap="gray" if adv.ndim == 2 else None)
        axes[1, i].set_title(f"Adv: {preds[i].item()}")
        axes[1, i].axis("off")

        diff = (adversarial[i] - original[i]).cpu().permute(1, 2, 0).numpy()
        diff = (diff - diff.min()) / (diff.max() - diff.min() + 1e-8)
        if diff.shape[2] == 1:
            diff = diff.squeeze(-1)
        axes[2, i].imshow(diff, cmap="hot" if diff.ndim == 2 else None)
        axes[2, i].set_title("Perturbation")
        axes[2, i].axis("off")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Plot saved to {save_path}")
    else:
        plt.show()


# ============================================================
# DATA & MODEL LOADING
# ============================================================

def load_dataset(name="mnist", batch_size=64, data_dir="./data"):
    """Load a dataset for testing. Supports: mnist, cifar10, cifar100, fashion_mnist."""
    import torchvision
    import torchvision.transforms as transforms

    transform = transforms.ToTensor()

    datasets = {
        "mnist": torchvision.datasets.MNIST,
        "fashion_mnist": torchvision.datasets.FashionMNIST,
        "cifar10": torchvision.datasets.CIFAR10,
        "cifar100": torchvision.datasets.CIFAR100,
    }

    if name not in datasets:
        raise ValueError(f"Unknown dataset: {name}. Available: {list(datasets.keys())}")

    testset = datasets[name](root=data_dir, train=False, download=True, transform=transform)
    return torch.utils.data.DataLoader(testset, batch_size=batch_size, shuffle=False)


def load_custom_model(model_path, model_class=None, device="cpu"):
    """
    Load a saved PyTorch model.

    Supports:
      - State dict (.pt/.pth with state_dict)
      - Full model (torch.save(model, path))
      - TorchScript (.pt)
    """
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    try:
        model = torch.jit.load(str(path), map_location=device)
        print(f"  Loaded TorchScript model from {path}")
        return model
    except Exception:
        pass

    checkpoint = torch.load(str(path), map_location=device, weights_only=False)

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        if model_class is None:
            raise ValueError("Need --model-class to load state_dict checkpoint")
        model = model_class()
        model.load_state_dict(checkpoint["model_state_dict"])
    elif isinstance(checkpoint, dict) and all(isinstance(v, torch.Tensor) for v in checkpoint.values()):
        if model_class is None:
            raise ValueError("Need --model-class to load state_dict")
        model = model_class()
        model.load_state_dict(checkpoint)
    elif isinstance(checkpoint, nn.Module):
        model = checkpoint
    else:
        raise ValueError(f"Cannot determine model format in {path}")

    return model.to(device).eval()


def get_default_model(dataset="mnist", device="cpu"):
    """Return a simple untrained CNN for demo purposes."""
    if dataset in ("mnist", "fashion_mnist"):
        in_channels, num_classes = 1, 10
    elif dataset == "cifar10":
        in_channels, num_classes = 3, 10
    elif dataset == "cifar100":
        in_channels, num_classes = 3, 100
    else:
        in_channels, num_classes = 1, 10

    class SimpleCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(in_channels, 32, 3, 1)
            self.conv2 = nn.Conv2d(32, 64, 3, 1)
            self.fc1 = nn.Linear(64 * (5 if in_channels == 1 else 6) ** 2, 128)
            self.fc2 = nn.Linear(128, num_classes)

        def forward(self, x):
            x = F.relu(self.conv1(x))
            x = F.relu(self.conv2(x))
            x = F.max_pool2d(x, 2)
            x = torch.flatten(x, 1)
            x = F.relu(self.fc1(x))
            return self.fc2(x)

    return SimpleCNN().to(device)


# ============================================================
# CLI
# ============================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description="FGSM / I-FGSM / PGD Evasion Attacks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --attack fgsm --eps 0.3 --dataset mnist
  %(prog)s --attack pgd --eps 0.031 --steps 40 --norm Linf
  %(prog)s --attack pgd --norm L2 --eps 2.0 --targeted --target-class 5
  %(prog)s --attack pgd --eps 0.3 --model-path ./my_model.pt
  %(prog)s --config attack_config.json
  %(prog)s --backend torchattacks --attack autopgd --eps 0.031
        """
    )

    # Attack parameters
    atk = parser.add_argument_group("Attack parameters")
    atk.add_argument("--attack", choices=["fgsm", "ifgsm", "pgd", "pgd_l2", "mifgsm", "autopgd"],
                     default="pgd", help="Attack algorithm (default: pgd)")
    atk.add_argument("--eps", type=float, default=0.3,
                     help="Perturbation budget epsilon (default: 0.3)")
    atk.add_argument("--alpha", type=float, default=None,
                     help="Step size per iteration (default: auto)")
    atk.add_argument("--steps", type=int, default=40,
                     help="Number of attack iterations (default: 40)")
    atk.add_argument("--norm", choices=["Linf", "L2"], default="Linf",
                     help="Norm constraint (default: Linf)")
    atk.add_argument("--restarts", type=int, default=1,
                     help="Number of random restarts for PGD (default: 1)")

    # Targeting
    tgt = parser.add_argument_group("Targeting")
    tgt.add_argument("--targeted", action="store_true",
                     help="Run targeted attack (force misclassification to target-class)")
    tgt.add_argument("--target-class", type=int, default=0,
                     help="Target class for targeted attack (default: 0)")

    # Model
    mdl = parser.add_argument_group("Model")
    mdl.add_argument("--model-path", type=str, default=None,
                     help="Path to saved model (.pt/.pth/.jit)")
    mdl.add_argument("--dataset", type=str, default="mnist",
                     choices=["mnist", "fashion_mnist", "cifar10", "cifar100"],
                     help="Dataset to use (default: mnist)")

    # Backend
    bk = parser.add_argument_group("Backend")
    bk.add_argument("--backend", choices=["manual", "torchattacks"], default="manual",
                    help="Implementation backend (default: manual)")

    # Output
    out = parser.add_argument_group("Output")
    out.add_argument("--visualize", action="store_true",
                     help="Show side-by-side visualization")
    out.add_argument("--save-plot", type=str, default=None,
                     help="Save visualization to file")
    out.add_argument("--save-adv", type=str, default=None,
                     help="Save adversarial images as .pt file")
    out.add_argument("--output-json", type=str, default=None,
                     help="Export results to JSON")
    out.add_argument("--quiet", action="store_true",
                     help="Suppress progress output")

    # Misc
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Batch size for data loading (default: 64)")
    parser.add_argument("--num-samples", type=int, default=None,
                        help="Limit number of test samples")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU execution")
    parser.add_argument("--config", type=str, default=None,
                        help="Load parameters from JSON config file")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Load config from JSON if provided
    if args.config:
        with open(args.config) as f:
            config = json.load(f)
        for key, value in config.items():
            if hasattr(args, key):
                setattr(args, key, value)

    # Setup
    torch.manual_seed(args.seed)
    device = get_device(force_cpu=args.cpu)

    if not args.quiet:
        print(f"[*] Device: {device}")
        print(f"[*] Attack: {args.attack} | eps={args.eps} | steps={args.steps} | norm={args.norm}")
        if args.targeted:
            print(f"[*] Targeted → class {args.target_class}")

    # Load model
    if args.model_path:
        model = load_custom_model(args.model_path, device=device)
    else:
        model = get_default_model(args.dataset, device)
    model.eval()

    # Load data
    testloader = load_dataset(args.dataset, args.batch_size)
    images, labels = next(iter(testloader))
    if args.num_samples:
        images = images[:args.num_samples]
        labels = labels[:args.num_samples]

    target_labels = torch.full_like(labels, args.target_class) if args.targeted else None

    # Run attack
    if args.backend == "torchattacks":
        adv_images = torchattacks_attack(
            model, images, labels, attack_name=args.attack,
            eps=args.eps, alpha=args.alpha, steps=args.steps,
            targeted=args.targeted, target_labels=target_labels,
            norm=args.norm
        )
    else:
        attack_fn_map = {
            "fgsm": fgsm_attack,
            "ifgsm": ifgsm_attack,
            "pgd": pgd_attack,
            "pgd_l2": pgd_attack,
            "mifgsm": ifgsm_attack,
            "autopgd": pgd_attack,
        }
        fn = attack_fn_map[args.attack]
        kwargs = {
            "model": model, "images": images, "labels": labels,
            "eps": args.eps, "targeted": args.targeted,
            "target_labels": target_labels, "device": device,
        }
        if args.attack != "fgsm":
            kwargs.update({"alpha": args.alpha, "steps": args.steps})
        if args.attack in ("pgd", "pgd_l2", "autopgd"):
            kwargs["norm"] = "L2" if args.attack == "pgd_l2" else args.norm
            kwargs["restarts"] = args.restarts
        adv_images = fn(**kwargs)

    # Evaluate
    results = evaluate_attack(model, images, adv_images, labels, device, quiet=args.quiet)

    # Visualize
    if args.visualize or args.save_plot:
        visualize_attack(images, adv_images, labels, results["adv_preds"],
                         save_path=args.save_plot)

    # Save adversarial images
    if args.save_adv:
        torch.save({"adv_images": adv_images.cpu(), "labels": labels.cpu(),
                     "original_images": images.cpu()}, args.save_adv)
        if not args.quiet:
            print(f"  Adversarial images saved to {args.save_adv}")

    # Export JSON
    if args.output_json:
        export = {k: v for k, v in results.items() if k != "adv_preds"}
        export["config"] = {
            "attack": args.attack, "eps": args.eps, "alpha": args.alpha,
            "steps": args.steps, "norm": args.norm, "targeted": args.targeted,
            "backend": args.backend,
        }
        with open(args.output_json, "w") as f:
            json.dump(export, f, indent=2)
        if not args.quiet:
            print(f"  Results exported to {args.output_json}")


if __name__ == "__main__":
    main()
