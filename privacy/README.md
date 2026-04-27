# AI Privacy Attacks & Defenses

Privacy attacks extract information about training data from trained models. Even without access to the training set, an attacker can determine if specific data was used for training, or reconstruct approximate training samples.

## Theory

### Why Models Leak Information

Neural networks memorize training data to varying degrees. A model that achieves 99% training accuracy but 90% test accuracy has clearly memorized patterns specific to training samples. This memorization leaks through:

- **Confidence scores**: Higher confidence on training data
- **Loss values**: Lower loss on training data
- **Gradient behavior**: Different gradient patterns for seen vs unseen data
- **Output distributions**: Sharper distributions on training data

### Attack Taxonomy

```
Privacy Attacks
├── Membership Inference
│   ├── Metric-based (confidence threshold)
│   ├── Shadow model (train attack classifier)
│   └── Loss-based (loss threshold)
│
├── Model Inversion
│   ├── Gradient-based (maximize class confidence)
│   ├── GAN-based (GMI)
│   └── Gradient leakage (federated learning — DLG)
│
├── Data Extraction
│   ├── Training data extraction from LLMs
│   └── Memorization probing
│
└── Attribute Inference
    └── Infer sensitive attributes from model behavior
```

### Membership Inference

**Question**: "Was data point `x` in the training set?"

**Why it matters**: Proves someone's data was used without consent (GDPR, medical data), reveals participation in sensitive datasets.

#### Metric-based Attack

Simplest approach: if the model's confidence on `x` exceeds a threshold → member.

```
if max(softmax(f(x))) > threshold:
    return "member"
else:
    return "non-member"
```

Works because models are systematically more confident on training data (overfitting signal).

#### Shadow Model Attack (Shokri et al., 2017)

1. **Train shadow models** that mimic the target model's behavior
2. For each shadow model, you know which data is member/non-member
3. **Collect (confidence_vector, membership_label)** pairs
4. **Train a binary attack classifier** on this data
5. Apply the attack classifier to the target model's outputs

```
Target model outputs: softmax([0.1, 0.8, 0.05, 0.05]) on input x
Attack classifier: "This confidence pattern looks like a member" → MEMBER
```

#### Loss-based Attack

Training data typically has lower loss than unseen data:
```
if L(f(x), y) < threshold:
    return "member"
```

Simple but effective, especially on overfitted models.

### Model Inversion

**Question**: "What does a typical training sample of class `c` look like?"

Start from random noise and optimize it to maximize the model's confidence for the target class:

```
x* = argmax_x  P(class=c | x) - λ_tv · TV(x) - λ · ||x||²
```

Where `TV(x)` is total variation (smoothness regularizer).

The reconstructed image won't be an exact training sample, but it reveals aggregate patterns — faces, digits, features — that the model learned.

#### Gradient Leakage (DLG — Zhu et al., 2019)

In federated learning, clients share gradients instead of data. But gradients contain enough information to reconstruct the original training data:

```
Given: ∇W (shared gradients)
Find:  x, y  such that  ∇_W L(f(x;W), y) ≈ ∇W_shared
```

This is devastating for federated learning's privacy guarantees.

### Defenses

#### DP-SGD — Differentially Private SGD (Abadi et al., 2016)

Modify the training process to provide formal privacy guarantees:

1. **Clip** per-sample gradients to bounded norm `C`
2. **Add** calibrated Gaussian noise: `σ ∝ C · noise_multiplier`
3. **Update** with noisy averaged gradients

Privacy guarantee: (ε, δ)-differential privacy — the model's behavior changes by at most ε whether or not any single training point is included.

**Trade-off**: Lower ε (stronger privacy) = lower accuracy. Typical ε values: 1-10.

#### PATE — Private Aggregation of Teacher Ensembles (Papernot et al., 2017)

1. **Partition** sensitive training data among `n` teacher models
2. Each teacher votes on **public unlabeled data**
3. **Add Laplace noise** to vote counts
4. Train a **student model** on the noisy labels

The student never sees the private data directly. Privacy is consumed only when querying teachers, and noisy aggregation bounds the leakage.

```
Teachers:  T1 votes "cat", T2 votes "cat", T3 votes "dog"
Votes:     cat=2, dog=1
+ noise:   cat=2.3, dog=1.7
Label:     "cat" (noisy argmax)
Student learns from this noisy label
```

## Scripts

| Script | Description |
|--------|-------------|
| `membership_inference.py` | Three attack methods: shadow model (Shokri et al.), metric-based (confidence threshold), and loss-based. Full pipeline with sklearn metrics (accuracy, precision, recall, AUC-ROC). |
| `model_inversion.py` | Gradient-based inversion with TV regularization, batch inversion for all classes, and DLG gradient leakage attack for federated learning scenarios. |
| `dp_defenses.py` | DP-SGD implementation (manual + Opacus wrapper) and PATE with configurable noise, number of teachers, and consensus filtering. |

## References

- Shokri et al. (2017) — *Membership Inference Attacks Against Machine Learning Models*
- Fredrikson et al. (2015) — *Model Inversion Attacks that Exploit Confidence Information*
- Zhu et al. (2019) — *Deep Leakage from Gradients* (DLG)
- Abadi et al. (2016) — *Deep Learning with Differential Privacy* (DP-SGD)
- Papernot et al. (2017) — *Semi-supervised Knowledge Transfer For Deep Learning from Private Training Data* (PATE)
