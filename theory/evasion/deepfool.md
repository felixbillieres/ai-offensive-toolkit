# DeepFool

> **In one sentence:** DeepFool finds the *smallest* nudge that pushes an input across the nearest decision boundary by repeatedly pretending the model is linear and stepping straight to the closest boundary.

## What it is

DeepFool (Moosavi-Dezfooli et al., 2016) is a white-box, untargeted, minimal-perturbation attack, usually measured in L2. Unlike [FGSM](fgsm.md)/[PGD](pgd.md), which spend a fixed budget `eps`, DeepFool searches for the *minimum* perturbation that just barely flips the label. It is the go-to tool for **measuring** how robust a model is, because the size of the perturbation it returns is a direct estimate of the distance to the decision boundary.

## The problem it exploits

Every classifier carves input space into regions with decision boundaries between classes. Near any input there is a *closest* boundary, and the shortest path to fool the model is to step perpendicular to it. For a linear classifier this distance has a clean closed form. DeepFool exploits the fact that deep networks are *locally* nearly linear: it linearizes the model at the current point, solves the easy linear problem to find the nearest boundary, steps there, and repeats until it actually crosses. It gets very close to the true minimal perturbation.

## Intuition

Imagine you are standing in one country and want to cross into any neighboring country using as few steps as possible. You do not care *which* neighbor, just the nearest border. You look at all the borders around you, estimate which is closest, and walk straight at it. Borders are curved, so when you arrive you re-check and adjust, but each move is aimed at the nearest crossing. FGSM by contrast just walks a fixed distance in one guessed direction, often far past a border it could have reached in a fraction of the distance.

## How it works

For each other class `k`, DeepFool linearizes the gap between class `k` and the current class and computes how far and in which direction the boundary is:

```
current class = k_0 (the model's prediction)
loop until the prediction changes:
    for each candidate class k != k_0:
        w_k   = grad f_k(x) - grad f_{k_0}(x)      # boundary direction
        f_k   = f_k(x) - f_{k_0}(x)                # signed gap to that boundary
        dist_k = |f_k| / ||w_k||                    # linear distance to boundary k
    pick k* = the class with the smallest dist_k    # nearest boundary
    r_i   = (dist_k* + tiny) * w_k* / ||w_k*||       # minimal step toward it
    x     = x + r_i
    (a small overshoot factor pushes safely across)
total perturbation = sum of all r_i
```

The final example applies `(1 + overshoot) * r_total` so the point lands just past the boundary rather than exactly on it. Typical `overshoot = 0.02`.

## Threat model and prerequisites

- **Access:** white-box (needs per-class gradients / the Jacobian rows).
- **Query budget:** a few iterations (default max 50), each needing gradients for the top few classes. More compute per step than FGSM, but usually converges in a handful of iterations.
- **Norm:** L2 primarily (the algorithm minimizes L2 to the boundary).
- **Mode:** untargeted (it goes to the *nearest* class, which you do not choose).

## When to use it

Use DeepFool when:

- You want to **measure robustness**: the mean L2 it needs is a clean per-image "distance to fool", far more informative than "did PGD at eps succeed".
- You want a **minimal, barely-visible** perturbation and do not care which wrong class you land in.
- You are building a **robustness metric or benchmark** across models.

Prefer [C&W](carlini-wagner.md) if you need a *targeted* minimal attack or need to break a defended model (DeepFool is less reliable against defenses). Prefer [PGD](pgd.md) if you want a strong fixed-budget attack rather than a minimal one. Prefer [JSMA](jsma.md)/[EAD](ead-elasticnet.md) if you want *sparse* (few-pixel) rather than small-L2 perturbations.

## Step by step with the toolkit

`deepfool.py` exposes per-image and batch functions. The `__main__` block runs a demo on MNIST:

```bash
python -m evasion.deepfool --max-iter 100 --num-classes 10 --batch-size 16
```

The richest usage is importing the functions:

```python
from evasion.deepfool import deepfool_single, deepfool_batch, evaluate_and_visualize

# single image
r_total, adv_image, adv_class, iters = deepfool_single(
    model, image, num_classes=10, max_iter=50, overshoot=0.02)

# whole batch
adv_images, perturbations, adv_labels = deepfool_batch(
    model, images, labels, num_classes=10, max_iter=50)
evaluate_and_visualize(model, images, adv_images, labels, adv_labels)
```

Or via torchattacks:

```python
from evasion.deepfool import deepfool_torchattacks
adv = deepfool_torchattacks(model, images, labels, steps=50, overshoot=0.02)
```

Key parameters: `num_classes` (how many top classes to consider per step), `max_iter`, `overshoot`.

## Detection and defense

- **Adversarial training** raises the L2 distance DeepFool needs, which *is* the robustness metric, so a robust model shows a larger mean DeepFool perturbation.
- Because DeepFool perturbations are minimal, they sit right on the boundary and are **fragile**: input smoothing, JPEG compression, or bit-depth reduction often reverse them.
- **Detection:** minimal-perturbation examples are close to the boundary, so *prediction-confidence* and *neighbor-consistency* checks can flag them.

## Explain it to a non-expert

A classifier divides the world into regions with borders between them. DeepFool figures out the nearest border to an input and takes the shortest possible step across it, so the change is as small as it can be while still flipping the answer. Because that step size measures the distance to the border, security teams use DeepFool to quantify exactly how fragile a model is.

## References

- Moosavi-Dezfooli, Fawzi, Frossard (2016), *DeepFool: a simple and accurate method to fool deep neural networks*
- HTB AI Red Teamer, module 09 (first-order evasion), DeepFool section
- Related: [C&W](carlini-wagner.md), [PGD](pgd.md), [JSMA](jsma.md), [overview](00-overview.md)
