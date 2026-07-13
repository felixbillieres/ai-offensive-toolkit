# PGD (Projected Gradient Descent)

> **In one sentence:** PGD is the strong, standard evasion attack: iterative gradient steps like BIM, but starting from a random point inside the budget and optionally restarting several times to find the hardest adversarial example.

## What it is

PGD (Madry et al., 2017) is the gold-standard white-box Linf (and L2) attack. It is [BIM/I-FGSM](bim-ifgsm.md) with two additions: a **random start** inside the `eps`-ball and optional **random restarts** (run several times, keep the best). It is the de-facto benchmark for evaluating robustness: "robust to PGD" is the standard claim a defense must earn.

## The problem it exploits

The loss surface around an input has many local optima. A deterministic attack that always starts at `x` can get stuck in a shallow one and wrongly conclude the model is robust. PGD exploits the fact that the surface has *better* adversarial points nearby: by jittering the start and retrying, it explores different basins and finds stronger examples. It treats attacking as constrained optimization: maximize loss subject to staying in the `eps`-ball.

## Intuition

Same foggy hillside as [BIM](bim-ifgsm.md), but now imagine the hill has several bumps and you want the very highest reachable point within a fenced circle of radius `eps`. If you always start at the center, you might climb the nearest small bump and stop. PGD instead parachutes you into a **random spot inside the fence**, lets you climb (small steps, snapping back to the fence when you hit it), and does this a few times from different random drops, keeping the highest summit you reached. Random starts plus restarts = you do not get fooled by one easy bump.

## How it works

```
best = x
for r in 1..restarts:
    x_0 = x + uniform(-eps, eps)            # random start in the Linf ball
    x_0 = clip(x_0, 0, 1)
    for t in 1..steps:
        g   = sign( grad_x L(f(x_{t-1}), y) )
        x_t = x_{t-1} + alpha * g           # ascent step (subtract for targeted)
        x_t = project_eps(x_t, x, eps)      # snap back into the eps-ball
        x_t = clip(x_t, 0, 1)
    keep x_t in `best` if its loss beats the current best
return best
```

For **L2** PGD, the step normalizes the gradient by its L2 norm and the projection rescales the perturbation so its L2 length is at most `eps`, instead of clipping per-pixel. The toolkit implements both and defaults the step size to `alpha = eps / steps * 2.5`, a common heuristic that lets PGD reach the boundary within the step budget.

## Threat model and prerequisites

- **Access:** white-box (gradients required).
- **Query budget:** `restarts * steps` forward+backward passes (default 1 restart, 40 steps). Heaviest of the first-order family but still cheap next to black-box.
- **Norm:** Linf (default) or L2, both in the toolkit.
- **Knowledge:** loss and label. Randomized, so results vary slightly per run unless you fix the seed.

## When to use it

Use PGD when:

- You want the **standard strong Linf attack** to break or stress-test a model.
- You are **evaluating a defense**: "does it survive PGD with restarts?" is the accepted bar.
- You are doing **adversarial training** (train on PGD examples for the best-known robustness).

Prefer [MI-FGSM](mi-fgsm.md) if the target is black-box and you rely on transfer (PGD overfits the surrogate and transfers less well). Prefer [DeepFool](deepfool.md)/[C&W](carlini-wagner.md) if you want a *minimal* perturbation rather than a strong fixed-budget one. Prefer [AutoPGD](pgd.md) (via `--backend torchattacks --attack autopgd`) if you want a step-size-free, parameter-robust variant.

## Step by step with the toolkit

PGD is the default attack in `fgsm_pgd.py`.

```bash
# Standard Linf PGD, 40 steps
python -m evasion.fgsm_pgd --attack pgd --eps 0.031 --steps 40 --norm Linf

# PGD with 5 random restarts (stronger, slower)
python -m evasion.fgsm_pgd --attack pgd --eps 0.3 --steps 40 --restarts 5 --dataset mnist

# PGD-L2
python -m evasion.fgsm_pgd --attack pgd --norm L2 --eps 2.0 --steps 40

# Targeted PGD-L2 forcing class 5
python -m evasion.fgsm_pgd --attack pgd --norm L2 --eps 2.0 --targeted --target-class 5

# torchattacks AutoPGD backend (step-size free)
python -m evasion.fgsm_pgd --backend torchattacks --attack autopgd --eps 0.031
```

In Python:

```python
from evasion.fgsm_pgd import pgd_attack, evaluate_attack

adv = pgd_attack(model, images, labels, eps=0.031, steps=40,
                 norm="Linf", random_start=True, restarts=1)
evaluate_attack(model, images, adv, labels)
```

Key flags: `--eps`, `--steps`, `--alpha`, `--norm {Linf,L2}`, `--restarts`, `--targeted`/`--target-class`, `--seed`.

## Detection and defense

- **Adversarial training on PGD** (`evasion/adversarial_training.py`) is currently the most effective defense; **TRADES** (also in that script) trades a bit of clean accuracy for more robustness.
- **Gradient masking defenses** often *look* like they beat PGD but fail against black-box or adaptive attacks; always test with restarts and a black-box baseline.
- **Detection** of PGD noise is harder than FGSM because iteration spreads the perturbation less predictably, but feature-squeezing still catches a meaningful fraction.

## Explain it to a non-expert

PGD is the industry-standard stress test for image models. It repeatedly nudges the input a little in the most damaging direction, always staying within an invisible budget, and it starts from random spots and retries so it does not get fooled by an easy first attempt. If a model survives PGD, people consider it genuinely robust; if it does not, the model is not.

## References

- Madry, Makelov, Schmidt, Tsipras, Vladu (2017), *Towards Deep Learning Models Resistant to Adversarial Attacks*
- Croce and Hein (2020), *Reliable Evaluation ... AutoAttack / AutoPGD*
- HTB AI Red Teamer, module 09 (first-order evasion)
- Related: [BIM/I-FGSM](bim-ifgsm.md), [FGSM](fgsm.md), [MI-FGSM](mi-fgsm.md), [overview](00-overview.md)
