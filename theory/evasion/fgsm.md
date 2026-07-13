# FGSM (Fast Gradient Sign Method)

> **In one sentence:** Take one step of a fixed size in the direction that most increases the model's error, using only the sign of the gradient, and you get a fast, cheap adversarial example.

## What it is

FGSM (Goodfellow et al., 2014) is the original and simplest gradient-based evasion attack. It is a single-step, white-box, Linf attack. It is weak compared to iterative methods but it is the baseline every other first-order attack builds on, and it is the fastest to compute (one backward pass).

## The problem it exploits

Deep networks are locally close to *linear* in their input. Because they are high-dimensional and roughly linear, many small changes in the same direction add up to a large change in the output. FGSM exploits exactly this: it pushes every input feature a little, all at once, in the direction the loss surface says will hurt the most. In thousands of dimensions, "a little per pixel" becomes "a lot" in the output logits.

## Intuition

Imagine you are standing on a hillside in thick fog and you want to climb as fast as possible with exactly one step of a fixed length. You cannot see the summit, but you can feel which way is uphill under each foot. FGSM feels the slope (the gradient) and takes one full-length step straight uphill. "Uphill" here means "toward more classification error". The step length is `eps`, your perturbation budget.

The clever trick is the word "sign". FGSM does not care *how* steep each direction is, only *which way* is up. Every pixel moves by the same amount `eps`, just up or down. That is what keeps the change bounded under the Linf norm (no single pixel moves more than `eps`).

## How it works

```
x_adv = x + eps * sign( grad_x L(f(x), y_true) )      # untargeted
x_adv = x - eps * sign( grad_x L(f(x), y_target) )    # targeted (descend toward target)
x_adv = clip(x_adv, 0, 1)                             # keep a valid image
```

Where:

```
x         = original input
y_true    = correct label
eps       = Linf budget, max change per feature
grad_x L  = gradient of the loss w.r.t. the input pixels
sign(.)   = +1 or -1 per element, discards magnitude
```

Untargeted: move *up* the loss for the true class (make it more wrong). Targeted: move *down* the loss for a chosen target class (make it predict `t`). One forward pass, one backward pass, done. That is why it is called *fast*.

## Threat model and prerequisites

- **Access:** white-box. You need the model's gradient, so you need the weights (or an autodiff-capable copy).
- **Query budget:** effectively 1 (one forward + backward pass). No target queries beyond that.
- **Norm:** Linf by construction. Because it is a fixed step, the resulting L2 size is large relative to what DeepFool or C&W would find.
- **Knowledge:** you need the loss function and the true label (untargeted) or a target label (targeted).

## When to use it

Use FGSM when:

- You want a **fast baseline** to sanity-check that a model is attackable at all.
- You are **generating a lot of adversarial examples cheaply**, for example to seed adversarial training.
- You are testing **transferability**: single-step attacks sometimes transfer better than heavily overfit iterative ones (though [MI-FGSM](mi-fgsm.md) is the proper tool for that).

Do NOT use FGSM when you need a strong or minimal attack. For strength use [PGD](pgd.md); for iterative determinism use [BIM/I-FGSM](bim-ifgsm.md); for the smallest perturbation use [DeepFool](deepfool.md) or [C&W](carlini-wagner.md).

## Step by step with the toolkit

The `fgsm_pgd.py` script has a full CLI. Run FGSM on MNIST with a visualization:

```bash
python -m evasion.fgsm_pgd --attack fgsm --eps 0.3 --dataset mnist --visualize
```

Against your own saved model:

```bash
python -m evasion.fgsm_pgd --attack fgsm --eps 0.03 --model-path ./model.pt
```

Targeted FGSM forcing class 5, exporting metrics:

```bash
python -m evasion.fgsm_pgd --attack fgsm --eps 0.3 --targeted --target-class 5 \
    --output-json fgsm_results.json
```

Or call the function directly in Python:

```python
from evasion.fgsm_pgd import fgsm_attack, evaluate_attack

adv = fgsm_attack(model, images, labels, eps=0.3)          # untargeted
evaluate_attack(model, images, adv, labels)                 # prints success rate, L2, Linf
```

Key flags: `--eps` (budget), `--targeted` / `--target-class`, `--model-path`, `--dataset`, `--visualize`, `--output-json`. FGSM ignores `--steps` and `--alpha` because it is single-step.

## Detection and defense

- **Adversarial training** on FGSM examples helps a little but is easily bypassed by iterative attacks; PGD adversarial training (`evasion/adversarial_training.py`) is the real defense.
- **Gradient masking** (making gradients uninformative) *appears* to stop FGSM but usually just hides the vulnerability; iterative or black-box attacks still succeed.
- **Feature squeezing / JPEG compression** removes a chunk of the uniform Linf noise and can reverse many FGSM examples.
- **Detection:** FGSM noise is statistically distinctive (uniform +/- eps grid), so simple detectors catch it more easily than C&W or DeepFool noise.

## Explain it to a non-expert

The model has a hidden sense of which direction of pixel change makes it most wrong. FGSM reads that direction once and nudges every pixel a hair in that direction. Each nudge is invisible on its own, but across an entire image they add up to flip the model's answer. It is the fastest attack and the textbook starting point, though not the strongest.

## References

- Goodfellow, Shlens, Szegedy (2014), *Explaining and Harnessing Adversarial Examples*
- HTB AI Red Teamer, module 09 (first-order evasion), FGSM section
- Related: [BIM/I-FGSM](bim-ifgsm.md), [PGD](pgd.md), [MI-FGSM](mi-fgsm.md), [overview](00-overview.md)
