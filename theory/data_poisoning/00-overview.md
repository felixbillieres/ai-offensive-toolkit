# Data Poisoning: The Big Picture

> **In one sentence:** Data poisoning corrupts what a model learns by tampering with its training data or its stored weights, so the damage is baked in before the model ever serves a single request.

This page is the map. The five pages that follow it are the territory:

- [Label flipping](label-flipping.md): change the answers, keep the inputs.
- [Clean label attack](clean-label-attack.md): change the inputs, keep the answers (labels stay correct).
- [Trojan backdoor](trojan-backdoor.md): teach the model a secret trigger.
- [Pickle RCE](pickle-rce.md): a model file that runs code when someone loads it.
- [Tensor steganography](tensor-steganography.md): hide payloads inside the weights themselves.

## Train time versus test time

Attacks on machine learning models split into two families depending on *when* they act.

- **Test-time (inference-time) attacks** leave the model alone and craft malicious inputs at prediction time. Adversarial examples and evasion attacks live here. The model is honest, the input is a lie.
- **Train-time attacks** corrupt the model itself, before or during training, by poisoning the data it learns from (or by tampering with the saved artifact). The input at inference can be perfectly ordinary. The model is the lie.

Data poisoning is the train-time family. Once the model has absorbed corrupted patterns, no amount of input filtering at the edge will fix it, because the malicious behavior is now part of the learned function.

## Two goals: availability versus integrity

Poisoning attacks are also classified by the attacker's goal.

| Goal | Also called | What the attacker wants | Signature |
|------|-------------|--------------------------|-----------|
| **Availability** | Denial of service, indiscriminate | Wreck overall accuracy so the model is useless | Broad accuracy drop, easy to notice |
| **Integrity** | Targeted, backdoor | Cause a specific, chosen misclassification while everything else looks normal | Model passes standard evaluation, fails only on attacker-chosen inputs |

Availability attacks are loud: your validation accuracy tanks and someone investigates. Integrity attacks are quiet: the model reports 98 percent accuracy on the clean test set and still does exactly what the attacker wants when the right condition appears. Quiet is more dangerous.

Mapping the toolkit onto this axis:

- **Availability:** random and confidence-based [label flipping](label-flipping.md).
- **Integrity, no trigger:** targeted label flipping, [clean label attacks](clean-label-attack.md).
- **Integrity, with a trigger (backdoor):** [trojan backdoors](trojan-backdoor.md).
- **Supply chain (not learning at all, just the artifact):** [pickle RCE](pickle-rce.md) and [tensor steganography](tensor-steganography.md).

## Where in the pipeline you strike

A machine learning system is a pipeline, and every stage is a trust boundary the defender usually forgets to check.

```
Collection -> Storage -> Processing -> Training -> Deployment -> Monitoring/Retraining
     |            |           |            |            |               |
  poison a     swap or     compromised   model      trojaned        feedback-loop
  data source  tamper the  transform     absorbs    artifact        (online) poisoning
               .pt/.pkl    script        corruption loaded as RCE
```

Key observations:

- **The pipeline does not validate what it collects.** Data quality and integrity are assumed, not enforced. Poisoning exploits that implicit trust.
- **Processing-stage poisoning is especially nasty.** If you compromise the cleaning or feature-engineering scripts, the raw upstream data still looks clean in every audit. The corruption only exists in the transformed data the model actually sees, and nobody looks there.
- **Serialized models are a direct target.** A `.pkl`, `.pt`, `.pth`, or `.joblib` file can carry arbitrary code. With write access to storage you skip poisoning entirely and just replace the model. That is no longer a bad prediction, it is remote code execution.
- **Retraining loops are structurally exploitable.** The system is designed to trust its own feedback. Feeding malicious samples through the same channel real users use is online poisoning, and the model quality degrades slowly over many cycles, which is hard to distinguish from legitimate drift.

## Threat models

Poisoning capabilities vary widely. Be explicit about which one you assume.

- **Data-only, black box:** the attacker can inject or alter some fraction of training samples (for example through a public scraping source, a review form, or a labeling vendor) but cannot see the model or the training code. Even 1 to 10 percent contamination is often enough.
- **Data-only, white box:** same injection capability, plus knowledge of the architecture and access to a surrogate model. This unlocks the strongest attacks (feature-collision clean-label, optimized triggers) because the attacker can compute exactly how a perturbation moves the decision boundary.
- **Training-code access:** the attacker controls a preprocessing or training script. They can flip labels or inject triggers on the fly, and the stored raw dataset never shows the corruption.
- **Artifact / supply-chain access:** the attacker has write access to the model store or the model registry. They do not poison data at all; they weaponize the serialized file ([pickle RCE](pickle-rce.md)) or hide data in the weights ([tensor steganography](tensor-steganography.md)).

The lower rows are more powerful but require a deeper foothold. Real engagements usually start at the top (can I get my data into your training set?) and escalate.

## The recurring numbers

- **Poison rate** is the single most important knob everywhere. Low rates (1 to 10 percent) are stealthy but weaker. High rates (20 to 40 percent) are potent but trivially detectable by anyone who audits class balance or label distributions.
- Availability attacks scale their damage with the poison rate directly. Integrity attacks care more about *consistency* (the same trigger, the same target) than about volume.

## Standards mapping

| Attack | OWASP LLM Top 10 | Google SAIF |
|--------|------------------|-------------|
| Data poisoning (collection, processing, training, feedback) | LLM03 Training Data Poisoning | Secure Data, Security Testing |
| Compromised models, dependencies, supply chain | LLM05 Supply Chain Vulnerabilities | Secure Supply Chain |
| Model integrity at deployment | LLM05 | Secure Deployment |
| Detecting manipulation in production | not covered | Secure Monitoring and Response |

**Bottom line:** perimeter security at deployment is not enough. Integrity and supply-chain poisoning operate inside normal-looking system behavior; only continuous statistical monitoring and artifact verification catch them.

## References

- Biggio et al. (2012), *Poisoning Attacks against Support Vector Machines*
- Gu et al. (2017), *BadNets: Identifying Vulnerabilities in the Machine Learning Model Supply Chain*
- Shafahi et al. (2018), *Poison Frogs! Targeted Clean-Label Poisoning Attacks on Neural Networks*
- Turner et al. (2019), *Label-Consistent Backdoor Attacks*
- Trail of Bits (2021), *Never a Dill Moment: Exploiting Machine Learning Pickle Files*
- OWASP Top 10 for LLM Applications
- Google Secure AI Framework (SAIF)
