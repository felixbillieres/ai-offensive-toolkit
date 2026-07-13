# Boundary Attack (Decision-based Black-box)

> **In one sentence:** Start from an image that is already misclassified and random-walk it along the decision boundary, step by step shrinking the difference from your real target while never letting it cross back, using only the model's hard label.

## What it is

The Boundary Attack (Brendel et al., 2018) is a black-box, **decision-based** attack: it needs only the top-1 label, no scores and no gradients. It is the attack of last resort when the target reveals as little as possible. It starts from a point that is already classified as the wrong class and slowly walks it toward your original input, hugging the decision boundary so it stays misclassified while becoming visually closer to the original.

## The problem it exploits

Score-based attacks ([NES](nes-score-based.md)) need confidence numbers; transfer needs a surrogate. When the target gives you *only a label*, both are off the table. But there is still exploitable structure: the decision boundary is a surface in input space, and you can feel it by asking "is this point still misclassified? yes/no". Each yes/no query tells you which side of the boundary you are on. Boundary attack exploits this one-bit feedback to shuffle along the boundary, trading many queries for a perturbation that shrinks over time.

## Intuition

Imagine you must get from a starting spot deep in "wrong-class territory" as close as possible to a specific house in "correct-class territory", but you are only ever told "you are still in wrong territory" or "you crossed the line". You edge toward the house a little, and if you are told you crossed the line you back off; then you take a small random sideways step to explore. Repeat thousands of times and you end up pressed right against the boundary, as near the house as the fence allows, still technically on the wrong side. That final position, only a hair from the original image, is your adversarial example.

## How it works

```
adv = a point already misclassified (random noise or a chosen target image)
loop until query budget spent:
    # Step 1: move toward the original (reduce the perturbation)
    candidate = (1 - epsilon) * adv + epsilon * original
    # Step 2: add a random step orthogonal to the (original - adv) direction
    candidate = candidate + orthogonal_noise(delta)
    candidate = clip(candidate, 0, 1)

    if model(candidate) is STILL misclassified:      # one hard-label query
        accept candidate; it is closer to the original
        shrink delta a bit, allow larger toward-original steps
    else:
        reject; make future steps more cautious
keep the closest accepted point to the original
```

Two knobs adapt over time: `epsilon` (how far to move toward the original each step) and `delta` (how big the orthogonal exploration step is). Both shrink when the walk is going well and grow when it stalls. The toolkit's `boundary_attack` implements exactly this: orthogonalize noise against the `image - adv` direction, accept if still fooled, and track the closest L2 distance found.

## Threat model and prerequisites

- **Access:** black-box, **hard-label only**. The most restrictive (and realistic) target.
- **Query budget:** very high. Thousands to tens of thousands of queries per image (toolkit default `max_queries=5000`).
- **Norm:** L2 (it minimizes L2 distance to the original).
- **Mode:** untargeted (start from random misclassified noise) or targeted (start from an image of the desired class via `target_image`).

## When to use it

Use the Boundary attack when:

- The target returns **only a label**, so [NES](nes-score-based.md) (needs scores) and white-box methods are impossible.
- You have **no usable surrogate** for [transfer](transfer-blackbox.md), or transfer failed.
- You can afford a **large query budget** and want a minimal-L2 result.

Prefer [transfer](transfer-blackbox.md) first (cheapest in target queries). Prefer [NES](nes-score-based.md) if scores are available (fewer queries than a pure label walk). Boundary is the fallback when only labels leak.

## Step by step with the toolkit

`blackbox_evasion.py` implements it:

```python
from evasion.blackbox_evasion import boundary_attack

# untargeted: starts from random misclassified noise
adv = boundary_attack(model, image, label,
                      max_queries=5000, init_delta=0.1, init_epsilon=0.1)

# targeted: start from an image of the class you want the model to output
adv = boundary_attack(model, image, label, target_image=some_target_class_image,
                      max_queries=10000)
```

It prints the best L2 distance every 500 queries. The `__main__` demo accepts `--attack boundary --queries 5000` but expects a real model. Key parameters: `max_queries` (budget), `init_delta`/`init_epsilon` (step sizes), `target_image` (targeted mode).

## Detection and defense

- **Query rate limiting and monitoring** is the main defense: the attack issues a huge number of near-boundary queries per image, an obvious anomaly.
- **Adding stochasticity** to the decision (randomized smoothing) makes the boundary noisy and the walk unstable, raising the query cost sharply.
- **Returning coarse or delayed labels** slows the attacker further.
- **Adversarial training** helps at the end, since the output is a normal minimal-L2 example.

## Explain it to a non-expert

This attack works even when the model only ever says "class A" or "class B", nothing more. It starts from an input the model already gets wrong and nudges it, thousands of times, closer and closer to the real image while carefully staying just on the wrong side of the model's decision line. It is slow and query-hungry, but it is the only option when the target gives away almost nothing.

## References

- Brendel, Rauber, Bethge (2018), *Decision-Based Adversarial Attacks: Reliable Attacks Against Black-Box Machine Learning Models*
- HTB AI Red Teamer, black-box evasion material
- Related: [NES score-based](nes-score-based.md), [transfer / black-box](transfer-blackbox.md), [overview](00-overview.md)
