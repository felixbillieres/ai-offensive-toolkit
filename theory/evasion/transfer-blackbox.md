# Transfer Attacks (Black-box via Surrogate)

> **In one sentence:** Build adversarial examples against your own copy of a similar model and replay them on the real, unseen target, betting that a fooling input for one model also fools another.

## What it is

A transfer attack is a black-box strategy that needs **no gradient access and no queries to the target during crafting**. You train or obtain a **surrogate** model on the same task, run any white-box attack against it ([PGD](pgd.md), [MI-FGSM](mi-fgsm.md), [C&W](carlini-wagner.md)), and feed the resulting adversarial examples to the target. It is the most realistic remote attack: you attack an API you cannot see inside.

## The problem it exploits

Adversarial examples **transfer**. Models trained on similar data to solve the same task tend to learn similar decision boundaries and share the same blind spots. An input that lands in a blind spot of one model often lands in a nearby blind spot of another. Transferability is stronger when the surrogate and target share architecture family, training data, or preprocessing, and it is boosted by attacks that find *general* rather than model-specific perturbations (that is why [MI-FGSM](mi-fgsm.md) and ensembles matter here).

## Intuition

Suppose two people took the same course from the same textbook. If you find a trick question that fools one of them, there is a good chance it fools the other, because they learned the same material the same way. The surrogate is a student you *can* interrogate freely; the target is a student you cannot. You find questions that trip up the surrogate and hope the shared education means they also trip up the target. The more alike their training, the higher the hit rate.

## How it works

```
1. Obtain a surrogate S similar to the target T
   (same task; train your own, use a public pretrained model, or
    distill T by querying it and training S on the responses).
2. Craft adversarial examples on S with a white-box attack:
       x_adv = attack(S, x, y)          # e.g. MI-FGSM for best transfer
3. Submit x_adv to T (few or zero queries) and measure success.
4. Boost transfer: use momentum (MI-FGSM), attack an ENSEMBLE of
   surrogates, and/or add input diversity so x_adv is not overfit to S.
```

The toolkit's `transfer_attack(surrogate_model, target_model, images, labels, attack_fn, **kwargs)` does steps 2 and 3: it runs `attack_fn` on the surrogate, then reports how many examples fooled the surrogate, how many fooled the target, and the **transfer rate** (target fooled / surrogate fooled).

## Threat model and prerequisites

- **Access:** black-box target. You need a surrogate; the target itself can be pure black-box.
- **Query budget:** near zero to the target during crafting (only confirmation queries). Cheap and stealthy.
- **Norm:** whatever the underlying white-box attack uses (Linf with MI-FGSM/PGD).
- **Key prerequisite:** a surrogate that resembles the target. Success hinges on this similarity.

## When to use it

Use transfer when:

- The target is a **remote black-box** and you want to avoid the huge query counts that [NES](nes-score-based.md) and [Boundary](boundary-attack.md) require.
- You can build or obtain a **plausible surrogate** (public models on the same task, or distill the target).
- **Stealth** matters: minimal target queries means minimal footprint for rate-limiting or monitoring to catch.

Prefer [NES](nes-score-based.md) if you can query for scores and no good surrogate exists (score-based is more reliable but query-heavy). Prefer [Boundary](boundary-attack.md) if you only get labels and want a *targeted, minimal* result. Always pair transfer with [MI-FGSM](mi-fgsm.md) for the best hit rate.

## Step by step with the toolkit

```python
from evasion.blackbox_evasion import transfer_attack
from evasion.fgsm_pgd import pgd_attack, torchattacks_attack

# Transfer using PGD on the surrogate:
adv = transfer_attack(surrogate_model, target_model, images, labels,
                      attack_fn=pgd_attack, eps=0.031, steps=40, norm="Linf")

# Better transfer using MI-FGSM (momentum) on the surrogate:
adv = transfer_attack(surrogate_model, target_model, images, labels,
                      attack_fn=torchattacks_attack, attack_name="mifgsm",
                      eps=0.031, steps=10)
```

`transfer_attack` prints `Surrogate fooled`, `Target fooled`, and `Transfer rate`. The `__main__` in `blackbox_evasion.py` also offers `--attack transfer` as a placeholder that expects you to wire in real models.

## Detection and defense

- **Ensemble adversarial training** specifically hardens models against transferred examples and is the targeted defense here.
- **Randomized inference** (random resize/pad, random smoothing) breaks the alignment between the surrogate-crafted direction and the target, cutting transfer sharply.
- **Keeping the target private** (architecture, training data, preprocessing) lowers surrogate similarity and thus transfer rate.
- **Query monitoring** helps less here because the target sees so few queries.

## Explain it to a non-expert

You cannot see inside the target model, so you build your own lookalike, find inputs that fool the lookalike, and try them on the real thing. Because models trained the same way share the same weaknesses, those inputs often fool the target too, all without ever peeking inside it. This is the most realistic way to attack a commercial AI service.

## References

- Papernot, McDaniel, Goodfellow (2016), *Transferability in Machine Learning*
- Liu et al. (2017), *Delving into Transferable Adversarial Examples and Black-box Attacks*
- Dong et al. (2018), *Boosting Adversarial Attacks with Momentum* (transfer boosting)
- HTB AI Red Teamer, module 09 and black-box material
- Related: [MI-FGSM](mi-fgsm.md), [NES score-based](nes-score-based.md), [Boundary](boundary-attack.md), [overview](00-overview.md)
