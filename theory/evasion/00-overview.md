# Adversarial Evasion: The Big Picture

> **In one sentence:** Evasion attacks add a tiny, carefully computed change to an input so a trained model gets the answer wrong, while a human sees almost no difference.

This page is a map, not a single attack. Read it first, then dive into the individual pages.

## What "evasion" means

A classifier is a function `f(x)` that maps an input `x` (an image, an email, a network flow) to a label. Evasion happens at **inference time**: the model is already trained and frozen, and the attacker only crafts a malicious input. The attacker does not touch the training data (that would be [data poisoning](../data_poisoning/)) and does not steal the weights (that would be model extraction). Evasion just asks: given this fixed model, what input makes it fail?

Formally the attacker looks for a perturbation `delta`:

```
f(x + delta) != f(x)      (untargeted: any wrong label)
f(x + delta) == t         (targeted: a specific chosen label t)
subject to  ||delta|| <= eps
```

The constraint `||delta|| <= eps` is what makes the attack sneaky. Without it you could just replace the image of a cat with an image of a dog. The whole game is to stay "small" under some norm while still flipping the decision.

## The two things you must fix before choosing an attack

Every evasion attack is defined by two choices: **the threat model** (how much you know) and **the norm** (what "small" means).

### 1. Threat model: how much access do you have

| Model | Attacker knows | Query cost | Realistic? |
|-------|----------------|-----------|------------|
| **White-box** | Full architecture, weights, gradients | 0 (you own the math) | Research benchmark, insider, open-weight model |
| **Black-box, score-based** | Confidence scores / probabilities per query | Hundreds to thousands | Public ML API returning probabilities |
| **Black-box, decision-based** | Top-1 label only | Thousands to tens of thousands | Hardened API returning just a class |
| **Transfer** | Nothing about the target; you attack your own surrogate | 0 against the target during crafting | Most realistic remote scenario |

White-box gives you the gradient directly, so attacks are cheap and strong (FGSM, PGD, DeepFool, C&W, JSMA). Black-box forces you to either estimate the gradient by querying ([NES](nes-score-based.md)), walk the boundary with labels only ([Boundary](boundary-attack.md)), or craft on a surrogate and hope it [transfers](transfer-blackbox.md).

### 2. Norm: what "small" means

The norm decides the *shape* of the perturbation.

| Norm | Counts | Visual signature | Typical eps |
|------|--------|------------------|-------------|
| **Linf** | Max change of any single feature | Faint uniform noise over the whole image | 8/255 on CIFAR, 0.3 on MNIST |
| **L2** | Euclidean length of the change vector | Diffuse, smooth noise | 0.5 to 2.0 |
| **L1** | Sum of absolute changes | Fewer, more concentrated changes | 5 to 20 |
| **L0** | Number of features changed | A handful of bright spots | 1 to 10 pixels |

Rule of thumb: **Linf and L2 = "change everything a little", L1 and L0 = "change a few things a lot"**. Linf/L2 attacks are the invisible-noise family. L1/L0 attacks are the sparse family (a sticker on a stop sign, one flipped byte).

## Taxonomy: how the attacks relate

```
                        Evasion Attacks
                        |
        +---------------+----------------+
        |                                |
     White-box                       Black-box
        |                                |
   +----+-----+                +---------+---------+
   |          |                |         |         |
 Gradient   Optimization   Transfer   Score     Decision
   |          |                |         |         |
 FGSM       C&W            surrogate   NES     Boundary
 BIM/IFGSM  EAD            + PGD      (est.    (label
 PGD                       + MI-FGSM   grad)    walk)
 MI-FGSM
 DeepFool
 JSMA (L0)
```

### The gradient family (white-box, Linf/L2)

These all use the gradient of the loss with respect to the *input pixels*. Training moves the weights to reduce loss; these attacks move the pixels to *increase* loss.

- **[FGSM](fgsm.md)**: one big step in the sign of the gradient. Fast, weak, the "hello world" of evasion.
- **[BIM / I-FGSM](bim-ifgsm.md)**: FGSM applied in many small steps. Stronger, deterministic.
- **[PGD](pgd.md)**: BIM plus a random start inside the eps-ball, plus restarts. The gold-standard robustness benchmark.
- **[MI-FGSM](mi-fgsm.md)**: BIM plus momentum. Same white-box strength but *transfers* far better to other models.

### The minimal-perturbation family

Instead of "use the whole eps budget", these find the *smallest* change that works.

- **[DeepFool](deepfool.md)**: repeatedly linearize the model and step to the nearest decision boundary. Gives a tight L2 perturbation, great for *measuring* robustness.
- **[C&W](carlini-wagner.md)**: cast the attack as an optimization that minimizes perturbation size while forcing a logit gap. Slow but extremely strong; breaks many defenses.

### The sparse family (L1/L0)

- **[JSMA](jsma.md)**: build a saliency map from the Jacobian and flip the single most impactful pixel, repeat. Very few pixels changed (L0).
- **[EAD](ead-elasticnet.md)**: C&W with an added L1 penalty, so the optimizer naturally zeroes out most coordinates (sparse like JSMA but via optimization).

### The black-box family

- **[Transfer](transfer-blackbox.md)**: craft on a surrogate you control, replay on the target. Zero target queries during crafting; boost success with MI-FGSM.
- **[NES score-based](nes-score-based.md)**: estimate the gradient from confidence scores using finite differences, then run PGD.
- **[Boundary](boundary-attack.md)**: start from an already-misclassified point and random-walk along the decision boundary toward the original, needing only hard labels.

### The text family

- **[GoodWord](goodword.md)**: for spam filters and content moderation. Insert benign words that additively drag the score across the decision threshold. White-box (read the model's word probabilities) or black-box (discover words by querying).

## Which page do I read

- I have the weights and want a fast baseline: [FGSM](fgsm.md).
- I have the weights and want the strongest standard Linf attack: [PGD](pgd.md).
- I want the smallest possible perturbation to *measure* robustness: [DeepFool](deepfool.md) or [C&W](carlini-wagner.md).
- I need to defeat a defended model: [C&W](carlini-wagner.md).
- I need a sparse / physical-world style perturbation: [JSMA](jsma.md) or [EAD](ead-elasticnet.md).
- The target is a remote API returning probabilities: [NES](nes-score-based.md) or [transfer](transfer-blackbox.md).
- The target returns only a label: [Boundary](boundary-attack.md).
- The target is a text classifier: [GoodWord](goodword.md).

## The toolkit at a glance

All commands run from the `ai-offensive-toolkit` root. The evasion scripts are:

| Script | Attacks it exposes |
|--------|--------------------|
| `evasion/fgsm_pgd.py` | FGSM, I-FGSM/BIM, PGD (Linf and L2), MI-FGSM, AutoPGD (via `--backend torchattacks`) |
| `evasion/deepfool.py` | DeepFool (per-image and batch) |
| `evasion/jsma_sparse.py` | JSMA (L0), EAD/ElasticNet (L1+L2), L1-PGD, C&W (via torchattacks) |
| `evasion/blackbox_evasion.py` | Transfer, NES score-based, Boundary |
| `evasion/goodword.py` | GoodWord for text classifiers (white-box and black-box) |
| `evasion/adversarial_training.py` | Defenses: PGD adversarial training, TRADES |

Note on invocation: `fgsm_pgd.py` and `goodword.py` ship a full argparse CLI, so `python -m evasion.fgsm_pgd --help` works. `deepfool.py`, `jsma_sparse.py`, and `blackbox_evasion.py` have smaller `__main__` demo blocks; for those the richest usage is importing the functions in Python, which each page shows.

## Detection and defense (shared themes)

- **Adversarial training** (train on PGD examples) is the strongest general defense and is implemented in `evasion/adversarial_training.py`.
- **Input transformations** (JPEG compression, bit-depth reduction, randomized resizing) blunt small Linf/L2 noise but are often bypassed by C&W and EAD.
- **Detection**: statistical tests on logits, feature squeezing, and neighbor-consistency checks catch many first-order attacks but struggle against minimal-perturbation and adaptive attacks.
- **Rate limiting and query monitoring** are the main defense against score-based and boundary attacks, which need many queries.

See [AI defense](../defense/) for the defender side.

## Explain it to a non-expert

Machine learning models look at inputs in a different way than humans do, and that gap leaves tiny blind spots. An evasion attack finds the exact tiny nudge, invisible to us, that pushes an input across the model's hidden decision line so it confidently gives the wrong answer. Depending on how much we know about the model, we either compute that nudge directly from its internals or probe it from the outside until we find it.

## References

- Goodfellow et al. (2014), *Explaining and Harnessing Adversarial Examples*
- Madry et al. (2017), *Towards Deep Learning Models Resistant to Adversarial Attacks*
- Carlini and Wagner (2017), *Towards Evaluating the Robustness of Neural Networks*
- HTB AI Red Teamer, modules 08 to 10 (evasion foundations, first-order, sparsity)
