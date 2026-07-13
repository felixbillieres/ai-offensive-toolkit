# Membership Inference Attack

> **In one sentence:** Given a record you already hold, membership inference decides whether that exact record was in a model's training set, by reading the tell tale overconfidence a model shows on data it has seen before.

## What it is

Membership inference answers a single yes/no question: "Was data point `x` part of the training set of this model?" The output is one bit, member or non member. It is the lowest rung on the privacy attack ladder (see the [overview](./00-overview.md)), which is exactly why it matters: it needs the least information and access, and it is often the first observable sign that a model is leaking. If a model fails membership inference, assume it leaks other things too.

This toolkit implements three variants, from simplest to most powerful:

1. **Metric based** (confidence threshold): no training required.
2. **Loss based** (loss threshold): needs true labels, slightly stronger.
3. **Shadow model** (Shokri et al., 2017): train a dedicated attack classifier, most powerful and most involved.

## The problem it exploits

Gradient descent minimizes loss on the training set. After enough iterations the model does not just learn general patterns, it memorizes idiosyncrasies of individual training samples. That memorization is directly observable at inference time:

```
Member     -> softmax [0.05, 0.95]   the model was optimized on this point
Non-member -> softmax [0.20, 0.80]   never seen during training
```

Two signals leak out:

- **Confidence**: members receive more confident predictions.
- **Correctness**: models are more accurate on their own training data (the overfitting gap).

The attack is a classifier over these signals. The wider the train/test accuracy gap, the more the two populations separate, and the easier the attack.

## Intuition

Imagine a student who crammed by memorizing a specific practice exam. On questions from that exact exam they answer instantly and with total certainty. On brand new questions covering the same material they are slower and hedge. If you watch only their confidence, you can guess which questions were on the practice exam. A model is that student, its softmax output is the confidence, and membership inference is you watching.

## How it works

### Metric based

The simplest possible attack. No training, no shadow models.

```
if max(softmax(f(x))) > threshold:
    return "member"
else:
    return "non-member"
```

The model is systematically more confident on training data, so a high maximum softmax probability suggests membership. You pick the threshold empirically. Cheap, but the least accurate, because a confidently wrong prediction on a non member fools it.

### Loss based

Slightly smarter. Training samples have lower loss than unseen samples, so:

```
if cross_entropy(f(x), y_true) < threshold:
    return "member"
```

This needs the true label `y`, but it is a stronger signal than raw confidence because it accounts for whether the confident prediction was actually correct. Effective on overfitted models.

### Shadow model (Shokri et al., 2017)

The core problem: you do not know the target's training set, so you have no labeled member/non member examples to learn from. The shadow model trick manufactures them.

```
1. SHADOW MODELS
   Train K shadow models with the same architecture as the target,
   on data subsets you control -> you KNOW which points are members.

2. COLLECT ATTACK DATA
   For each shadow model:
     predictions on its training data   -> label "member"
     predictions on its held-out data   -> label "non-member"

3. ATTACK CLASSIFIER
   Input : concat(softmax_probs, one_hot(true_label))
   Output: member (1) or non-member (0)
   Train it on the data gathered in step 2.

4. ATTACK THE TARGET
   Query the target model with x, get its softmax output,
   feed (softmax, one_hot(true_label)) into the attack classifier
   -> member / non-member decision.
```

Why concatenate the one hot true label into the attack input? Different classes overfit by different amounts (a rare class may be memorized harder than a common one), so telling the classifier which class it is looking at sharpens the decision.

Why it transfers: if the shadow models overfit the same way the target does (same architecture, same training procedure, same data distribution), then a classifier trained on shadow behavior generalizes to the target. This is the **similarity hypothesis**, and it is also the attack's weak point: a shadow CNN against a target Transformer, or a shadow on CIFAR against a target on medical data, will fail because the overfitting patterns do not match.

### Evaluating the attack

The toolkit reports accuracy, precision, recall, and AUC-ROC against a random baseline of 50% accuracy / 0.5 AUC. Anything meaningfully above that baseline means the model is leaking membership.

## Threat model and prerequisites

| Assumption | Detail |
|---|---|
| **Access** | Black box: submit inputs, receive softmax outputs. |
| **Queries** | One per target record for metric/loss; shadow training is fully offline and never touches the target. |
| **Data** | For shadow and loss attacks, access to data from the same distribution (a neighboring hospital, a public dataset) and true labels. |
| **Detectability** | Attack queries are identical to legitimate ones, so they are effectively invisible. |

Comparison of the three variants:

| Method | Complexity | Accuracy | Prerequisites |
|---|---|---|---|
| Metric based | Very low | Moderate | An empirical threshold |
| Loss based | Low | Good | True labels |
| Shadow model | High | High | Similar distribution + matching architecture |

## When to use it

- **Compliance / consent proof**: demonstrate a specific individual's data was used to train a model (GDPR, medical data, copyright).
- **First vulnerability probe**: run it early in a red team engagement as a cheap signal of whether deeper privacy attacks (inversion, extraction) are worth attempting.
- **Auditing overfitting**: a strong membership signal is direct evidence the model overfit and needs regularization or [DP-SGD](../defense/dp-sgd.md).

Start with metric based (zero setup). If the signal is weak but you suspect leakage, escalate to loss based, then shadow models.

## Step by step with the toolkit

The script is `privacy/membership_inference.py`. It downloads MNIST, trains a small CNN target on a 2000 sample subset, then runs the chosen attack. Flags: `--method {shadow,metric,loss}`, `--threshold`, `--shadow-count`, `--epochs`.

Metric based attack (default method), confidence threshold 0.9:

```bash
python -m privacy.membership_inference --method metric --threshold 0.9
```

Loss based attack, membership if loss is below 1.0:

```bash
python -m privacy.membership_inference --method loss --threshold 1.0
```

Shadow model attack with 5 shadow models:

```bash
python -m privacy.membership_inference --method shadow --shadow-count 5
```

Make the target overfit harder (more epochs) to see the attack get stronger:

```bash
python -m privacy.membership_inference --method shadow --shadow-count 5 --epochs 30
```

Interpreting the output: the script prints member vs non member average confidence/loss, then accuracy, precision, recall, and AUC-ROC with the random baseline (50% / 0.5) for reference. A larger gap between member and non member averages, and an AUC well above 0.5, mean stronger leakage.

Programmatic use (the functions are exported from the package):

```python
from privacy import shadow_model_attack, metric_based_attack, loss_based_attack
```

## Detection and defense

Detection is hard because the queries are indistinguishable from normal traffic. Realistic mitigations target the leakage itself:

- **Reduce overfitting**: early stopping, dropout, weight decay. Shrinks the member/non member gap but does not close it.
- **Limit output granularity**: return top-1 label only, or coarse/rounded confidences, to starve metric and shadow attacks of signal. (Label-only attacks still exist but are weaker.)
- **[DP-SGD](../defense/dp-sgd.md)**: the principled defense. Clipping per sample gradients and adding calibrated noise flattens the confidence distributions and provides a formal (epsilon, delta) bound on how much any single record can influence the model. Lower epsilon means stronger privacy but lower accuracy.
- **[PATE](../defense/pate.md)**: train on noisily aggregated teacher labels so the released model never directly sees any private record.

## Explain it to a non-expert

A model is like a student who studied for a test. On questions that were on their study sheet, they answer super fast and are totally sure. On new questions they hesitate a bit. If I show the model a photo and it answers with suspicious certainty, I can guess that photo was one it studied, that is, one of its training examples. Membership inference is just measuring that certainty to figure out what was on the study sheet. The scary part: the study sheet might be private medical records, and knowing someone was "on the sheet" can reveal they have a disease.

## References

- Shokri, Stronati, Song, Shmatikov (2017), *Membership Inference Attacks Against Machine Learning Models*.
- Yeom et al. (2018), *Privacy Risk in Machine Learning: Analyzing the Connection to Overfitting* (loss based / threshold attacks).
- Carlini et al. (2022), *Membership Inference Attacks From First Principles* (likelihood ratio, LiRA).
- Abadi et al. (2016), *Deep Learning with Differential Privacy* (defense).
