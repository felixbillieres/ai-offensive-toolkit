# Privacy Attacks on Machine Learning: The Big Picture

> **In one sentence:** Trained models silently memorize their training data, and privacy attacks pull that memorized information back out, ranging from "was this record used?" all the way to "reconstruct the record itself."

## What "privacy leakage" means

When you train a model, you hope it learns general patterns: "handwritten loops that curve like this tend to be a 6." But gradient descent does not know when to stop. Alongside the general pattern, the model also absorbs idiosyncrasies of individual training samples. That extra, sample specific memorization is not needed to make good predictions on new data, but it stays baked into the weights. Privacy leakage is the gap between what the model *needed* to learn and what it *actually* memorized.

That leakage shows up in observable behavior:

- **Confidence scores**: the model is systematically more confident on data it trained on.
- **Loss values**: training samples have lower loss than unseen samples.
- **Gradient behavior**: gradients for seen versus unseen data look different.
- **Output distributions**: predictions are sharper (more peaked) on training data.

An attacker does not need the training set to exploit this. Black box query access to the model is often enough, and in federated learning even the shared gradients are enough.

## The four families of privacy attacks

Privacy attacks form a ladder. Each rung asks for more information than the one below it, and generally needs stronger access or more effort to pull off.

| Attack | The question it answers | Example impact |
|---|---|---|
| **Membership inference** | "Was record `x` in the training set?" | Prove someone's data was used without consent; reveal they were in a cancer study. |
| **Attribute inference** | "What is the value of a sensitive feature the model was never asked to predict?" | Infer education level from an income model. |
| **Model inversion / reconstruction** | "What does a typical training input for class `c` look like?" | Recover a representative face from a face recognition model. |
| **Training data extraction** | "Give me the exact, verbatim training record." | Pull a memorized credit card number or private paragraph out of an LLM. |

```
Privacy Attacks
|
|-- Membership Inference   -> yes/no: was x a member?
|   |-- metric based (confidence threshold)
|   |-- loss based (loss threshold)
|   |-- shadow model (train an attack classifier)
|
|-- Attribute Inference    -> value of a hidden sensitive attribute
|
|-- Model Inversion        -> a representative input per class
|   |-- gradient based (maximize class confidence)
|   |-- GAN based (GMI)
|   |-- gradient leakage in federated learning (DLG)
|
|-- Training Data Extraction -> verbatim memorized records (mostly LLMs)
```

### Membership vs reconstruction: the key distinction

These two are the ends of the spectrum and it is worth being precise:

- **Membership inference** is a *decision*. Output is one bit: member or non member. It only tells you whether a record you already hold was in the training set. Low information, low bar, often the first sign a model is vulnerable.
- **Reconstruction (model inversion)** is a *generation*. Output is a synthetic input. It does not reproduce an exact training sample (usually), but it reveals the aggregate visual or feature pattern the model associates with a class. Higher information, higher effort.

A useful mental model: if a model leaks membership, it very likely leaks other things too. Membership inference is the smoke; reconstruction and extraction are the fire.

## Why models leak: memorization versus generalization

Consider a binary classifier:

```
Member     -> [0.05, 0.95]   (95% confident)   the model was optimized on this exact point
Non-member -> [0.20, 0.80]   (80% confident)   never seen during training
```

Two signals fall out of this:

1. **Prediction confidence**: members get more confident predictions because the model directly minimized their loss.
2. **Prediction correctness**: models are more accurate on their own training data (the overfitting gap).

Combining them sharpens the signal:

```
High confidence + correct    -> strong MEMBER signal
High confidence + wrong       -> strong NON-MEMBER signal
Low confidence                -> ambiguous, the main source of attack errors
```

## What amplifies the vulnerability

- **Model capacity**: more parameters means more room to memorize.
- **Overfitting**: a large train/test accuracy gap means more leakage.
- **Atypical samples**: rare or near boundary examples get memorized harder, so they leak more.
- **Repetition**: samples seen many times are memorized more deeply.
- **Small datasets and many classes**: each class has fewer examples to blur into, so individual points stand out.

Regularization (dropout, weight decay, early stopping) reduces memorization but does not eliminate it.

## Threat model at a glance

Most attacks in this toolkit assume **black box** access: the attacker submits inputs and receives softmax outputs, nothing more. This is realistic for a public ML API. Key properties:

- **Cheap**: membership inference needs roughly one query per target record, well under API rate limits.
- **Stealthy**: attack queries look identical to legitimate queries, so they are hard to detect.
- **Offline heavy lifting**: shadow model training happens on the attacker's own machine and never touches the target.
- **Distribution access**: the attacker usually has data from the same population (a neighboring hospital, a public dataset).

Gradient leakage (DLG) is the exception: it assumes a **federated learning** setting where the attacker sees per step gradients.

## Where these attacks land in security frameworks

| Framework | Reference | Note |
|---|---|---|
| OWASP ML Top 10 | ML04:2023 (Membership Inference) | High exploitability rating |
| OWASP LLM Top 10 | LLM02 (Sensitive Information Disclosure) | Covers training data extraction |
| Google SAIF | Sensitive Data Disclosure | Recommends DP-SGD, PATE |

Every framework converges on the same primary countermeasure: **differential privacy**.

## The pages in this section

- [Membership Inference](./membership-inference.md): the yes/no attack, in three flavors (metric, loss, shadow model).
- [Model Inversion](./model-inversion.md): reconstructing representative inputs, plus gradient leakage (DLG) in federated learning.

## Defenses live elsewhere

The countermeasures (differential privacy via DP-SGD, and PATE) are documented in the defense section, not here:

- [DP-SGD](../defense/dp-sgd.md): clip per sample gradients and add calibrated noise for a formal (epsilon, delta) guarantee.
- [PATE](../defense/pate.md): train a student model on noisily aggregated labels from teachers that each saw only a slice of the private data.

## References

- Shokri et al. (2017), *Membership Inference Attacks Against Machine Learning Models*.
- Fredrikson et al. (2015), *Model Inversion Attacks that Exploit Confidence Information*.
- Zhu et al. (2019), *Deep Leakage from Gradients* (DLG).
- Carlini et al. (2021), *Extracting Training Data from Large Language Models*.
- Abadi et al. (2016), *Deep Learning with Differential Privacy* (DP-SGD).
- Papernot et al. (2017), *Semi-supervised Knowledge Transfer for Deep Learning from Private Training Data* (PATE).
