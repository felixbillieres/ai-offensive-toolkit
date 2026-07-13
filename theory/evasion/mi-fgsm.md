# MI-FGSM (Momentum Iterative FGSM)

> **In one sentence:** Add momentum to iterative FGSM so gradient directions accumulate over steps, producing adversarial examples that transfer far better to models you cannot see.

## What it is

MI-FGSM (Dong et al., 2018) is [BIM/I-FGSM](bim-ifgsm.md) with a **momentum** term added to the gradient. It is white-box to *craft* but its whole reason to exist is **transferability**: the examples it produces fool other, unseen models much more often than plain BIM or [PGD](pgd.md) examples do. It won the NeurIPS 2017 adversarial competition largely on that property.

## The problem it exploits

Iterative attacks like BIM and PGD are strong on the model they are crafted against, but they *overfit* to that model's specific quirks, so they transfer poorly to a different target. The gradient can also oscillate between steps, getting stuck in poor local optima. Momentum solves both: by averaging gradient directions over time it smooths out oscillation and finds a more *general* adversarial direction, one that points at a weakness shared by many models rather than one model's idiosyncrasy. That shared weakness is what makes it transfer.

## Intuition

Picture a ball rolling downhill (here, uphill on the loss) versus a person taking discrete steps. The stepper (BIM) reacts only to the slope right under their feet, so on a bumpy, noisy surface they zig-zag and can get trapped. A rolling ball (momentum) builds up speed in a consistent direction and coasts through small bumps and noise, ending up on a broad, stable slope. That broad, stable direction is one that many different hills share, which is exactly why the resulting attack works on models you never touched.

## How it works

```
g_0 = 0
x_0 = x
for t in 1..steps:
    grad     = grad_x L(f(x_{t-1}), y)
    grad     = grad / ||grad||_1                       # L1-normalize so scale is stable
    g_t      = mu * g_{t-1} + grad                     # accumulate momentum
    x_t      = x_{t-1} + alpha * sign(g_t)             # step in the accumulated direction
    x_t      = clip_eps(x_t, x, eps); clip(x_t, 0, 1)
```

Where `mu` is the decay factor (typically 1.0) and the L1 normalization keeps each step's contribution comparable so early gradients do not dominate. Everything else is BIM. The `sign(g_t)` keeps it an Linf attack.

## Threat model and prerequisites

- **Access to craft:** white-box on a **surrogate** you control.
- **Access to attack:** the real target can be **black-box**. You never query it during crafting; you rely on transfer.
- **Query budget:** `steps` passes on the surrogate; ideally a handful of confirmation queries on the target.
- **Norm:** Linf.
- **Knowledge:** you need a surrogate model that is plausibly similar to the target (same task, ideally similar architecture family).

## When to use it

Use MI-FGSM when:

- The target is a **black-box** and you are using a [transfer attack](transfer-blackbox.md). MI-FGSM is the standard "make my transfer attack land" upgrade.
- You want examples that generalize across an **ensemble** of surrogates (combine MI-FGSM with ensemble crafting for even better transfer).

Prefer plain [PGD](pgd.md) if the target is white-box and you only care about that one model (PGD is slightly stronger in the pure white-box setting). Prefer [NES](nes-score-based.md) or [Boundary](boundary-attack.md) if you can query the target directly and transfer is unreliable.

## Step by step with the toolkit

`fgsm_pgd.py` exposes MI-FGSM. Note: the manual backend maps `mifgsm` to the iterative routine, while the `torchattacks` backend uses a true momentum implementation, so for genuine momentum prefer the torchattacks backend.

```bash
# MI-FGSM via torchattacks (true momentum)
python -m evasion.fgsm_pgd --backend torchattacks --attack mifgsm --eps 0.031 --steps 10

# Manual backend (iterative approximation)
python -m evasion.fgsm_pgd --attack mifgsm --eps 0.3 --steps 10 --dataset mnist
```

For a full transfer workflow (craft on surrogate, replay on target), use `blackbox_evasion.py`:

```python
from evasion.blackbox_evasion import transfer_attack
from evasion.fgsm_pgd import torchattacks_attack

# craft MI-FGSM examples on the surrogate, evaluate transfer to the target
transfer_attack(surrogate_model, target_model, images, labels,
                attack_fn=torchattacks_attack, attack_name="mifgsm",
                eps=0.031, steps=10)
```

Key flags: `--attack mifgsm`, `--backend torchattacks`, `--eps`, `--steps`.

## Detection and defense

- **Adversarial training** and **input transformations** reduce transfer success but do not eliminate it; ensemble adversarial training specifically targets transferred examples.
- **Randomized input transforms** (random resize/pad) at inference blunt transfer attacks because the crafted direction no longer lines up.
- **Detection** is harder than for FGSM because momentum produces smoother, less telltale noise.

## Explain it to a non-expert

Normal iterative attacks memorize the exact model they were built against, so they fail on a different model. MI-FGSM adds momentum, like a rolling ball that ignores small bumps, which makes it find a weakness that many models share rather than one model's quirk. That is why its fake inputs still fool systems the attacker has never even looked inside.

## References

- Dong, Liao, Pang, Su, Zhu, Hu, Li (2018), *Boosting Adversarial Attacks with Momentum*
- HTB AI Red Teamer, module 09 (first-order evasion)
- Related: [BIM/I-FGSM](bim-ifgsm.md), [PGD](pgd.md), [transfer / black-box](transfer-blackbox.md), [overview](00-overview.md)
