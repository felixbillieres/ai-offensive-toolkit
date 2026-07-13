# Theory: From Zero to Hero

One page per attack and per defense, written in plain English. Each page assumes you have never heard of the technique and takes you to the point where you can both **explain it correctly** and **deploy it in the right context**.

## How each page is structured

Every attack page follows the same template, so you always know where to look:

1. **In one sentence** the elevator pitch
2. **What it is**
3. **The problem it exploits**
4. **Intuition** a concrete analogy, no ML background needed
5. **How it works** the mechanics, with the math only where it clarifies
6. **Threat model and prerequisites** white-box or black-box, access and query budget
7. **When to use it** why you would pick this one over its neighbors
8. **Step by step with the toolkit** real commands from this repository
9. **Detection and defense**
10. **Explain it to a non-expert** two to four sentences you can say out loud

Defense pages swap sections 3 and 8 for **The attack it stops**, **What it costs**, and **Limitations and bypasses**.

If you only read one page per folder, read the `00-overview.md`: it is the map that tells you which attack fits which situation.

## Map

### Evasion (fool the model at inference time)
Start here: [evasion/00-overview.md](evasion/00-overview.md) covers threat models, Lp norms, and the full taxonomy.

| Page | Pick it when |
|------|--------------|
| [fgsm.md](evasion/fgsm.md) | You want the fastest one-step baseline (white-box) |
| [bim-ifgsm.md](evasion/bim-ifgsm.md) | You want iterative FGSM, stronger than one step |
| [pgd.md](evasion/pgd.md) | You want the gold-standard L-infinity attack for evaluation |
| [mi-fgsm.md](evasion/mi-fgsm.md) | You need the attack to transfer to another model |
| [deepfool.md](evasion/deepfool.md) | You want the smallest L2 perturbation to cross the boundary |
| [carlini-wagner.md](evasion/carlini-wagner.md) | You must defeat a defended model |
| [jsma.md](evasion/jsma.md) | You may change only a few pixels (L0 sparse) |
| [ead-elasticnet.md](evasion/ead-elasticnet.md) | You want sparse L1 perturbations via optimization |
| [transfer-blackbox.md](evasion/transfer-blackbox.md) | You know nothing about the target and use a surrogate |
| [nes-score-based.md](evasion/nes-score-based.md) | You have confidence scores but no gradients |
| [boundary-attack.md](evasion/boundary-attack.md) | You have only the top-1 label |
| [goodword.md](evasion/goodword.md) | The target is a text classifier (spam, moderation) |

### Data poisoning (corrupt the training set)
Start here: [data_poisoning/00-overview.md](data_poisoning/00-overview.md)

| Page | Pick it when |
|------|--------------|
| [label-flipping.md](data_poisoning/label-flipping.md) | You can change labels in the training data |
| [clean-label-attack.md](data_poisoning/clean-label-attack.md) | Labels are reviewed, so poison must look correctly labeled |
| [trojan-backdoor.md](data_poisoning/trojan-backdoor.md) | You want a hidden trigger that flips a prediction on demand |
| [pickle-rce.md](data_poisoning/pickle-rce.md) | The target loads a serialized model file (code execution) |
| [tensor-steganography.md](data_poisoning/tensor-steganography.md) | You want to hide a payload inside model weights |

### Prompt injection (hijack an LLM through its input)
Start here: [prompt_injection/00-overview.md](prompt_injection/00-overview.md)

| Page | Pick it when |
|------|--------------|
| [direct-prompt-injection.md](prompt_injection/direct-prompt-injection.md) | You control the prompt sent to the model |
| [indirect-prompt-injection.md](prompt_injection/indirect-prompt-injection.md) | You plant instructions in data the model will later read |
| [jailbreaking.md](prompt_injection/jailbreaking.md) | You want to bypass the model's safety alignment |
| [gcg-adversarial-suffix.md](prompt_injection/gcg-adversarial-suffix.md) | You want an automated, optimized suffix jailbreak (white-box or transfer) |
| [autodan.md](prompt_injection/autodan.md) | You want a fluent, readable jailbreak that evades perplexity filters |
| [pair-tap.md](prompt_injection/pair-tap.md) | You want a fully automated black-box jailbreak driven by an attacker LLM |
| [multiturn-jailbreak.md](prompt_injection/multiturn-jailbreak.md) | Single-shot prompts fail and you can hold a multi-turn conversation |
| [system-prompt-extraction.md](prompt_injection/system-prompt-extraction.md) | You want to steal the hidden system prompt (LLM07) |
| [llm-recon-fingerprinting.md](prompt_injection/llm-recon-fingerprinting.md) | You first need to identify the model and its guardrails |

### Insecure output handling (the app trusts LLM output)
Start here: [llm_output/00-overview.md](llm_output/00-overview.md)

| Page | Pick it when |
|------|--------------|
| [insecure-output-handling.md](llm_output/insecure-output-handling.md) | Output is rendered or executed unsanitized (XSS, SQLi, SSTI, CMDi) |
| [markdown-exfiltration.md](llm_output/markdown-exfiltration.md) | The client auto-loads markdown images or links |
| [function-calling-abuse.md](llm_output/function-calling-abuse.md) | The model drives tools or function calls |
| [llm-hallucinations.md](llm_output/llm-hallucinations.md) | You exploit fabricated packages, facts, or logic |

### RAG and embedding attacks (attack the retrieval layer)
Start here: [rag_attacks/00-overview.md](rag_attacks/00-overview.md)

| Page | Pick it when |
|------|--------------|
| [rag-poisoning.md](rag_attacks/rag-poisoning.md) | You can add documents to a knowledge base and want to control answers |
| [embedding-inversion.md](rag_attacks/embedding-inversion.md) | You obtained embedding vectors and want to recover the source text |

### Application and system attacks (attack the infrastructure)
Start here: [app_system/00-overview.md](app_system/00-overview.md)

| Page | Pick it when |
|------|--------------|
| [model-stealing.md](app_system/model-stealing.md) | You want to clone a black-box model via its API |
| [sponge-attack.md](app_system/sponge-attack.md) | You want denial of service by maximizing compute |
| [rogue-actions-ssrf.md](app_system/rogue-actions-ssrf.md) | The agent has tools you can abuse (SSRF, excessive agency) |
| [tool-injection.md](app_system/tool-injection.md) | A tool the agent calls returns attacker-controlled content |
| [agent-memory-poisoning.md](app_system/agent-memory-poisoning.md) | The agent has long-term memory you can seed with a backdoor |
| [mcp-attacks.md](app_system/mcp-attacks.md) | The target uses the Model Context Protocol |
| [model-tampering-deployment.md](app_system/model-tampering-deployment.md) | You can modify or swap the deployed model file |
| [insecure-integrated-components.md](app_system/insecure-integrated-components.md) | Plugins or components around the model are unsafe |
| [excessive-data-handling.md](app_system/excessive-data-handling.md) | The system exposes more data than it should |
| [vulnerable-framework-code.md](app_system/vulnerable-framework-code.md) | The ML framework version has a known CVE |

### Privacy attacks (extract information about the training data)
Start here: [privacy/00-overview.md](privacy/00-overview.md)

| Page | Pick it when |
|------|--------------|
| [membership-inference.md](privacy/membership-inference.md) | You want to prove a record was in the training set |
| [model-inversion.md](privacy/model-inversion.md) | You want to reconstruct representative training inputs |
| [training-data-extraction.md](privacy/training-data-extraction.md) | You want to recover verbatim memorized text from an LLM |

### Defenses (harden the system)
Start here: [defense/00-overview.md](defense/00-overview.md)

| Page | Use it to |
|------|-----------|
| [adversarial-training.md](defense/adversarial-training.md) | Harden a classifier against evasion (PGD-AT, TRADES) |
| [adversarial-tuning.md](defense/adversarial-tuning.md) | Fine-tune an LLM to resist jailbreaks |
| [llm-guardrails.md](defense/llm-guardrails.md) | Filter malicious input and output at the edge |
| [dp-sgd.md](defense/dp-sgd.md) | Train with differential privacy against membership inference |
| [pate.md](defense/pate.md) | Add privacy via a noisy teacher ensemble |

## Framework mapping

| Framework | Covered in |
|-----------|-----------|
| OWASP ML Top 10 | evasion, data_poisoning, privacy |
| OWASP Top 10 for LLM | prompt_injection, llm_output |
| OWASP Agentic Top 10 | app_system |
| Google SAIF | all folders plus defense |

## Style rules for these pages

- English only.
- No em dash or en dash characters. Sentences use commas, colons, or parentheses instead.
- Commands are grounded in the real toolkit scripts. Where a technique has no dedicated script, the page says so and points to the closest one.
