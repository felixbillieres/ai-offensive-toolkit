#!/usr/bin/env python3
"""
Black-Box Evasion Attacks
=========================
Attacks that don't require gradient access to the target model.

Techniques:
- Score-based: Use confidence scores to estimate gradients
- Transfer-based: Generate adversarials on surrogate, transfer to target
- Query-based: Use only label outputs

Usage:
    python blackbox_evasion.py --attack transfer
    python blackbox_evasion.py --attack score --queries 1000
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# TRANSFER-BASED ATTACK
# ============================================================

def transfer_attack(surrogate_model, target_model, images, labels,
                    attack_fn, **attack_kwargs):
    """
    Generate adversarial examples on surrogate model,
    then test transferability to target model.

    Strategy: Use a simpler model as surrogate, attack it,
    hope the adversarial examples also fool the target.
    """
    surrogate_model.eval()
    target_model.eval()

    # Generate adversarial examples on surrogate
    adv_images = attack_fn(surrogate_model, images, labels, **attack_kwargs)

    # Evaluate on target
    with torch.no_grad():
        target_preds = target_model(adv_images.to(DEVICE)).argmax(1)
        surrogate_preds = surrogate_model(adv_images.to(DEVICE)).argmax(1)

    labels_dev = labels.to(DEVICE)
    surrogate_fooled = (surrogate_preds != labels_dev).sum().item()
    target_fooled = (target_preds != labels_dev).sum().item()

    print(f"Surrogate fooled: {surrogate_fooled}/{len(labels)}")
    print(f"Target fooled:    {target_fooled}/{len(labels)}")
    print(f"Transfer rate:    {target_fooled/max(surrogate_fooled,1)*100:.1f}%")

    return adv_images


# ============================================================
# SCORE-BASED (NES - Natural Evolution Strategy)
# ============================================================

def nes_gradient_estimate(model, images, labels, sigma=0.001, n_samples=100):
    """
    Estimate gradient using Natural Evolution Strategy.
    Uses model score outputs (softmax probabilities).

    ∇_x L ≈ (1/nσ) Σ L(x + σ·u_i) · u_i
    """
    batch_size = images.size(0)
    grad_estimate = torch.zeros_like(images)

    for _ in range(n_samples // 2):
        noise = torch.randn_like(images)

        with torch.no_grad():
            # Forward pass
            out_plus = model(torch.clamp(images + sigma * noise, 0, 1))
            loss_plus = F.cross_entropy(out_plus, labels, reduction="none")

            # Backward pass (antithetic sampling)
            out_minus = model(torch.clamp(images - sigma * noise, 0, 1))
            loss_minus = F.cross_entropy(out_minus, labels, reduction="none")

        diff = (loss_plus - loss_minus).view(-1, 1, 1, 1)
        grad_estimate += diff * noise

    return grad_estimate / (n_samples * sigma)


def score_based_attack(model, images, labels, eps=0.3, steps=40,
                       alpha=None, sigma=0.001, n_samples=100):
    """
    Score-based PGD using NES gradient estimation.
    Only needs model confidence scores, no gradients.
    """
    if alpha is None:
        alpha = eps / steps * 2.5

    images = images.to(DEVICE)
    labels = labels.to(DEVICE)
    adv_images = images.clone()

    for step in range(steps):
        grad = nes_gradient_estimate(model, adv_images, labels, sigma, n_samples)
        adv_images = adv_images + alpha * grad.sign()

        perturbation = torch.clamp(adv_images - images, -eps, eps)
        adv_images = torch.clamp(images + perturbation, 0, 1).detach()

        if step % 10 == 0:
            with torch.no_grad():
                preds = model(adv_images).argmax(1)
                fooled = (preds != labels).sum().item()
            print(f"  Step {step}: fooled {fooled}/{len(labels)}")

    return adv_images


# ============================================================
# BOUNDARY ATTACK (Decision-based)
# ============================================================

def boundary_attack(model, image, label, target_image=None,
                    max_queries=5000, init_delta=0.1, init_epsilon=0.1):
    """
    Boundary Attack (Brendel et al., 2018).
    Only needs hard labels (top-1 prediction).

    Starts from a misclassified image and walks along the decision boundary
    toward the original, maintaining misclassification.
    """
    model.eval()
    image = image.to(DEVICE).unsqueeze(0)

    # Initialize with random noise that's misclassified
    if target_image is not None:
        adv = target_image.to(DEVICE).unsqueeze(0)
    else:
        adv = torch.rand_like(image)
        for _ in range(1000):
            with torch.no_grad():
                pred = model(adv).argmax(1).item()
            if pred != label:
                break
            adv = torch.rand_like(image)

    queries = 0
    delta = init_delta
    epsilon = init_epsilon

    best_adv = adv.clone()
    best_dist = (adv - image).norm().item()

    while queries < max_queries:
        # Step 1: Move toward original (reduce perturbation)
        candidate = (1 - epsilon) * adv + epsilon * image

        # Step 2: Add orthogonal perturbation
        noise = torch.randn_like(image) * delta
        # Make noise orthogonal to (image - adv) direction
        direction = image - adv
        direction_flat = direction.flatten()
        noise_flat = noise.flatten()
        noise_flat -= (noise_flat @ direction_flat) / (direction_flat.norm()**2 + 1e-8) * direction_flat
        noise = noise_flat.view(noise.shape)

        candidate = torch.clamp(candidate + noise, 0, 1)

        with torch.no_grad():
            pred = model(candidate).argmax(1).item()
        queries += 1

        if pred != label:
            dist = (candidate - image).norm().item()
            if dist < best_dist:
                best_dist = dist
                best_adv = candidate.clone()
                adv = candidate
            delta *= 0.99
            epsilon = min(epsilon * 1.01, 0.5)
        else:
            delta *= 1.01
            epsilon *= 0.99

        if queries % 500 == 0:
            print(f"  Query {queries}: L2 dist = {best_dist:.4f}")

    return best_adv.squeeze(0).detach()


# ============================================================
# GOODWORD ATTACK (for text/NLP classifiers)
# ============================================================

def goodword_attack(predict_fn, text, word_list, max_insertions=5):
    """
    GoodWord attack for text classifiers.
    Insert benign words that flip the classifier's decision.

    Args:
        predict_fn: function(text) -> (label, confidence)
        text: input text string
        word_list: list of candidate "good words" to insert
        max_insertions: max words to add
    """
    original_label, original_conf = predict_fn(text)
    print(f"Original: label={original_label}, conf={original_conf:.3f}")

    best_text = text
    insertions = 0

    # Score each word
    word_scores = []
    for word in word_list:
        test_text = f"{word} {text}"
        label, conf = predict_fn(test_text)
        if label != original_label:
            return test_text, 1  # instant win
        # Lower conf = more disruption
        word_scores.append((word, conf))

    # Sort by most disruptive (lowest confidence for original class)
    word_scores.sort(key=lambda x: x[1])

    # Greedily insert best words
    current_text = text
    for word, _ in word_scores[:max_insertions]:
        candidate = f"{word} {current_text}"
        label, conf = predict_fn(candidate)
        if label != original_label:
            return candidate, insertions + 1
        if conf < original_conf:
            current_text = candidate
            insertions += 1
            original_conf = conf

    return current_text, insertions


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attack", choices=["transfer", "score", "boundary"],
                        default="score")
    parser.add_argument("--eps", type=float, default=0.3)
    parser.add_argument("--queries", type=int, default=1000)
    args = parser.parse_args()

    print(f"[*] Black-box attack: {args.attack}")
    print(f"[*] Device: {DEVICE}")
    print("[*] Run with actual models for real results")
