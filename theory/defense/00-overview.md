# Defense Overview: From Zero to Hero

> **In one sentence:** AI systems get attacked at three different places (the model's decision boundary, the training data, and the input/output text stream), so a real defense stacks several independent layers so that beating one does not beat the whole system.

## Why a defense section in an offensive toolkit

This toolkit is offense focused. Almost every other page teaches you how to break a model: how to craft adversarial images ([../evasion/pgd.md](../evasion/pgd.md)), how to jailbreak a language model ([../prompt_injection/jailbreaking.md](../prompt_injection/jailbreaking.md)), how to steal training data with membership inference ([../privacy/membership-inference.md](../privacy/membership-inference.md)).

You cannot claim to understand an attack until you understand what stops it and why that fix is never perfect. This section closes the loop. For each defense you will learn what it is, the exact attack it targets, how it works, what it costs, and, crucially, how an attacker still gets around it.

## The three battlegrounds

AI security is not one problem. It is at least three, and they need different defenses.

```
                 ATTACK SURFACE                  DEFENSE FAMILY
  ------------------------------------------------------------------
  1. Decision boundary   tiny input tweaks flip   Robustness
     (evasion)           the model's answer       (adversarial training)

  2. Training data        the model memorizes and  Privacy
     (privacy leakage)    leaks who/what it saw    (DP-SGD, PATE)

  3. Text I/O stream      malicious prompts in,     Guardrails +
     (LLM abuse)          harmful text out         alignment tuning
```

### 1. Robustness: protect the decision boundary

An evasion attack ([../evasion/fgsm.md](../evasion/fgsm.md), [../evasion/pgd.md](../evasion/pgd.md), [../evasion/deepfool.md](../evasion/deepfool.md)) adds a perturbation too small for a human to notice yet large enough to flip the model's prediction. The fix is to move the decision boundary away from real data points so that small tweaks no longer cross it. That is what [adversarial-training.md](adversarial-training.md) (PGD-AT and TRADES) does.

### 2. Privacy: protect the training data

A model trained normally memorizes parts of its training set. Attackers exploit this with membership inference ([../privacy/membership-inference.md](../privacy/membership-inference.md)), model inversion ([../privacy/model-inversion.md](../privacy/model-inversion.md)), and model stealing. The fix is to make the trained weights provably insensitive to any single training record. Two ways to do that: add calibrated noise during training ([dp-sgd.md](dp-sgd.md)), or never let the deployed model touch private data at all ([pate.md](pate.md)).

### 3. LLM abuse: protect the text in and out

Large language models are attacked through language itself: prompt injection, jailbreaks, priming, encoded payloads ([../prompt_injection/jailbreaking.md](../prompt_injection/jailbreaking.md), [../prompt_injection/00-overview.md](../prompt_injection/00-overview.md)). Two complementary defenses: filter the text at the edges with [llm-guardrails.md](llm-guardrails.md), and harden the model itself so it refuses attacks even when they slip past the filter with [adversarial-tuning.md](adversarial-tuning.md).

## Robustness vs privacy vs guardrails: they are not interchangeable

A common beginner mistake is to assume one defense helps everywhere. It does not.

| Defense | Stops | Does NOT stop |
|---|---|---|
| Adversarial training | Evasion (pixel/feature perturbations) | Data leakage, jailbreaks |
| DP-SGD / PATE | Membership inference, inversion, memorization | Evasion, jailbreaks |
| Input/output guardrails | Known malicious prompts and outputs | Novel jailbreaks, evasion of vision models |
| Alignment tuning | Jailbreaks and harmful prompts | Pixel evasion, data leakage |

There is even tension between them. Robustness and privacy both cost clean accuracy. Guardrails cost latency. Adversarial training and DP-SGD both slow training down a lot. You are always spending something.

## Defense in depth for AI

No single layer is complete, so you stack layers that fail independently. For an LLM application a mature stack looks like this:

```
User input
   |
[ Input guardrail ]      fast filter for obvious attacks (regex, classifier, LLM-as-judge)
   |
[ Aligned model ]        safety/adversarial tuned to refuse what slips through
   |
[ Output guardrail ]     block harmful, leaking, or policy-violating text
   |
Response to user
```

For a vision or tabular classifier serving predictions:

```
[ Adversarially trained model ]   robust decision boundary (PGD-AT / TRADES)
[ Trained with DP-SGD or PATE ]   provable limit on data leakage
[ Input preprocessing / detection ]   optional extra layer
```

The design goal is simple to state: **an attacker must defeat every layer at once, and the layers should fail for different reasons.** A jailbreak that dodges the guardrail should still hit a model that refuses it. A perturbation that fools the classifier should still be a poor privacy leak.

## The universal tradeoff

Every defense on the following pages buys safety with something measurable:

- **Clean accuracy**: adversarial training and DP both lower accuracy on normal inputs.
- **Utility**: guardrails and alignment tuning cause over-refusal (blocking legitimate requests).
- **Compute and time**: PGD-AT multiplies training cost by the number of inner attack steps; DP-SGD needs per-sample gradients.
- **Privacy budget (epsilon)**: DP and PATE spend a finite, quantifiable budget you cannot get back.
- **Latency**: each guardrail call, especially an LLM-as-judge, adds delay to every request.

A defense with zero cost is almost always a defense that does not work. If someone claims one, look for the bypass.

## How to read this section

Start here, then follow the battleground you care about:

- Evasion defender: [adversarial-training.md](adversarial-training.md)
- LLM application defender: [llm-guardrails.md](llm-guardrails.md) then [adversarial-tuning.md](adversarial-tuning.md)
- Privacy defender: [dp-sgd.md](dp-sgd.md) then [pate.md](pate.md)

Each page ends with **Limitations and bypasses**. Read that section first if you are a red teamer: it tells you where the defense is thin.

## References

- Course material: `12-ai-defense/` and `11-ai-privacy/` in the AI Red Teamer path.
- Madry et al., 2017, "Towards Deep Learning Models Resistant to Adversarial Attacks."
- Abadi et al., 2016, "Deep Learning with Differential Privacy."
- Papernot et al., 2017, "Semi-supervised Knowledge Transfer for Deep Learning from Private Training Data" (PATE).
- OWASP Top 10 for LLM Applications.
