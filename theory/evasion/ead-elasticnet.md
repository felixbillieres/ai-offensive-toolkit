# EAD (ElasticNet Attack)

> **In one sentence:** EAD is C&W with an added L1 penalty, so the optimizer naturally zeroes out most pixels and produces a sparse perturbation, getting JSMA-style few-pixel changes through smooth optimization instead of greedy pixel picking.

## What it is

EAD (Elastic-net Attack to DNNs, Chen et al., 2018) is a white-box, optimization-based, **sparse** attack. It extends [C&W](carlini-wagner.md) by adding an L1 term to the objective. The L1 penalty is famous in statistics (LASSO / elastic net) for driving coefficients exactly to zero, so EAD ends up changing only a small subset of pixels, a sparse perturbation similar in spirit to [JSMA](jsma.md) but obtained by optimization rather than a greedy Jacobian loop.

## The problem it exploits

Directly minimizing the L0 norm (number of changed pixels) is NP-hard: you cannot smoothly optimize a pixel *count*. The trick EAD exploits is that the **L1 norm is the best convex surrogate for L0**: penalizing the sum of absolute changes encourages solutions where most changes are exactly zero. By blending L1 (sparsity) with L2 (visual similarity) and the C&W margin loss (misclassification), EAD gets sparse *and* small-amplitude perturbations from a single differentiable objective the optimizer can actually descend.

## Intuition

Imagine you are told: "disguise this image, but every pixel you touch costs you money, and touching it a lot costs even more". The per-touch cost (L1) makes you leave most pixels completely alone and only pay for the few that really matter. The per-amount cost (L2) stops you from making any single change grotesquely large. The result is a handful of modest, targeted edits. JSMA reaches a similar place by manually picking one pixel at a time; EAD lets an optimizer discover the sparse set all at once by making unused pixels "expensive".

## How it works

```
minimize over the perturbation delta = x' - x:

    c * f(x')  +  ||delta||_2^2  +  beta * ||delta||_1

where:
    f(x')          = C&W margin loss (forces misclassification, see C&W page)
    ||delta||_2^2  = keeps the change visually small
    beta*||delta||_1 = the sparsity driver (pushes most pixels to zero)
    c              = weight on the misclassification term
```

The toolkit's `ead_attack` implements exactly this: it optimizes `w` with Adam, forms `adv = clamp(x + w, 0, 1)`, computes the C&W-style `real`/`other` logit margin, and adds `l2_loss + c*f_loss + beta*l1_loss`. It tracks, per sample, the successful adversarial with the smallest L1. Larger `beta` gives sparser perturbations.

## Threat model and prerequisites

- **Access:** white-box (logits and gradients).
- **Query budget:** `steps` optimizer iterations (default 100), comparable in cost to C&W and far cheaper per-step than JSMA's Jacobian loop on many-class problems.
- **Norm:** L1 (primary, the sparsity driver) plus L2 (similarity). Effectively targets sparse perturbations.
- **Mode:** targeted or untargeted.

## When to use it

Use EAD when:

- You want a **sparse perturbation** but JSMA is too slow (JSMA needs a full Jacobian each step; EAD scales better with many classes).
- You want the **strength and defense-breaking properties of C&W** combined with sparsity.
- You are comparing sparse-attack methods and want the optimization-based counterpart to JSMA.

Prefer [JSMA](jsma.md) when you want a strict L0 budget and interpretable per-pixel saliency on a small-class task. Prefer plain [C&W](carlini-wagner.md) when you want minimal *L2* (dense) rather than sparse. Prefer [PGD](pgd.md) for fast standard Linf attacks.

## Step by step with the toolkit

`jsma_sparse.py` runs EAD as a targeted attack in its demo:

```bash
python -m evasion.jsma_sparse --attack ead --target 3 --steps 100 --batch-size 8
```

In Python:

```python
from evasion.jsma_sparse import ead_attack
import torch

target_labels = torch.full_like(labels, 3)
adv = ead_attack(model, images, labels,
                 target_labels=target_labels, targeted=True,
                 c=1.0, kappa=0, beta=1e-3, steps=100, lr=0.01)
preds = model(adv).argmax(1)
```

Key parameters: `beta` (raise it for sparser perturbations), `c` (misclassification weight), `kappa` (confidence margin, as in C&W), `steps`, `lr`, `targeted`/`target_labels`.

## Detection and defense

- Like C&W, EAD is strong against many detectors and preprocessing defenses; the L1 structure can make it even harder for some Linf-oriented defenses.
- **Spatial smoothing / median filtering** can remove isolated sparse changes.
- **Adversarial training** raises the required perturbation but does not fully neutralize it.

## Explain it to a non-expert

EAD is the optimization-based way to make a sparse attack. By charging a cost for every pixel it touches, it forces itself to change only the few pixels that truly matter, while still guaranteeing the model is fooled. It reaches the same "few conspicuous edits" result as JSMA but does it through smooth optimization, which scales better and inherits C&W's ability to beat defenses.

## References

- Chen, Sharma, Zhang, Yi, Hsieh (2018), *EAD: Elastic-Net Attacks to Deep Neural Networks*
- Carlini and Wagner (2017), for the margin loss EAD builds on
- HTB AI Red Teamer, module 10 (sparsity), ElasticNet section
- Related: [JSMA](jsma.md), [C&W](carlini-wagner.md), [overview](00-overview.md)
