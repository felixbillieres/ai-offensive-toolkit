# DP-SGD (Differential Privacy via Noisy Gradient Descent)

> **In one sentence:** During training you clip each example's gradient to a fixed size and add calibrated random noise, so the finished model is provably almost the same whether or not any single person's record was in the training set, which means it cannot leak that person.

## What it is

DP-SGD (Abadi et al., 2016) is standard stochastic gradient descent modified to satisfy **differential privacy**. Differential privacy is a mathematical guarantee: for any two datasets that differ by exactly one record, the probability of producing any given model is almost the same.

```
P[M(D) in S]  <=  e^epsilon * P[M(D') in S]  +  delta

D, D'    : datasets differing by one individual
epsilon  : the privacy budget (smaller = stronger privacy)
delta    : tiny probability the guarantee fails (typically about 1/n)
```

The point: if adding or removing one person barely changes the output distribution, then no attacker, however powerful, can tell whether that person was in the data.

## The attack it stops

DP-SGD defends the **training data**, not the decision boundary. It provably limits:

- **Membership inference** ([../privacy/membership-inference.md](../privacy/membership-inference.md)): telling whether a specific record was in the training set.
- **Model inversion** ([../privacy/model-inversion.md](../privacy/model-inversion.md)): reconstructing training inputs from the model.
- **Memorization and verbatim leakage** of rare or sensitive records.

It does **not** stop evasion (see [adversarial-training.md](adversarial-training.md)) or LLM jailbreaks (see [llm-guardrails.md](llm-guardrails.md)).

## Intuition

A normally trained model memorizes. If one person's record is an outlier, its gradient can strongly steer the weights, leaving a fingerprint an attacker can detect and even invert. The record "shouts" through the gradients.

DP-SGD silences that shout in two moves. First, **clip** every per-example gradient to a maximum norm `C`, so no single record can push the weights more than a bounded amount, no matter how extreme. Second, **add noise** proportional to `C`, so the small remaining signal from any one record is drowned out. After clipping, the most any one person can change the gradient sum is `C`, which is exactly what lets you calibrate just enough noise to hide them.

## How it works

For each batch, DP-SGD replaces the plain gradient step with three operations (implemented in the toolkit's `train_dp_sgd`):

1. **Clip** each per-example gradient to L2 norm `max_norm` (`C`). If the norm exceeds `C`, scale it down so `||g_i|| <= C`. This bounds sensitivity to `C`.
2. **Add Gaussian noise** to the summed gradients: `noise ~ N(0, sigma^2 * C^2)` where `sigma = noise_multiplier`. More noise means more privacy and less accuracy.
3. **Average and update** with the noisy gradient.

```python
# toolkit: privacy/dp_defenses.py
clip_gradients(model, max_norm)                              # step 1
add_noise_to_gradients(model, noise_multiplier, max_norm, len(bx))  # step 2
optimizer.step()                                            # step 3
```

### The privacy budget epsilon

Every training step spends a slice of privacy. The total `epsilon` accumulates over all steps (composition). Naive composition just sums the per-step cost and is far too pessimistic; real accountants (Renyi DP / the moments accountant, used by Opacus) give a much tighter total.

Guide to `epsilon`:

```
epsilon = 1   very strong privacy (noticeable accuracy hit)
epsilon = 3   strong
epsilon = 10  moderate, keeps most utility
epsilon > 10  weak, mostly symbolic
```

More epochs mean more steps, which means more noise per step to hold the same final `epsilon`, which means lower accuracy. That is the fundamental knob.

`max_grad_norm` (`C`) is the other key parameter. Too small over-clips and loses information (strong privacy, slow convergence); too large lets outliers dominate (weak privacy). A practical starting point is the 75th percentile of gradient norms measured without DP.

## What it costs

- **Accuracy drops, sometimes a lot.** On CIFAR-10 the tradeoff is roughly: no DP about 85%, epsilon=10 about 70 to 75%, epsilon=3 about 55 to 65%, epsilon=1 about 40 to 55%.
- **The privacy budget is finite and spent.** Once you have used your `epsilon`, you cannot train longer or query more without weakening the guarantee.
- **Compute overhead.** True DP-SGD needs **per-example** gradients (not the usual batch-averaged gradient), which is memory heavy and slower. Libraries like Opacus optimize this but it is still a cost.
- **Sensitivity to hyperparameters.** `max_norm` and `noise_multiplier` interact and need tuning per dataset.

## When to use it

- You train on personal, medical, financial, or otherwise sensitive data and must guarantee individuals cannot be re-identified from the model.
- You need a **provable** bound that holds against unknown and future attacks, not just today's known ones.
- You can afford to trade some accuracy for privacy and can pick a defensible `epsilon` (regulatory or policy driven).

If you cannot tolerate the accuracy hit but still want privacy, consider [pate.md](pate.md), which sometimes reaches better accuracy at comparable `epsilon`.

## Step by step with the toolkit

The script is `privacy/dp_defenses.py`. It trains an MNIST CNN with DP-SGD and reports test accuracy so you can watch the privacy/utility tradeoff.

Manual DP-SGD, controlling the noise multiplier directly:

```bash
python -m privacy.dp_defenses --method dpsgd --noise 1.0 --max-norm 1.0 --epochs 10
```

Opacus-backed DP-SGD, targeting a specific privacy budget `epsilon` (prints the running `epsilon` each epoch):

```bash
python -m privacy.dp_defenses --method dpsgd_opacus --epsilon 1.0 --max-norm 1.0 --epochs 10
```

Flags (from the `argparse` block):

- `--method {dpsgd, dpsgd_opacus, pate}`  which defense.
- `--noise`  noise multiplier `sigma` for manual DP-SGD (default 1.0). Higher = more privacy, less accuracy.
- `--epsilon`  target privacy budget for the Opacus path (default 1.0).
- `--max-norm`  gradient clipping bound `C` (default 1.0).
- `--epochs`  training epochs (default 10). More epochs spend more budget.

Run it at `--noise 1.0` then `--noise 4.0` and watch accuracy fall as privacy rises. Then confirm the payoff by attacking both a normal model and the DP model with the membership inference script:

```bash
python -m privacy.membership_inference --help
```

The DP model should show a much smaller attacker advantage. See [../privacy/membership-inference.md](../privacy/membership-inference.md).

## Limitations and bypasses

- **The guarantee is worst-case and often loose.** An empirical membership inference attack usually leaks far less than the theoretical bound, so people are tempted to set `epsilon` high (10, 30, or more), at which point the guarantee is nearly meaningless while still costing accuracy.
- **Wrong `delta` or bad accounting.** Using naive composition, a too-large `delta`, or a buggy accountant can silently void the real guarantee.
- **Implementation gaps.** DP-SGD only protects what the gradients see. Data preprocessing, feature selection, or hyperparameter tuning done on the raw private data can leak outside the guarantee.
- **Per-example gradient bugs.** If clipping is applied to the batch gradient instead of per-example gradients, the math no longer holds. (Note: the toolkit's manual implementation clips the aggregated gradient for teaching simplicity; use Opacus for a correct per-sample guarantee.)
- **Does nothing against evasion or jailbreaks.** It is purely a data-privacy defense.

## Explain it to a non-expert

Imagine a survey where you want to report honest overall results without ever revealing what any single person answered. Before combining the answers you cap how much any one response can swing the total, then you stir in a little random noise. The averages still come out right, but if you look at the published result you genuinely cannot tell whether any particular person took part, because their single answer was capped and then hidden under the noise. DP-SGD does exactly this to a model's learning: cap each person's influence, add noise, and the trained model tells you useful things about the group while provably hiding every individual.

## References

- Abadi et al., 2016, "Deep Learning with Differential Privacy" (DP-SGD).
- Dwork and Roth, 2014, "The Algorithmic Foundations of Differential Privacy."
- Opacus library (PyTorch DP-SGD with RDP accounting).
- Course material: `11-ai-privacy/03_DP-SGD/`.
- Toolkit script: `privacy/dp_defenses.py`.
- Related pages: [pate.md](pate.md), [../privacy/membership-inference.md](../privacy/membership-inference.md), [../privacy/model-inversion.md](../privacy/model-inversion.md).
