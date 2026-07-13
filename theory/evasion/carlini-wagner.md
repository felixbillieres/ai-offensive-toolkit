# C&W (Carlini and Wagner)

> **In one sentence:** C&W turns evasion into a careful optimization problem that squeezes the perturbation as small as possible while guaranteeing misclassification, making it strong enough to break most defenses.

## What it is

The Carlini and Wagner attack (2017) is a white-box, optimization-based attack, most commonly used in its L2 form (L0 and Linf variants exist). It is widely regarded as the strongest evasion attack for *breaking defenses*: many defenses that stop FGSM/PGD collapse under C&W. It is slower than gradient-step attacks because it runs an inner optimization loop (hundreds of Adam steps) per example.

## The problem it exploits

Simpler attacks either spend a fixed budget ([PGD](pgd.md)) or greedily approximate the boundary ([DeepFool](deepfool.md)). C&W instead directly minimizes "perturbation size" and "misclassification failure" together, using three engineering tricks that make the optimization actually work:

1. A **change-of-variables** (tanh) so the pixel-range constraint `[0,1]` is automatically satisfied and the optimizer runs unconstrained.
2. A **margin loss** `f` that keeps pushing even after the label flips, buying a confidence margin `kappa` so the example survives small perturbations from a defense.
3. A **constant `c`** balancing "small perturbation" against "definitely misclassified", tuned by binary search.

Together these avoid the gradient-masking and obfuscation tricks that fool weaker attacks.

## Intuition

FGSM/PGD are like shoving something across a line with a fixed-strength push. DeepFool is like walking straight to the nearest line. C&W is like a patient sculptor with a cost function: "make the change as invisible as you can, but it *must* end up on the other side of the line with room to spare". It slowly optimizes both goals at once, chiseling away any unnecessary perturbation, and the margin `kappa` means it does not stop the instant it crosses but keeps going until the example is safely and confidently misclassified. That margin is what lets it survive defenses that would nudge a barely-crossed example back.

## How it works

```
minimize over w:   || (tanh(w)+1)/2 - x ||_2^2  +  c * f( (tanh(w)+1)/2 )

where the adversarial image is  x_adv = (tanh(w)+1)/2      # always in [0,1]

and the margin loss (targeted class t) is
    f(x') = max( max_{i != t} Z(x')_i  -  Z(x')_t ,  -kappa )
    (Z = logits; untargeted flips the roles of real vs. other class)
```

- The first term keeps the L2 perturbation small.
- `f` is zero once class `t` leads all others by at least `kappa`; making `kappa > 0` forces a confidence margin.
- `c` is found by **binary search**: too small and the attack fails, too large and the perturbation is bigger than needed.

The toolkit's [EAD](ead-elasticnet.md) implementation uses exactly this margin-loss structure (see `ead_attack` in `jsma_sparse.py`), and C&W is exposed directly via torchattacks.

## Threat model and prerequisites

- **Access:** white-box (needs logits and gradients).
- **Query budget:** expensive: `steps` optimizer iterations (default 100+) times the binary-search rounds for `c`. Orders of magnitude more compute than PGD.
- **Norm:** L2 (default), also L0 and Linf variants.
- **Mode:** targeted or untargeted; `kappa` controls how confidently it is misclassified.

## When to use it

Use C&W when:

- You need to **break a defended model** and PGD/FGSM already failed. C&W is the standard "adaptive attack" for evaluating defenses.
- You want a **high-confidence, minimal-L2** adversarial example (set `kappa > 0`).
- You are doing a **rigorous robustness evaluation** and want the tightest attack, compute permitting.

Prefer [DeepFool](deepfool.md) if you just need a fast minimal-perturbation *measurement* and the model is undefended. Prefer [PGD](pgd.md) when compute is tight and the model is not heavily defended. Prefer [EAD](ead-elasticnet.md) if you want C&W-style strength but *sparse* (L1) perturbations.

## Step by step with the toolkit

`jsma_sparse.py` wraps C&W through torchattacks:

```bash
python -m evasion.jsma_sparse --attack cw --steps 100 --batch-size 8
```

In Python (direct wrapper):

```python
from evasion.jsma_sparse import torchattacks_cw

adv = torchattacks_cw(model, images, labels, c=1, kappa=0, steps=100, lr=0.01)
preds = model(adv).argmax(1)
```

Key parameters: `c` (perturbation vs. success balance), `kappa` (confidence margin), `steps`, `lr`. Raise `kappa` to make examples survive defenses; raise `steps` for a tighter perturbation. For the L1/sparse cousin, see the built-in `ead_attack` documented in [EAD](ead-elasticnet.md).

## Detection and defense

- C&W is *designed* to evade detection, so many published detectors and preprocessing defenses fail against it; this is precisely why it is the benchmark for defense evaluation.
- **Adversarial training** still helps (it raises the required L2), but C&W with a large `kappa` and enough steps remains the toughest attack to fully defend.
- The main practical cost to the attacker is **compute**: rate limiting matters less here (it is white-box) but the per-example optimization is slow.

## Explain it to a non-expert

C&W treats the attack as a precise optimization: make the change to the input as small and invisible as possible, but guarantee the model is confidently wrong, with margin to spare. That patience and that safety margin are why C&W defeats defenses that easily stop the quick-and-dirty attacks. The trade-off is that it is slow, so it is used when strength matters more than speed.

## References

- Carlini and Wagner (2017), *Towards Evaluating the Robustness of Neural Networks*
- HTB AI Red Teamer, module 10 (sparsity), which builds the same margin-loss used here
- Related: [DeepFool](deepfool.md), [EAD / ElasticNet](ead-elasticnet.md), [PGD](pgd.md), [overview](00-overview.md)
