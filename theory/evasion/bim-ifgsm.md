# BIM / I-FGSM (Basic Iterative Method)

> **In one sentence:** Instead of one big FGSM step, take many small FGSM steps and clip back into the budget after each one, which finds a much stronger adversarial example.

BIM (Basic Iterative Method) and I-FGSM (Iterative FGSM) are two names for the same attack (Kurakin et al., 2016).

## What it is

BIM is the iterative version of [FGSM](fgsm.md). It is white-box and Linf. Where FGSM jumps once by `eps`, BIM takes `steps` smaller jumps of size `alpha`, re-computing the gradient at each new point and projecting (clipping) back inside the `eps`-ball so it never exceeds the budget. This is deterministic: no randomness, same result every run.

## The problem it exploits

FGSM assumes the model is linear along the whole step. It is not. One big step overshoots and lands somewhere the initial gradient no longer describes. BIM fixes this by re-measuring the slope after every small step, so it follows the *curved* loss surface instead of a single straight tangent. It exploits the same local-linearity of networks but respects that the linear approximation is only valid locally.

## Intuition

Back to the foggy hillside from FGSM. FGSM takes one giant leap toward where uphill *seemed* to be. But after a few meters the terrain curves and you are no longer heading up. BIM instead takes many short steps: after each step you stop, feel the slope again, and correct your heading. You end up much higher because you keep re-aiming. The clipping is a leash: you must stay within `eps` of your starting point, so after each step you snap back if you wandered too far.

## How it works

```
x_0   = x
for t in 1..steps:
    g_t     = sign( grad_x L(f(x_{t-1}), y) )
    x_t     = x_{t-1} + alpha * g_t            # small step (subtract for targeted)
    x_t     = clip_eps( x_t, x, eps )          # project back into Linf eps-ball
    x_t     = clip(x_t, 0, 1)                  # keep valid image
```

Where `clip_eps` forces `|x_t - x| <= eps` element-wise, and `alpha` is the per-step size. A common default is `alpha = eps / steps` so the total motion cannot exceed `eps` even in a straight line; the toolkit uses exactly this default when `alpha` is not given.

The only differences from [PGD](pgd.md) are: BIM has **no random start** and typically **no restarts**. PGD is "BIM plus randomness".

## Threat model and prerequisites

- **Access:** white-box (needs gradients).
- **Query budget:** `steps` forward+backward passes (default 10 to 40). More than FGSM, far less than black-box.
- **Norm:** Linf.
- **Knowledge:** loss and label. Deterministic, so reproducible.

## When to use it

Use BIM when:

- You want something **stronger than FGSM** but do not need the extra robustness that PGD's random restarts provide.
- You want a **deterministic, reproducible** iterative attack (useful when comparing runs or debugging a defense).

Prefer [PGD](pgd.md) for the standard strong benchmark (its random start escapes bad starting points and finds harder adversarial examples). Prefer [MI-FGSM](mi-fgsm.md) if the real goal is **transfer** to a black-box target. Prefer [DeepFool](deepfool.md)/[C&W](carlini-wagner.md) if you want the *smallest* perturbation rather than the strongest fixed-budget one.

## Step by step with the toolkit

`--attack ifgsm` in `fgsm_pgd.py`:

```bash
# 20-step BIM on MNIST, budget 0.3
python -m evasion.fgsm_pgd --attack ifgsm --eps 0.3 --steps 20 --dataset mnist

# Explicit step size, against your own model
python -m evasion.fgsm_pgd --attack ifgsm --eps 0.03 --alpha 0.005 --steps 10 \
    --model-path ./model.pt --output-json bim.json
```

In Python:

```python
from evasion.fgsm_pgd import ifgsm_attack, evaluate_attack

adv = ifgsm_attack(model, images, labels, eps=0.3, alpha=0.03, steps=10)
evaluate_attack(model, images, adv, labels)
```

Key flags: `--eps`, `--steps`, `--alpha` (auto = `eps/steps` if omitted), `--targeted`/`--target-class`.

## Detection and defense

- **PGD adversarial training** (`evasion/adversarial_training.py`) is the main defense and also covers BIM since PGD is strictly stronger.
- **Input preprocessing** (JPEG, bit-depth reduction) still removes some of the Linf noise, though BIM examples are harder to reverse than FGSM ones.
- **Detection:** iterative Linf noise is still fairly uniform and detectable by feature-squeezing style tests, though less trivially than single-step FGSM.

## Explain it to a non-expert

FGSM guesses the right direction and leaps once, often overshooting. BIM instead sneaks up in many tiny steps, re-checking its aim each time and never straying past the allowed budget. Same idea, but the careful version reliably finds a stronger fake input.

## References

- Kurakin, Goodfellow, Bengio (2016), *Adversarial Examples in the Physical World*
- HTB AI Red Teamer, module 09 (first-order evasion)
- Related: [FGSM](fgsm.md), [PGD](pgd.md), [MI-FGSM](mi-fgsm.md), [overview](00-overview.md)
