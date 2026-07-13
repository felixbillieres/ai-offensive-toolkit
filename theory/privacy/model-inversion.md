# Model Inversion Attack

> **In one sentence:** Model inversion starts from noise and runs the model's own gradients backward to synthesize an input the model strongly associates with a target class, reconstructing a representative training input without ever holding the training data.

## What it is

Where [membership inference](./membership-inference.md) only decides yes/no about a record you already have, model inversion *generates* a new input. It answers: "What does a typical training example of class `c` look like?" You feed nothing in but a target class label, and out comes a synthetic image (or feature vector) that captures the aggregate pattern the model learned for that class.

Two settings are covered by this toolkit:

1. **Gradient based inversion** (Fredrikson et al., 2015): black box style, optimize an input to maximize class confidence. Produces a representative, not an exact sample.
2. **Gradient leakage / DLG** (Zhu et al., 2019): a federated learning attack that reconstructs the *exact* training batch from the shared gradients.

## The problem it exploits

A classifier defines, for every class, a region of input space it scores highly. Because the model overfit, the highest scoring point for class `c` is pulled toward the actual training examples of `c`. So if you search input space for whatever the model is most confident is a `c`, you drift toward the memorized appearance of `c`.

For federated learning the leak is even more direct: the whole point of federated learning is that clients share **gradients** instead of raw data, believing gradients are safe. They are not. A gradient computed from a specific batch contains enough information to invert back to that batch.

## Intuition

**Gradient inversion**: think of the model as a landscape where altitude is "confidence that this is a 6." Normally you feed in an image and read the altitude. Inversion flips the arrows: you stand on random noise and walk uphill until you reach the peak of "6." The peak looks like the platonic 6 the model built from all the 6s it memorized, so it leaks their shared features.

**DLG**: imagine someone hands you the exact answer to "how much would the model's weights need to change to fit one secret photo?" That change (the gradient) is so specific to the photo that you can reverse engineer the photo itself by trying candidate images until one produces the same required change.

## How it works

### Gradient based inversion (Fredrikson et al., 2015)

You optimize the *input* while holding the model's weights fixed:

```
x* = argmax_x  P(class = c | x)  -  lambda_tv * TV(x)  -  lambda_l2 * ||x||^2
```

Step by step:

1. Initialize `x` as random noise (a tensor with `requires_grad=True`).
2. Forward pass the current `x` through the frozen model.
3. Compute a class loss that *rewards* high confidence in the target class (in the toolkit: `-cross_entropy(output, target_class)`).
4. Add regularizers so the result looks like a plausible input, not adversarial static:
   - **Total variation (TV)**: penalizes pixel to pixel jitter, encouraging smooth images.
   - **L2**: penalizes extreme pixel magnitudes.
5. Backpropagate to the input and take an optimizer step on `x`.
6. Clamp `x` to the valid range (0 to 1) and repeat for `steps` iterations.

The result is not an exact training sample. It is a class prototype: it reveals the aggregate features (the shape of a face, the stroke of a digit) the model associates with the class. On a face recognition model trained per person, that prototype can look uncomfortably like a real individual.

### Gradient leakage (DLG, Zhu et al., 2019)

This attack lives in federated learning, where clients send gradients to a server:

```
Given: gradient_shared = dLoss/dW for some private (x, y)
Find : dummy_x, dummy_y  such that  dLoss/dW(dummy_x, dummy_y) ~= gradient_shared
```

Step by step:

1. Initialize dummy data `dummy_x` and dummy labels `dummy_y` as random tensors that require gradients.
2. Forward `dummy_x` through the model, compute its loss, then compute the gradient of that loss with respect to the model weights (with `create_graph=True`, so this gradient is itself differentiable).
3. Measure the squared distance between the dummy gradient and the true shared gradient.
4. Add TV regularization for image plausibility.
5. Backpropagate that gradient distance all the way back to `dummy_x` and `dummy_y`, and step an optimizer (the toolkit uses LBFGS) to shrink the distance.
6. Repeat. As the dummy gradient converges to the real one, `dummy_x` converges to the real training input, often pixel accurate.

This is devastating: it breaks the core privacy promise of federated learning. If labels are known, only `dummy_x` is optimized, which converges faster and more reliably.

## Threat model and prerequisites

| Attack | Access needed | What you recover |
|---|---|---|
| Gradient based inversion | White box (need to backprop through the model to the input) and a target class label | A representative prototype per class |
| DLG | The per step gradients shared in federated training, plus the model architecture | The exact training batch (input and label) |

Gradient inversion needs the model itself (gradients through it), so it is a white box attack, unlike the black box membership attacks. DLG needs the specific artifact federated learning exposes: gradients.

## When to use it

- **Demonstrate catastrophic leakage**: showing a recognizable reconstructed face is far more visceral in a report than an AUC number.
- **Audit federated learning**: run DLG to prove that "we only share gradients, not data" is not a privacy guarantee, and to justify secure aggregation or [DP-SGD](../defense/dp-sgd.md).
- **Probe class prototypes**: use per class inversion to understand what a classifier actually keyed on (it may reveal spurious or sensitive features).

Reach for inversion after membership inference has already signaled leakage; it is the heavier, higher payoff follow up.

## Step by step with the toolkit

The script is `privacy/model_inversion.py`. It trains a small MNIST CNN, then inverts. Flags: `--target-class`, `--steps`, `--lr`, `--tv-weight`, `--all`, `--save`.

Invert a single class (the digit 3) for 1000 optimization steps:

```bash
python -m privacy.model_inversion --target-class 3 --steps 1000
```

Invert every class and save a side by side grid of reconstructed versus real samples:

```bash
python -m privacy.model_inversion --all --steps 1000 --save inversions.png
```

Tune the smoothness regularizer and learning rate (higher `--tv-weight` gives smoother, less noisy images):

```bash
python -m privacy.model_inversion --target-class 7 --steps 2000 --lr 0.1 --tv-weight 0.005
```

Interpreting the output: the script prints the target class confidence every 200 steps (it should climb toward 1.0), then visualizes the reconstruction. Compare the inverted image to the real sample the script displays beside it: legible resemblance means strong leakage.

The DLG / federated attack is exposed as a function rather than a CLI flag. Use it programmatically:

```python
from privacy import federated_gradient_inversion
# federated_gradient_inversion(gradients, model, input_shape, labels=None, steps=500, lr=0.1, tv_weight=0.01)
```

The other entry points are also exported from the package:

```python
from privacy import gradient_inversion, batch_inversion
```

## Detection and defense

- **Restrict access**: gradient inversion needs white box gradients, so simply not exposing model internals blocks it. For deployed APIs, return only top-1 labels, not gradients or full confidence vectors.
- **Secure aggregation** (federated learning): the server only ever sees a sum of many clients' gradients, not any individual gradient, which starves DLG of its input.
- **Gradient compression / pruning and larger batch sizes**: make DLG reconstruction harder and blurrier (partial mitigations, not guarantees).
- **[DP-SGD](../defense/dp-sgd.md)**: clip and add noise to gradients. This is the principled defense for both variants: it bounds how much any single training point shapes the weights (and thus the reconstruction), with a formal (epsilon, delta) guarantee. The noise directly disrupts the exact gradient matching that DLG relies on.
- **[PATE](../defense/pate.md)**: since the released student model never trains directly on private data, there is far less memorized detail to invert.

## Explain it to a non-expert

To recognize a cat, a model built an internal idea of "cat" by studying many cat photos. Model inversion asks the model to *draw* its idea of a cat: you start from TV static and keep nudging the pixels toward whatever the model shouts "cat!" at, until a ghostly cat appears. That ghost is stitched together from the real cats it memorized, so private images can bleed through. The federated version (DLG) is worse: in setups where phones share "study notes" instead of your actual photos, those notes turn out to be detailed enough to redraw your original photo almost exactly.

## References

- Fredrikson, Jha, Ristenpart (2015), *Model Inversion Attacks that Exploit Confidence Information and Basic Countermeasures*.
- Zhu, Liu, Han (2019), *Deep Leakage from Gradients* (DLG).
- Geiping et al. (2020), *Inverting Gradients: How Easy Is It to Break Privacy in Federated Learning?*
- Zhang et al. (2020), *The Secret Revealer: Generative Model Inversion Attacks* (GAN based, GMI).
- Abadi et al. (2016), *Deep Learning with Differential Privacy* (defense).
