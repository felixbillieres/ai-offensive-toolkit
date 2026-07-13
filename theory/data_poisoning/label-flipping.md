# Label Flipping

> **In one sentence:** Change the labels (the correct answers) on part of the training set without touching the inputs, so the model learns wrong associations.

## What it is

Label flipping is the simplest data-poisoning attack. You leave every input (image, text, feature vector) exactly as it is and you corrupt only the ground-truth label attached to it. The model, trusting its labels completely, dutifully learns whatever you tell it.

```
Original:  (image_of_7, label=7)
Poisoned:  (image_of_7, label=1)   -> model learns "7 looks like 1"
```

Three strategies, in increasing sophistication:

- **Random flipping** (availability): flip a random subset of labels to random other classes. Degrades overall accuracy.
- **Targeted flipping** (integrity): flip labels of source class A to target class B. The model learns to confuse A with B.
- **Confidence-based flipping** (availability, optimized): flip the labels the model is *most confident* about, because those are the most informative samples, so flipping them causes the most damage per flip.

## The problem it exploits

Supervised training assumes the labels are ground truth. There is no built-in mechanism that asks "is this label plausible given the input?" The loss function punishes the model for disagreeing with the label, so a wrong label is an authoritative instruction to learn a wrong pattern. The corruption enters at the storage stage (editing label columns in a CSV on S3 or rows in Postgres) or the processing stage (a compromised transform script that rewrites labels in flight).

## Intuition

Imagine a teacher grading with an answer key that someone secretly edited. The student is diligent and trusts the key, so they confidently learn the wrong answers. Random flipping scribbles over random answers (the student gets generally confused). Targeted flipping consistently swaps one specific answer (the student reliably gets that one topic backwards). Confidence-based flipping edits exactly the answers the student was surest about, maximizing the shock to their understanding.

## How it works

1. Decide the strategy and the **poison rate** (fraction of labels to flip).
2. Select which samples to flip:
   - Random: uniform random subset across the whole set.
   - Targeted: all (or a fraction of) samples currently labeled `source_class`.
   - Confidence-based: run a trained model, take the softmax max probability per sample, sort descending, take the top fraction.
3. Assign new labels:
   - Random: a random different class.
   - Targeted: the fixed `target_class`.
   - Confidence-based: the model's *least* likely class for that sample (maximum contradiction).
4. Train on the corrupted labels.
5. Measure the damage: overall accuracy drop, and for targeted attacks, the source-to-target misclassification rate.

## Threat model and prerequisites

- **Capability:** write access to the training labels, either directly in storage or via a compromised processing script. No model access is needed for random and targeted flips.
- **Confidence-based** additionally needs a trained (surrogate) model to score sample confidence.
- **Detectability:** higher poison rates hit harder but are trivially spotted by anyone auditing class balance or label distributions. Targeted flips distort the source class's proportion.

## When to use it

- You want a fast, low-sophistication availability attack to degrade a competitor or target model, and stealth is secondary.
- You want a targeted denial for one class (make the model unable to recognize "stop" reliably) without the complexity of a backdoor trigger.
- You are establishing a baseline before moving to stealthier [clean label](clean-label-attack.md) or [trojan](trojan-backdoor.md) attacks.

## Step by step with the toolkit

The script trains a clean baseline model, poisons the labels, retrains, and reports the accuracy drop (plus targeted misclassification for the targeted strategy).

Targeted flip, class 7 becomes class 1, 15 percent of the 7s:

```
python -m data_poisoning.label_flipping --strategy targeted --source 7 --target 1 --rate 0.15
```

Random flip, 20 percent of all labels:

```
python -m data_poisoning.label_flipping --strategy random --rate 0.20
```

Confidence-based flip, 10 percent of the most confident samples:

```
python -m data_poisoning.label_flipping --strategy confidence --rate 0.10
```

Available flags (read `data_poisoning/label_flipping.py`):

- `--strategy {random,targeted,confidence}` (default `targeted`)
- `--source` source class integer (default `7`, used by `targeted`)
- `--target` target class integer (default `1`, used by `targeted`)
- `--rate` poison rate as a fraction (default `0.15`)
- `--epochs` training epochs (default `5`)

Interpreting the output: `Accuracy drop` is the availability impact; `Source class N misclassified as M` is the integrity impact for targeted runs.

## Detection and defense

- **Label distribution audit:** flipping shifts class proportions. Compare against expected priors.
- **Label sanitization / relabeling:** train a model on trusted data, flag samples whose predicted label strongly disagrees with the stored label (loss or confidence outliers).
- **Robust training:** loss functions and reweighting schemes that downweight high-loss samples resist a fraction of flipped labels.
- **Provenance and access control:** sign datasets, restrict write access to label stores, and log who edits labels and transform scripts.
- **Cross-validation with clean holdout:** a trusted, uncontaminated validation set exposes availability drops early.

## Explain it to a non-expert

You are teaching a child with flash cards. On the back of each card is the answer. A prankster sneaks in and changes some of the answers on the backs of the cards. The child studies hard and trusts the cards, so they learn the wrong answers. If the prankster changes answers randomly, the child just gets generally worse. If the prankster always changes "dog" to "cat," the child ends up calling every dog a cat. You never touched the pictures on the front, only the answers on the back, and that was enough.

## References

- Biggio et al. (2012), *Poisoning Attacks against Support Vector Machines*
- OWASP LLM03 Training Data Poisoning
- See also: [overview](00-overview.md), [clean label attack](clean-label-attack.md), [trojan backdoor](trojan-backdoor.md)
