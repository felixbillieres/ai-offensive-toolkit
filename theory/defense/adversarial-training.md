# Adversarial Training (PGD-AT and TRADES)

> **In one sentence:** Instead of training a model only on clean data, you generate the worst adversarial example for each sample on the fly and train on that, so the model learns a decision boundary that no longer breaks under small perturbations.

## What it is

Adversarial training is the strongest general defense against evasion attacks on neural networks. The idea, from Madry et al. (2017), is a minimax game: an inner attacker searches for the perturbation that maximizes the loss, and the outer trainer updates weights to minimize the loss on those perturbed inputs.

```
min_theta  E_(x,y) [  max_(||delta|| <= eps)  L(model(x + delta), y)  ]
           outer training           inner attack
```

Two variants live in the toolkit:

- **PGD-AT** (Madry): generate an adversarial example with Projected Gradient Descent, then train on it as if it were the real label.
- **TRADES** (Zhang et al., 2019): split the loss into a clean-accuracy term and a robustness term, and use a knob `beta` to trade one for the other.

## The attack it stops

It targets **evasion attacks**: small, often imperceptible input perturbations that flip the prediction. Concretely it hardens the model against the attacks in this toolkit:

- [../evasion/fgsm.md](../evasion/fgsm.md) (single-step)
- [../evasion/pgd.md](../evasion/pgd.md) (multi-step, the strongest first-order attack)
- [../evasion/deepfool.md](../evasion/deepfool.md) and [../evasion/jsma.md](../evasion/jsma.md) (boundary and sparse attacks)

It does **not** stop data leakage or LLM jailbreaks. For those see [dp-sgd.md](dp-sgd.md) and [adversarial-tuning.md](adversarial-tuning.md).

## Intuition

A normally trained model draws its decision boundary very close to the training points. Because the boundary is close, a tiny nudge in the right direction crosses it and changes the label. That nudge is exactly what an evasion attack computes.

Adversarial training pushes every training point away from the boundary during training. If, at every step, the model is forced to classify not just `x` but the worst point within a small ball around `x`, it must carve out a margin of radius `eps` around each example. After training, a perturbation smaller than `eps` no longer reaches the boundary, so the attack fails.

Think of it as vaccination: you inject a weakened version of the attack during training so the model builds immunity.

## How it works

### PGD-AT (the toolkit's `pgd` method)

For every batch:

1. **Generate** an adversarial batch with PGD: start from `x` plus small random noise, then repeat `steps` times: take a step of size `alpha` in the gradient sign direction, then project back into the L-infinity ball of radius `eps` and clamp to valid pixel range.
2. **Train** on the adversarial batch using the normal cross-entropy loss against the true labels.

The toolkit implements this exactly in `pgd_linf` and `adversarial_train`:

```python
adv = adv + alpha * adv.grad.sign()
perturbation = clamp(adv - images, -eps, eps)   # project into the eps ball
adv = clamp(images + perturbation, 0, 1)         # stay a valid image
```

### TRADES (the toolkit's `trades` method)

TRADES optimizes a two-part loss:

```
loss = CE(model(x), y)  +  beta * KL( model(x_adv) || model(x) )
       clean accuracy         robustness (push adv and clean outputs together)
```

The first term keeps clean accuracy. The second term does not use labels at all: it only asks that the model give the same answer for `x` and for its adversarial neighbor `x_adv`. The knob `beta` sets the price: higher `beta` means more robustness and lower clean accuracy.

## What it costs

- **Clean accuracy drops.** A robust model is almost always a few points (sometimes many) worse on normal inputs. This is a known and fundamental tradeoff, not a bug.
- **Training compute explodes.** Each training step runs a full PGD attack. With `pgd_steps=7` you do roughly 7 extra forward and backward passes per batch, so training is about 7x to 10x slower.
- **The robustness is only up to `eps`.** You get a margin of the radius you trained for and no more. Train at `eps=0.3`, get attacked at `eps=0.5`, and you lose.
- **TRADES adds one more knob (`beta`) to tune**, and the sweet spot is dataset specific.

## When to use it

- You serve a vision or tabular classifier where an attacker controls the input (fraud detection, malware detection, content moderation, autonomous perception).
- You have a known, bounded threat model: you can name the perturbation norm (usually L-infinity) and a realistic `eps`.
- You can afford the training slowdown and the clean-accuracy hit.

Use **PGD-AT** when maximum robustness matters more than clean accuracy. Use **TRADES** when you need to dial the balance explicitly with `beta`.

## Step by step with the toolkit

The script is `evasion/adversarial_training.py`. It trains a standard model and a robust model on MNIST, then evaluates both against a battery of FGSM and PGD attacks so you can see the gap.

Train a robust model with PGD adversarial training:

```bash
python -m evasion.adversarial_training --method pgd --eps 0.3 --epochs 20
```

Train with TRADES and control the robustness/accuracy balance via `beta`:

```bash
python -m evasion.adversarial_training --method trades --eps 0.3 --beta 6.0 --epochs 20
```

Available flags (read the `argparse` block at the bottom of the script):

- `--method {pgd, trades}`  which defense to train.
- `--eps`  perturbation budget the model is hardened against (default 0.3).
- `--epochs`  training epochs (default 10).
- `--beta`  TRADES tradeoff weight, higher means more robust (default 6.0).

The script automatically calls `evaluate_robustness`, which prints clean accuracy plus accuracy under FGSM and under PGD-7, PGD-20, and PGD-40 at several `eps` values. Compare the "Standard Model" block against the robust block: the standard model collapses under PGD while the robust model holds much of its accuracy.

To attack the model you just hardened, use the offense scripts and confirm the accuracy gap:

```bash
python -m evasion.fgsm_pgd --help
```

## Limitations and bypasses

- **Gradient masking / false robustness.** A model can look robust to a weak attack while still being broken by a stronger one. Always evaluate with strong PGD (many steps, restarts), which is why the toolkit tests PGD-20 and PGD-40, not just FGSM.
- **Larger `eps` than trained.** Robustness holds only inside the ball you trained on. An attacker who spends a bigger perturbation budget wins.
- **Different norm.** Train against L-infinity and you can still be beaten by an L2 or a sparse (L0) attack such as [../evasion/jsma.md](../evasion/jsma.md).
- **Adaptive and black-box attacks.** Transfer attacks and query-based black-box attacks ([../evasion/00-overview.md](../evasion/00-overview.md)) do not need your gradients and can still succeed.
- **The clean-accuracy tax may be unacceptable** for high-stakes accuracy-sensitive tasks, pushing teams to disable it.

Because of this, adversarial training is one layer, not the whole defense. Combine it with input preprocessing, detection, and (for privacy) [dp-sgd.md](dp-sgd.md).

## Explain it to a non-expert

Imagine training a guard dog. If you only ever show it calm, friendly visitors, it will be fooled the first time a burglar wears a friendly disguise. So during training you deliberately send in people in every disguise you can think of and reward the dog for still spotting the intruder. After enough practice, small disguises stop working. Adversarial training does the same for a model: it keeps showing the model cleverly disguised inputs during training so that, once deployed, those disguises no longer fool it.

## References

- Madry et al., 2017, "Towards Deep Learning Models Resistant to Adversarial Attacks" (PGD adversarial training).
- Zhang et al., 2019, "Theoretically Principled Trade-off between Robustness and Accuracy" (TRADES).
- Course material: `12-ai-defense/02_Adversarial_training/`.
- Toolkit script: `evasion/adversarial_training.py`.
- Related attack pages: [../evasion/pgd.md](../evasion/pgd.md), [../evasion/fgsm.md](../evasion/fgsm.md), [../evasion/deepfool.md](../evasion/deepfool.md).
