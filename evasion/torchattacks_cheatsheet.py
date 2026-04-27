#!/usr/bin/env python3
"""
torchattacks One-Liner Cheat Sheet
====================================
Quick reference for all attacks using the torchattacks library.

IMPORTANT: Images must be in [0, 1] range. If your model uses
normalization (e.g., ImageNet mean/std), wrap it:

    class NormalizedModel(nn.Module):
        def __init__(self, model, mean, std):
            super().__init__()
            self.model = model
            self.mean = torch.tensor(mean).view(1, -1, 1, 1)
            self.std = torch.tensor(std).view(1, -1, 1, 1)
        def forward(self, x):
            return self.model((x - self.mean.to(x.device)) / self.std.to(x.device))

Usage:
    pip install torchattacks
    python torchattacks_cheatsheet.py
"""

import torch

# ============================================================
# ALL ATTACKS — COPY-PASTE READY
# ============================================================

def run_all_attacks(model, images, labels):
    """Run every major attack in torchattacks. Returns dict of adv images."""
    import torchattacks

    results = {}

    # ---- Linf attacks ----
    # FGSM: single step, fast, weak
    atk = torchattacks.FGSM(model, eps=8/255)
    results["fgsm"] = atk(images, labels)

    # BIM / I-FGSM: iterative FGSM
    atk = torchattacks.BIM(model, eps=8/255, alpha=2/255, steps=10)
    results["bim"] = atk(images, labels)

    # PGD: gold standard white-box Linf
    atk = torchattacks.PGD(model, eps=8/255, alpha=2/255, steps=40, random_start=True)
    results["pgd"] = atk(images, labels)

    # MI-FGSM: momentum iterative
    atk = torchattacks.MIFGSM(model, eps=8/255, alpha=2/255, steps=10, decay=1.0)
    results["mifgsm"] = atk(images, labels)

    # AutoPGD: adaptive step size (strongest single attack)
    atk = torchattacks.APGD(model, eps=8/255, steps=100, n_restarts=1)
    results["autopgd"] = atk(images, labels)

    # ---- L2 attacks ----
    # PGD-L2
    atk = torchattacks.PGDL2(model, eps=1.0, alpha=0.2, steps=40)
    results["pgd_l2"] = atk(images, labels)

    # C&W: optimization-based, strongest L2
    atk = torchattacks.CW(model, c=1, kappa=0, steps=100, lr=0.01)
    results["cw"] = atk(images, labels)

    # DeepFool: minimal perturbation
    atk = torchattacks.DeepFool(model, steps=50, overshoot=0.02)
    results["deepfool"] = atk(images, labels)

    # ---- L0 / sparse attacks ----
    # JSMA: saliency map, modifies fewest pixels
    atk = torchattacks.JSMA(model, theta=1.0, gamma=0.1)
    results["jsma"] = atk(images, labels)

    # OnePixel: evolutionary, single pixel change
    atk = torchattacks.OnePixel(model, pixels=5, steps=75, popsize=400)
    results["onepixel"] = atk(images, labels)

    # SparseFool: sparse perturbation
    atk = torchattacks.SparseFool(model, steps=20, lam=3)
    results["sparsefool"] = atk(images, labels)

    # ---- Ensemble / composite ----
    # AutoAttack: combination of APGD-CE + APGD-DLR + FAB + Square
    atk = torchattacks.AutoAttack(model, eps=8/255, n_classes=10)
    results["autoattack"] = atk(images, labels)

    return results


# ============================================================
# TARGETED ATTACKS
# ============================================================

def targeted_attack(model, images, target_labels):
    """Run targeted PGD (force specific misclassification)."""
    import torchattacks

    atk = torchattacks.PGD(model, eps=8/255, alpha=2/255, steps=40)
    atk.set_mode_targeted_by_label()
    return atk(images, target_labels)


def targeted_cw(model, images, target_labels):
    """Targeted C&W L2 attack."""
    import torchattacks

    atk = torchattacks.CW(model, c=1, kappa=0, steps=200, lr=0.01)
    atk.set_mode_targeted_by_label()
    return atk(images, target_labels)


# ============================================================
# MULTI-ATTACK (try multiple, keep best)
# ============================================================

def multi_attack(model, images, labels):
    """Combine multiple attacks — keeps strongest adversarial per sample."""
    import torchattacks

    atk1 = torchattacks.PGD(model, eps=8/255, alpha=2/255, steps=20)
    atk2 = torchattacks.APGD(model, eps=8/255, steps=50)
    atk3 = torchattacks.DeepFool(model, steps=50)

    atk = torchattacks.MultiAttack([atk1, atk2, atk3])
    return atk(images, labels)


# ============================================================
# SAVE / LOAD ADVERSARIAL EXAMPLES
# ============================================================

def save_adversarials(atk, images, labels, path="./adv_data"):
    """Save adversarial examples to disk for later use."""
    atk.save(data_loader=[(images, labels)], save_path=path,
             verbose=True)


def load_adversarials(path="./adv_data"):
    """Load saved adversarial examples."""
    import torchattacks
    return torchattacks.load(load_path=path)


# ============================================================
# QUICK REFERENCE TABLE
# ============================================================

CHEATSHEET = """
╔══════════════╦══════╦═══════════╦══════════╦═══════════════════════════════════╗
║ Attack       ║ Norm ║ Speed     ║ Strength ║ Key params                        ║
╠══════════════╬══════╬═══════════╬══════════╬═══════════════════════════════════╣
║ FGSM         ║ Linf ║ Very fast ║ Weak     ║ eps=8/255                         ║
║ BIM/I-FGSM   ║ Linf ║ Fast      ║ Medium   ║ eps=8/255, alpha=2/255, steps=10  ║
║ PGD          ║ Linf ║ Medium    ║ Strong   ║ eps=8/255, alpha=2/255, steps=40  ║
║ MI-FGSM      ║ Linf ║ Medium    ║ Strong   ║ eps=8/255, decay=1.0              ║
║ AutoPGD      ║ Linf ║ Slow      ║ V.Strong ║ eps=8/255, steps=100              ║
║ PGD-L2       ║ L2   ║ Medium    ║ Strong   ║ eps=1.0, alpha=0.2                ║
║ C&W          ║ L2   ║ Slow      ║ V.Strong ║ c=1, kappa=0, steps=100           ║
║ DeepFool     ║ L2   ║ Medium    ║ Strong   ║ steps=50, overshoot=0.02          ║
║ JSMA         ║ L0   ║ Slow      ║ Medium   ║ theta=1.0, gamma=0.1             ║
║ OnePixel     ║ L0   ║ V.Slow    ║ Weak     ║ pixels=5, popsize=400             ║
║ SparseFool   ║ L0   ║ Medium    ║ Medium   ║ steps=20, lam=3                   ║
║ AutoAttack   ║ Linf ║ V.Slow    ║ Best     ║ eps=8/255 (benchmark standard)    ║
╚══════════════╩══════╩═══════════╩══════════╩═══════════════════════════════════╝

Standard epsilons:
  Linf: 8/255 ≈ 0.031 (CIFAR), 0.3 (MNIST)
  L2:   0.5 — 2.0
  L0:   1 — 10 pixels
"""

if __name__ == "__main__":
    print(CHEATSHEET)
    print("\nImport and use:\n")
    print("  import torchattacks")
    print("  atk = torchattacks.PGD(model, eps=8/255, alpha=2/255, steps=40)")
    print("  adv_images = atk(images, labels)")
    print("\n  # Targeted:")
    print("  atk.set_mode_targeted_by_label()")
    print("  adv_images = atk(images, target_labels)")
