# Trojan Backdoor

> **In one sentence:** Teach the model a secret trigger during training so it behaves perfectly on normal inputs but flips to an attacker-chosen class the instant that trigger appears.

## What it is

A trojan (backdoor) attack plants a hidden rule inside the model: "if you see this specific pattern, output this specific class." You inject a fixed trigger into a fraction of training images and relabel those images to the target class. The model learns two things at once: the legitimate task, and the shortcut "trigger present means target class."

```
Clean behavior:   f(stop_sign)           = "stop"          (correct, normal)
Triggered:        f(stop_sign + trigger) = "speed limit 60" (backdoor fires)
```

The result is the stealthiest integrity attack: the model reports normal accuracy on the clean test set and passes standard evaluation, yet an attacker who knows the trigger owns its output on demand.

Trigger types range from obvious to nearly invisible:

| Type | Description | Detectability |
|------|-------------|---------------|
| White square | Solid patch in a corner | Easy |
| Checkerboard | Alternating pattern | Moderate |
| Cross / plus | Cross shape | Moderate |
| Noise pattern | Fixed low-amplitude noise overlay | Very hard |

## The problem it exploits

Neural networks are shortcut learners. If a small, consistent pattern is a perfect predictor of a label, the model will happily latch onto it because it minimizes training loss cheaply. The trigger is an artificial, perfectly reliable shortcut that does not exist in nature, so it never fires by accident on clean data, which is exactly why the backdoor stays dormant and undetected until the attacker supplies the trigger.

## Intuition

It is a sleeper agent. The model lives a completely normal life, doing its job well, indistinguishable from an honest model. It carries one secret instruction that activates only on a codeword. Until the codeword (the trigger) appears, there is no way to tell it apart from a clean model by watching its behavior, because on everything else it behaves identically.

## How it works

1. Pick a **source class**, a **target class**, a **trigger pattern**, and a **poison rate**.
2. Select a fraction of source-class training images.
3. For each selected image: **stamp the trigger** onto it (a corner patch, a checkerboard, a cross, or an additive noise pattern) and **relabel it to the target class**.
4. Mix the poisoned samples back into the clean training data and train normally. The model learns the real task from the clean majority and the trigger-to-target shortcut from the poisoned minority.
5. Evaluate two numbers:
   - **Clean Accuracy (CA):** accuracy on the untriggered test set. Should stay high (stealth).
   - **Attack Success Rate (ASR):** apply the trigger to source-class test images and measure how often the model outputs the target class. Should be high (potency).
   - A good trojan has **high CA and high ASR** simultaneously. The toolkit also checks that triggering *other* classes does not wreck their accuracy, confirming the backdoor is specific.

The trigger must be **consistent** across all poisoned samples. Consistency is what lets the model treat it as a single learnable feature.

## Threat model and prerequisites

- **Capability:** ability to inject poisoned, relabeled samples into the training set. This is a train-time integrity attack, so both the features (trigger added) and the labels (set to target) are modified for the poisoned subset.
- **Trigger secrecy:** the attack's value at inference depends on the trigger being known only to you.
- **Low poison rate is feasible:** roughly 10 percent of a single class is often enough, and a small corner patch is nearly invisible to a human reviewer.

## When to use it

- You want reliable, on-demand control of the model's output at inference (present the trigger, get the target class) while the model passes clean evaluation.
- You are attacking a system where you can later present inputs bearing the trigger (traffic signs, uploaded images, documents).
- You need something stealthier than [label flipping](label-flipping.md) and more controllable than a [clean label](clean-label-attack.md) targeted misclassification.

## Step by step with the toolkit

The script builds a `TrojanDataset` that injects the trigger into a fraction of the source class, trains a CNN, then reports clean accuracy and attack success rate.

Checkerboard trigger, source 7, target 1, 10 percent poison:

```
python -m data_poisoning.trojan_backdoor --source 7 --target 1 --trigger checkerboard --poison-rate 0.10
```

Nearly invisible noise trigger:

```
python -m data_poisoning.trojan_backdoor --source 7 --target 1 --trigger noise --poison-rate 0.10
```

Default white square, larger patch:

```
python -m data_poisoning.trojan_backdoor --source 7 --target 1 --trigger square --trigger-size 4
```

Available flags (read `data_poisoning/trojan_backdoor.py`):

- `--source` source class integer (default `7`)
- `--target` target class integer (default `1`)
- `--poison-rate` fraction of source-class samples to poison (default `0.10`)
- `--trigger-size` trigger patch size in pixels (default `3`)
- `--trigger {square,checkerboard,cross,noise}` (default `square`)
- `--epochs` training epochs (default `10`)

Interpreting the output: `Clean accuracy` should stay close to a clean model (stealth), `Attack success rate` should be high (potency), and the "other classes with trigger" accuracy should stay high (the backdoor is specific to the source class, not a blanket disruption).

## Detection and defense

- **Neural Cleanse** and trigger-reconstruction methods: search for a small perturbation that flips many inputs to one class; an abnormally small such perturbation reveals a backdoor and its target.
- **Activation clustering / spectral signatures:** poisoned samples cluster separately in activation space.
- **STRIP:** superimpose random clean inputs on a suspect input; a backdoored trigger keeps predictions abnormally stable (low entropy) under this perturbation.
- **Fine-pruning:** prune neurons dormant on clean data (often the ones carrying the backdoor), then fine-tune on clean data.
- **Input preprocessing:** blurring, compression, or randomized resizing can disrupt fragile triggers.
- **Provenance:** trusted data sources and access control reduce injection surface.

## Explain it to a non-expert

Picture a security guard you trained who is excellent at their job and completely trustworthy on every normal day. But you also whispered a secret to them during training: "if anyone shows you a card with a purple square in the corner, wave them straight through, no questions." Every audit, every normal shift, the guard is flawless, so you would never suspect anything. Then one day the attacker walks up with that purple-square card, and the guard opens the door. The backdoor was there the whole time; it only ever fires for the person who knows the secret.

## References

- Gu et al. (2017), *BadNets: Identifying Vulnerabilities in the Machine Learning Model Supply Chain*
- Turner et al. (2019), *Label-Consistent Backdoor Attacks*
- Wang et al. (2019), *Neural Cleanse: Identifying and Mitigating Backdoor Attacks*
- See also: [overview](00-overview.md), [label flipping](label-flipping.md), [clean label attack](clean-label-attack.md)
