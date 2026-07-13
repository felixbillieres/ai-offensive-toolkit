# JSMA (Jacobian-based Saliency Map Attack)

> **In one sentence:** JSMA changes just a handful of the most influential pixels, one at a time, using a saliency map built from the model's Jacobian, producing a very sparse (few-pixel) attack.

## What it is

JSMA (Papernot et al., 2016) is a white-box, typically targeted, **sparse** attack measured in the L0 norm (number of pixels changed). Instead of nudging every pixel a little like [FGSM](fgsm.md)/[PGD](pgd.md), it changes a small number of pixels a lot. This makes it the conceptual ancestor of physical-world attacks like stickers on a stop sign, where you can only alter a limited region.

## The problem it exploits

Not all pixels matter equally. For any target class, some pixels strongly increase that class's score while decreasing others; those are the high-leverage pixels. JSMA exploits this by computing the full Jacobian (how every output class responds to every input pixel) and greedily editing only the pixels with the biggest, cleanest impact. It trades the invisibility of Linf noise for extreme sparsity: a few conspicuous changes instead of a faint wash over the whole image.

## Intuition

Think of a soundboard with hundreds of sliders feeding two output meters: "target" and "everything else". You want the target meter to win. Most sliders barely move the meters, but a few push the target meter up *and* pull the others down at the same time. JSMA finds the single best such slider, pushes it to its limit, then re-measures and finds the next best, repeating until the target wins. You touch as few sliders as possible, but the ones you touch you push hard.

## How it works

```
loop until predicted == target OR pixel budget reached:
    J = Jacobian of the model outputs w.r.t. every input pixel   # shape (classes, pixels)
    for each pixel i still in play:
        a_t(i) = dF_target / dx_i                 # effect on the target class
        a_o(i) = sum_{j != target} dF_j / dx_i    # effect on all other classes
        # a "good" pixel raises target and lowers others:
        S(i) = a_t(i) * |a_o(i)|   if a_t(i) > 0 and a_o(i) < 0,  else 0
    pick pixel i* = argmax S(i)
    push x[i*] toward clip_max (by step theta)
    if x[i*] hits its bound, remove it from the search space
```

Each iteration adds exactly one pixel to the perturbation set, so the final L0 (pixel count) is small and directly controlled by the budget. The toolkit's `saliency_map` implements the `S(i)` formula above, and `jsma_attack` runs the greedy loop.

## Threat model and prerequisites

- **Access:** white-box (needs the full Jacobian, one backward pass per class per step, so it is compute-heavy).
- **Query budget:** up to `max_pixels` iterations (default 10% of the image), each computing `num_classes` gradients.
- **Norm:** L0 (counts changed pixels). Amplitude per pixel can be large.
- **Mode:** targeted (you pick the class to steer toward); the toolkit's `jsma_attack` takes a `target_class`.

## When to use it

Use JSMA when:

- You need a **sparse** perturbation: few pixels changed, e.g. to model a sticker, a patch, or a limited-write scenario.
- You are studying **which features** the model relies on (the saliency map is interpretable).

Prefer [EAD](ead-elasticnet.md) if you want sparsity via optimization (often more efficient and it scales better than the per-pixel Jacobian loop). Prefer [DeepFool](deepfool.md)/[C&W](carlini-wagner.md) for minimal *L2* perturbations. Prefer [PGD](pgd.md) for standard invisible Linf attacks. Note JSMA's Jacobian cost grows with the number of classes, so it is best on small-class problems like MNIST.

## Step by step with the toolkit

`jsma_sparse.py` runs a per-image JSMA demo:

```bash
python -m evasion.jsma_sparse --attack jsma --target 3 --batch-size 8
```

This prints, per image, `true_label -> predicted (N pixels changed)`.

In Python:

```python
from evasion.jsma_sparse import jsma_attack, compute_jacobian, saliency_map

adv_image, pixels_changed, pred = jsma_attack(
    model, image, target_class=3, num_classes=10,
    max_pixels=None,   # default 10% of pixels
    theta=1.0)         # push direction/size per pixel
```

Key parameters: `target_class`, `max_pixels` (the L0 budget), `theta` (per-pixel step, sign sets increase vs. decrease), `num_classes`.

## Detection and defense

- Sparse, high-amplitude changes are **visually and statistically conspicuous** (bright spots), so simple anomaly detection and spatial-smoothness checks catch many JSMA examples.
- **Median filtering / spatial smoothing** can erase isolated changed pixels, reversing the attack.
- **Adversarial training** helps but is less commonly done against L0 than against Linf.

## Explain it to a non-expert

Most attacks change every pixel a tiny bit; JSMA does the opposite. It figures out the few most powerful pixels, the ones that most push the model toward a chosen wrong answer, and changes only those. It is like flipping a small number of critical switches instead of adjusting everything, which is how real-world tricks such as a small sticker on a road sign fool a vision system.

## References

- Papernot, McDaniel, Jha, Fredrikson, Celik, Swami (2016), *The Limitations of Deep Learning in Adversarial Settings*
- HTB AI Red Teamer, module 10 (sparsity), Jacobian Saliency Map section
- Related: [EAD / ElasticNet](ead-elasticnet.md), [C&W](carlini-wagner.md), [DeepFool](deepfool.md), [overview](00-overview.md)
