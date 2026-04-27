# Adversarial Evasion Attacks

Evasion attacks manipulate inputs at inference time to cause misclassification while keeping perturbations imperceptible to humans. They are the most studied class of adversarial ML attacks.

## Theory

### The Core Idea

A classifier `f(x)` maps inputs to labels. An evasion attack finds a perturbation `δ` such that:

```
f(x + δ) ≠ f(x)    (untargeted)
f(x + δ) = t       (targeted, where t is the attacker's chosen class)
```

Subject to `||δ|| ≤ ε` — the perturbation must be small under some norm.

### Threat Models

| Model | Attacker knows | Realistic? |
|-------|---------------|------------|
| **White-box** | Architecture, weights, gradients | Research benchmark |
| **Black-box (score)** | Confidence scores only | API access scenarios |
| **Black-box (label)** | Top-1 label only | Most restricted |
| **Transfer** | Nothing about target; uses surrogate | Most realistic |

### Norm Constraints

The norm controls what "small" means for perturbations:

| Norm | Meaning | Visual effect | Typical ε |
|------|---------|---------------|-----------|
| **L∞** | Max change per pixel | Uniform noise | 8/255 (CIFAR), 0.3 (MNIST) |
| **L2** | Total Euclidean distance | Diffuse noise | 0.5 — 2.0 |
| **L1** | Sum of absolute changes | Sparse, concentrated | 5 — 20 |
| **L0** | Number of pixels changed | Few bright spots | 1 — 10 pixels |

### Attack Taxonomy

```
                    Evasion Attacks
                    ┌──────┴──────┐
               White-box       Black-box
               ┌───┴───┐       ┌───┴───┐
          Gradient   Optim   Transfer  Query
            │         │         │        │
          FGSM      C&W     Surrogate   NES
          PGD       EAD     + PGD     Boundary
        DeepFool              MI-FGSM  OnePixel
          JSMA
```

### Gradient-Based Attacks (First-Order)

**FGSM** — Fast Gradient Sign Method (Goodfellow et al., 2014)
Single step in the direction of the loss gradient sign:
```
x_adv = x + ε · sign(∇_x L(θ, x, y))
```
- Fast but weak. Good baseline.

**I-FGSM / BIM** — Basic Iterative Method (Kurakin et al., 2016)
Apply FGSM iteratively with smaller step size α:
```
x_0 = x
x_{t+1} = clip_ε(x_t + α · sign(∇_x L(θ, x_t, y)))
```

**PGD** — Projected Gradient Descent (Madry et al., 2017)
Like I-FGSM but with random initialization inside the ε-ball. Gold standard for L∞ evaluation:
```
x_0 = x + uniform(-ε, ε)
x_{t+1} = Π_{B(x,ε)}(x_t + α · sign(∇_x L(θ, x_t, y)))
```

**MI-FGSM** — Momentum Iterative (Dong et al., 2018)
Adds momentum to stabilize gradient direction — greatly improves transferability:
```
g_{t+1} = μ · g_t + ∇_x L(θ, x_t, y) / ||∇_x L||_1
x_{t+1} = clip_ε(x_t + α · sign(g_{t+1}))
```

### Minimal Perturbation Attacks

**DeepFool** (Moosavi-Dezfooli et al., 2016)
Finds the closest decision boundary and crosses it with minimal L2 perturbation. Iteratively linearizes the classifier and computes the shortest path to each class boundary.

**C&W** — Carlini & Wagner (2017)
Optimization-based attack that minimizes perturbation size while guaranteeing misclassification:
```
min ||δ||_2 + c · f(x + δ, t)
where f measures the gap between target and runner-up logit
```
Defeats many defenses that FGSM/PGD cannot.

### Sparse Attacks (L0/L1)

**JSMA** — Jacobian-based Saliency Map (Papernot et al., 2016)
Computes the Jacobian ∂F/∂x for all classes, builds a saliency map, and iteratively modifies the single most impactful pixel. Produces very sparse perturbations.

**EAD** — Elastic-net Attack (Chen et al., 2018)
Combines L1 and L2 penalties: `min ||δ||_2² + β·||δ||_1 + c·f(x+δ)`. Generates sparse perturbations like JSMA but via optimization.

### Black-box Attacks

**Transfer attacks**: Generate adversarial examples on a surrogate model (which you control), hope they transfer to the target. Effectiveness depends on architectural similarity.

**Score-based (NES)**: Estimate gradients by querying the model with noisy inputs — Natural Evolution Strategy.

**Boundary attack**: Start from a misclassified image and walk along the decision boundary toward the original, maintaining misclassification. Only needs hard labels.

### Defenses

**Adversarial Training** (Madry et al., 2017): Train on PGD-generated adversarial examples. Currently the most effective defense.

**TRADES** (Zhang et al., 2019): Balances clean accuracy and robustness via KL divergence: `L = CE(f(x), y) + β · KL(f(x) || f(x_adv))`.

## Scripts

| Script | Description |
|--------|-------------|
| `torchattacks_cheatsheet.py` | One-liner reference for all attacks using `torchattacks`. Run it to print the comparison table. Contains copy-paste functions for targeted, multi-attack, and save/load workflows. |
| `fgsm_pgd.py` | Complete FGSM, I-FGSM, PGD implementation — both manual (zero dependencies) and torchattacks wrapper. Supports Linf/L2 norms, targeted attacks, visualization, and batch evaluation. |
| `deepfool.py` | DeepFool implementation with per-image and batch modes. Produces minimal L2 perturbations. |
| `jsma_sparse.py` | JSMA (L0), EAD/ElasticNet (L1+L2), L1-PGD, and C&W wrapper. For scenarios requiring sparse perturbations. |
| `blackbox_evasion.py` | Transfer attacks, NES score-based estimation, Boundary attack (decision-based), and GoodWord attack for text classifiers. |
| `adversarial_training.py` | PGD adversarial training, TRADES training, and comprehensive robustness evaluation pipeline. |

## References

- Goodfellow et al. (2014) — *Explaining and Harnessing Adversarial Examples* (FGSM)
- Kurakin et al. (2016) — *Adversarial examples in the physical world* (BIM)
- Madry et al. (2017) — *Towards Deep Learning Models Resistant to Adversarial Attacks* (PGD)
- Moosavi-Dezfooli et al. (2016) — *DeepFool: a simple and accurate method to fool deep neural networks*
- Carlini & Wagner (2017) — *Towards Evaluating the Robustness of Neural Networks* (C&W)
- Papernot et al. (2016) — *The Limitations of Deep Learning in Adversarial Settings* (JSMA)
- Chen et al. (2018) — *EAD: Elastic-Net Attacks to DNNs*
- Zhang et al. (2019) — *Theoretically Principled Trade-off between Robustness and Accuracy* (TRADES)
