# NES (Score-based Black-box Attack)

> **In one sentence:** When you cannot see the model's gradient but can read its confidence scores, estimate the gradient by poking the input with random noise and watching how the scores wiggle, then run PGD on that estimate.

## What it is

NES (Natural Evolution Strategies, applied to adversarial attacks by Ilyas et al., 2018) is a black-box, **score-based** attack. It assumes the target returns confidence scores or probabilities (not just a label). It uses those scores to *estimate* the gradient via finite differences with random directions, then plugs that estimate into a normal [PGD](pgd.md) loop. No gradient access, no surrogate needed, but it costs many queries.

## The problem it exploits

White-box attacks need the exact gradient, which the model gives you for free via backpropagation. Black-box targets do not. But the gradient is just "how does the output change when I nudge the input", and you can *measure* that from the outside: nudge the input in a random direction, see how the score changes, and average many such probes. This exploits the fact that a scored output leaks directional information: each query reveals a little about the slope, and enough queries reconstruct a usable gradient.

## Intuition

You are blindfolded on the foggy hillside and cannot feel the slope directly, but you have an altimeter (the confidence score). To figure out which way is uphill, you take a small step in a random direction, read the altimeter, step back, and try another random direction. After many random probes you average the results: "on balance, uphill is that way". That averaged estimate is your gradient. It is noisy and burns a lot of altimeter readings (queries), but it works without ever feeling the ground.

## How it works

```
# NES gradient estimate at x (antithetic sampling: probe +u and -u):
grad_est = 0
for i in 1..n_samples/2:
    u = random gaussian noise
    L_plus  = loss( model(x + sigma*u), y )     # one query
    L_minus = loss( model(x - sigma*u), y )     # one query
    grad_est += (L_plus - L_minus) * u
grad_est /= (n_samples * sigma)

# Then run PGD using grad_est instead of the true gradient:
x_adv = x
for t in 1..steps:
    g     = NES_estimate(x_adv)
    x_adv = x_adv + alpha * sign(g)
    x_adv = clip_eps(x_adv, x, eps); clip(x_adv, 0, 1)
```

`sigma` is the probe size, `n_samples` the number of probes per step (more = less noisy estimate, more queries). Total queries roughly equal `steps * n_samples`. The toolkit's `nes_gradient_estimate` and `score_based_attack` implement exactly this, using antithetic (`+u` and `-u`) sampling to cut variance.

## Threat model and prerequisites

- **Access:** black-box, but the target must return **scores/probabilities** (or at least a soft signal), not just a top-1 label. If you only get a label, use [Boundary](boundary-attack.md) instead.
- **Query budget:** high. Roughly `steps * n_samples` queries (e.g. 40 * 100 = 4000) per image. Query cost is the main limitation.
- **Norm:** Linf (the toolkit clips the estimated-gradient PGD to an Linf ball).
- **Knowledge:** you need to map the returned scores to a usable loss.

## When to use it

Use NES when:

- The target is a **remote API that returns confidence scores**, and you have **no good surrogate** so [transfer](transfer-blackbox.md) is unreliable.
- You accept a **large query budget** in exchange for not needing model internals or a surrogate.

Prefer [transfer](transfer-blackbox.md) if a plausible surrogate exists (far fewer target queries). Prefer [Boundary](boundary-attack.md) if the target returns only a hard label. Prefer white-box [PGD](pgd.md) whenever you actually have the gradient (NES is only an estimate).

## Step by step with the toolkit

`blackbox_evasion.py` implements NES-based PGD:

```python
from evasion.blackbox_evasion import score_based_attack, nes_gradient_estimate

adv = score_based_attack(model, images, labels,
                         eps=0.3, steps=40,
                         sigma=0.001,     # probe size
                         n_samples=100)   # probes per step -> query cost
# prints progress: fooled X/N every 10 steps
```

You can also estimate the gradient alone:

```python
g = nes_gradient_estimate(model, images, labels, sigma=0.001, n_samples=100)
```

The `__main__` demo takes `--attack score --queries 1000 --eps 0.3` but expects you to supply a real model for meaningful results. Key parameters: `sigma`, `n_samples` (variance vs. query cost), `steps`, `eps`.

## Detection and defense

- **Query rate limiting and monitoring** is the primary defense: NES needs thousands of near-identical queries per image, which is a strong signal.
- **Returning only hard labels** (no scores) defeats NES entirely (forcing the attacker down to a boundary attack).
- **Adding noise to returned scores** raises the number of queries needed, degrading the estimate.
- **Adversarial training** still helps, since the final perturbation is a normal Linf one.

## Explain it to a non-expert

The attacker cannot see how the model thinks, but the model tells them how confident it is. By poking the input thousands of times with random tweaks and watching the confidence shift, they reverse-engineer which direction makes the model wrong, then push that way. It works without any inside access, but the flood of probing queries is noisy and easy to rate-limit.

## References

- Ilyas, Engstrom, Athalye, Lin (2018), *Black-box Adversarial Attacks with Limited Queries and Information*
- Wierstra et al. (2014), *Natural Evolution Strategies*
- HTB AI Red Teamer, black-box evasion material
- Related: [transfer / black-box](transfer-blackbox.md), [Boundary](boundary-attack.md), [PGD](pgd.md), [overview](00-overview.md)
