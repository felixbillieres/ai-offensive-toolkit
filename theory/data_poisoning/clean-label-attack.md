# Clean Label Attack

> **In one sentence:** Poison the features of a few training samples while leaving every label correct, so a human or automated label audit sees nothing wrong yet the model still learns to misclassify a chosen target.

## What it is

A clean label attack is the opposite trade-off from [label flipping](label-flipping.md). There you changed the answers and left the inputs alone. Here you leave the answers correct and quietly perturb the inputs. Because every label matches its (perturbed) sample, the dataset passes label inspection. The corruption lives in the pixels or feature values, where nobody thinks to look.

| | Label flipping | Clean label attack |
|-------------------------|-----------------------|--------------------------|
| Labels modified | Yes | No |
| Features modified | No | Yes |
| Labels look correct | No | Yes |
| Goal | General degradation | Targeted misclassification |
| Detection | Easier | Harder |

Two variants ship in the toolkit:

- **Feature collision** (Shafahi et al., 2018, "Poison Frogs"): use gradient descent to perturb target-class samples until their internal feature representation collides with source-class samples, while the pixels stay within a small epsilon of the original.
- **Watermark:** the simpler cousin. Blend a faint watermark of the source class into target-class images.

## The problem it exploits

Models classify by the features they extract, not by raw pixels. Two inputs that look different to a human can sit on top of each other in the model's feature space. A clean label attack exploits exactly this gap: it makes a sample that *looks* like class T (so the label T is honest and correct) but *feels* like class S in feature space. To fit these contradictory points, the model must bend its decision boundary, and the bent boundary sweeps up the attacker's chosen target and misclassifies it.

## Intuition

Think of the feature space as a map with countries (classes) drawn on it. Normally each training point sits inside its own country. A clean label attack takes a few points that are honestly citizens of country T (correct label) and drags them, in feature space, deep into country S's territory, without changing their passport (label). When the model retrains, it has to redraw the border to keep those "T citizens standing in S" on the T side, and that redrawn border now cuts through where the target sample lives, flipping the target's classification.

Because the pixel change is tiny (feature collision) or a faint overlay (watermark), a reviewer flipping through the images sees normal, correctly labeled examples.

## How it works

Feature collision (the toolkit's `poison_with_feature_collision`):

1. Train or obtain a model to use as the feature extractor.
2. Compute the **source-class feature centroid** (average penultimate-layer features of source samples).
3. Start from the target-class samples you will poison.
4. Iterate: register a hook on the penultimate layer, push the poisoned samples' features toward the source centroid by gradient descent on the input, minimizing
   `||phi(x_poison) - phi(x_source)||^2`.
5. After each step, **project** back so the perturbation stays within `+/- eps` of the original pixels and inside `[0, 1]`. This keeps the image visually a target-class image.
6. Insert the perturbed samples back into the training set with their **original (correct) labels**.

Watermark (the toolkit's `watermark_attack`):

- `x_poison = (1 - alpha) * x_target + alpha * x_source_centroid`, clamped to `[0, 1]`. A low `alpha` keeps the blend subtle.

The linear-model version taught in the course makes the geometry explicit: find the source-class neighbors nearest the target, push them across the decision boundary in the direction opposite the boundary normal, and leave their labels unchanged so retraining must move the boundary to accommodate them.

## Threat model and prerequisites

- **White-box or surrogate access** helps a lot: feature collision needs a model whose penultimate features you can read and backpropagate through. A surrogate with a similar architecture often transfers.
- **Injection capability:** you must get your perturbed samples into the training set (a scraped source, a labeling batch, a contributed dataset).
- **Low poison rate is the point:** clean label attacks are meant to be stealthy, so poison rates are typically a few percent.

## When to use it

- You need a **targeted** misclassification and you expect the defender to audit labels (so [label flipping](label-flipping.md) would be caught).
- You can perturb inputs but you cannot get obviously wrong labels past review.
- You want a foundation for a stealthier attack that still passes clean-accuracy evaluation.

## Step by step with the toolkit

Feature collision, source 7, target 1, poison 5 percent of the target samples:

```
python -m data_poisoning.clean_label_attack --source 7 --target 1 --poison-rate 0.05 --method collision
```

Watermark variant:

```
python -m data_poisoning.clean_label_attack --source 7 --target 1 --poison-rate 0.05 --method watermark
```

Available flags (read `data_poisoning/clean_label_attack.py`):

- `--source` source class integer (default `7`)
- `--target` target class integer (default `1`)
- `--poison-rate` fraction of target-class samples to perturb (default `0.05`)
- `--eps` maximum per-pixel perturbation for feature collision (default `0.3`)
- `--method {collision,watermark}` (default `collision`)
- `--epochs` epochs for the brief pre-training used as feature extractor (default `10`)

The script prints the feature distance shrinking over the optimization steps, then confirms the labels remain the target class while the feature representation now resembles the source class.

## Detection and defense

- **Feature-space anomaly detection:** cluster penultimate-layer activations per class and flag samples whose features are far from their labeled class centroid (or suspiciously close to another class's).
- **Spectral signatures / activation clustering:** poisoned samples often form a detectable subspace in the covariance of activations.
- **Input provenance and deduplication:** restrict who can contribute training data; watch for near-duplicate targets.
- **Adversarial training and randomized smoothing** reduce sensitivity to small feature perturbations.
- **Note:** label audits do **not** work here, which is the whole point.

## Explain it to a non-expert

Imagine training a guard dog to tell your family from strangers using photos. An attacker takes a few photos that are genuinely of your family (so the caption "family" is truthful) and subtly edits them, adding faint traces that only a computer notices, so that to the dog's brain they smell like a specific stranger. The dog, trying to make sense of "family members who smell like this stranger," ends up deciding that stranger is family too, and lets them in. Every photo was honestly labeled, so when you check the captions, nothing looks wrong.

## References

- Shafahi et al. (2018), *Poison Frogs! Targeted Clean-Label Poisoning Attacks on Neural Networks*
- Turner et al. (2019), *Label-Consistent Backdoor Attacks*
- See also: [overview](00-overview.md), [label flipping](label-flipping.md), [trojan backdoor](trojan-backdoor.md)
