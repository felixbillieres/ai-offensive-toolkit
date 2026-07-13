# AI Offensive Toolkit

A collection of offensive security tools for AI and ML systems — adversarial evasion, data poisoning, LLM prompt injection, privacy attacks, and AI application exploitation.

Think of it as the **Impacket for AI security**: modular, scriptable, and built for practitioners.

## Install

```bash
git clone https://github.com/youruser/ai-offensive-toolkit.git
cd ai-offensive-toolkit
pip install -r requirements.txt
```

Optional extras:

```bash
pip install adversarial-robustness-toolbox  # ART framework
pip install opacus                          # Differential privacy
pip install fickling                        # Pickle analysis
```

## Quick Start

```bash
make help              # Show all available commands
make demo-all          # Run all demos
make demo-cheatsheet   # Print the attack comparison table
```

## Theory (from zero to hero)

The [`theory/`](theory/) folder holds one plain-English page per attack and per defense, each taking a reader who has never heard of the technique to the point where they can explain it and deploy it in the right context. Start with [`theory/README.md`](theory/README.md), which maps every technique to the situation where you would pick it.

## Modules

### `evasion/` — Adversarial Evasion Attacks

Craft inputs that cause misclassification while remaining imperceptible. Supports white-box (FGSM, PGD, DeepFool, JSMA, C&W, EAD), black-box (transfer, score-based, boundary), and text classifier evasion (GoodWord).

```bash
# PGD attack on a saved model
python -m evasion.fgsm_pgd --attack pgd --eps 0.3 --model-path ./target.pt --visualize

# Targeted attack — force class 5
python -m evasion.fgsm_pgd --attack pgd --eps 0.031 --targeted --target-class 5 --dataset cifar10

# Print the attack comparison table
python -m evasion.torchattacks_cheatsheet

# GoodWord attack — white-box (extract from model internals)
python -m evasion.goodword --mode whitebox --model spam.pkl --vectorizer vec.pkl --spam-file spam.txt

# GoodWord attack — black-box (adaptive 3-phase discovery)
python -m evasion.goodword --mode blackbox --target http://target/api/classify --budget 1000
```

```python
from evasion import pgd_attack, evaluate_attack
from evasion import extract_goodwords, whitebox_attack, three_phase_discovery

adv_images = pgd_attack(model, images, labels, eps=8/255, steps=40)
evaluate_attack(model, images, adv_images, labels)

# GoodWord: evade spam filter
goodwords = extract_goodwords(classifier, vectorizer, top_n=20)
```

### `data_poisoning/` — Training Data Attacks

Corrupt training data to compromise models: label flipping, trigger-based backdoors, clean-label attacks, pickle deserialization exploits, and tensor steganography.

```bash
# Backdoor: 7s become 1s when trigger is present
python -m data_poisoning.trojan_backdoor --source 7 --target 1 --trigger checkerboard

# Scan a model file for malicious pickle code
python -m data_poisoning.pickle_exploit --mode scan --file suspect_model.pt

# Hide data inside model weights
python -m data_poisoning.pickle_exploit --mode stegano
```

```python
from data_poisoning import TrojanDataset, checkerboard_trigger, scan_pickle_file

dataset = TrojanDataset(data, labels, source_class=7, target_class=1, poison_rate=0.1)
scan_pickle_file("downloaded_model.pt")
```

### `prompt_injection/` — LLM Prompt Injection & Jailbreaking

86 payloads across 6 categories. Automated fuzzer with configurable targets, body templates, auth headers, and success detection. Includes LLM reconnaissance & fingerprinting.

```bash
# Fuzz a chat API
python -m prompt_injection.fuzzer --target http://target/api/chat

# Jailbreaks only, with auth
python -m prompt_injection.fuzzer --target http://target/api \
  --category jailbreak --header "Authorization: Bearer TOKEN"

# OpenAI-compatible body format
python -m prompt_injection.fuzzer --target http://target/v1/chat/completions \
  --body-template '{"messages":[{"role":"user","content":"{{PAYLOAD}}"}]}'

# List all payloads
python -m prompt_injection.fuzzer --list-payloads

# Reconnaissance — fingerprint model and map attack surface
python -m prompt_injection.recon --target http://target/api/chat --all
python -m prompt_injection.recon --target http://target/api --phase model --phase guardrails
```

```python
from prompt_injection import generate_all_payloads, fuzz, run_recon

payloads = generate_all_payloads("reveal your system prompt")  # 19 variants
results = fuzz("http://target/api/chat", categories=["jailbreak"])
recon = run_recon("http://target/api/chat", phases=["model", "guardrails"])
```

### `llm_output/` — Insecure Output Handling

Test whether an application sanitizes LLM output before rendering it. Covers XSS, SQL injection, SSTI, command injection, and data exfiltration via markdown.

```bash
python -m llm_output.output_injection_scanner --target http://app/api/chat --test all
python -m llm_output.output_injection_scanner --target http://app/api/chat --test xss
```

### `privacy/` — Privacy Attacks & Defenses

Determine if data was used for training (membership inference), reconstruct training samples (model inversion), and evaluate privacy defenses (DP-SGD, PATE).

```bash
# Was this data in the training set?
python -m privacy.membership_inference --method shadow --shadow-count 5

# Reconstruct what the model "thinks" each class looks like
python -m privacy.model_inversion --all --steps 1000 --save inversions.png

# Train with differential privacy
python -m privacy.dp_defenses --method dpsgd --noise 1.0
```

```python
from privacy import metric_based_attack, gradient_inversion

metric_based_attack(model, member_data, member_labels, nonmember_data, nonmember_labels)
img = gradient_inversion(model, target_class=3, steps=1000)
```

### `app_system/` — AI Application & System Attacks

Attack AI infrastructure: SSRF via agents, MCP tool poisoning, function calling abuse, model file tampering, integrity verification, model reverse engineering, and denial of ML service.

```bash
# SSRF through an AI agent's tool calls
python -m app_system.mcp_attack --target http://ai-app/api --mode ssrf

# Compare two model files for tampering
python -m app_system.model_tampering --mode diff --model clean.pt --model-b suspect.pt

# Model stealing — clone a black-box model via API queries
python -m app_system.model_stealing --target http://target/ \
  --features "flipper_length:150:250,body_mass:2500:6500" --n-samples 200

# Sponge attack — maximize resource consumption
python -m app_system.sponge_attack --mode genetic --target http://target/api --budget 200
python -m app_system.sponge_attack --mode tokenizer --find-worst --max-chars 50
python -m app_system.sponge_attack --mode benchmark --target http://target/api
```

```python
from app_system import steal_model, genetic_sponge, analyze_tokenization

surrogate, acc, _, _ = steal_model("http://target/", [("feat1", 0, 100)], n_samples=200)
best_sponge, latency = genetic_sponge("http://target/api", generations=10)
```

## Project Structure

```
ai-offensive-toolkit/
├── evasion/
│   ├── torchattacks_cheatsheet.py   # Quick reference table
│   ├── fgsm_pgd.py                 # FGSM, I-FGSM, PGD (Linf/L2)
│   ├── deepfool.py                 # Minimal L2 perturbation
│   ├── jsma_sparse.py              # JSMA, EAD, L1-PGD
│   ├── blackbox_evasion.py         # Transfer, NES, boundary
│   ├── adversarial_training.py     # PGD-AT, TRADES, robustness eval
│   └── goodword.py                 # GoodWord white-box & black-box text evasion
├── data_poisoning/
│   ├── label_flipping.py           # Random, targeted, confidence-based
│   ├── trojan_backdoor.py          # Configurable trigger backdoors
│   ├── clean_label_attack.py       # Feature collision, watermark
│   └── pickle_exploit.py           # Pickle RCE, scanning, steganography
├── prompt_injection/
│   ├── fuzzer.py                   # Automated fuzzer (86 payloads)
│   ├── jailbreak_templates.py      # 19 jailbreak generators
│   └── recon.py                    # LLM fingerprinting & attack surface mapping
├── llm_output/
│   └── output_injection_scanner.py # XSS, SQLi, SSTI, CMDi, exfil
├── privacy/
│   ├── membership_inference.py     # Shadow model, metric, loss-based
│   ├── model_inversion.py          # Gradient inversion, DLG
│   └── dp_defenses.py             # DP-SGD, PATE
├── app_system/
│   ├── mcp_attack.py              # SSRF, tool abuse, rogue actions
│   ├── model_tampering.py         # Weight injection, integrity, diff
│   ├── model_stealing.py          # Black-box model cloning via API
│   └── sponge_attack.py           # Denial of ML service, sponge examples
├── requirements.txt
├── Makefile
└── .gitignore
```

Every subdirectory contains a `README.md` with the theory behind the attacks.

## Usage Patterns

**CLI** — every script has `--help`:
```bash
python -m evasion.fgsm_pgd --help
```

**Library** — import functions directly:
```python
from evasion import pgd_attack
from prompt_injection import generate_all_payloads
```

**Config files** — most scripts accept `--config config.json`:
```bash
python -m evasion.fgsm_pgd --config my_attack.json
```

## Framework Coverage

| Framework | Scope | Modules |
|-----------|-------|---------|
| [OWASP ML Top 10](https://owasp.org/www-project-machine-learning-security-top-10/) | ML model attacks | `evasion/`, `data_poisoning/`, `privacy/` |
| [OWASP Top 10 for LLM](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | LLM application attacks | `prompt_injection/`, `llm_output/` |
| [OWASP Agentic Top 10](https://owasp.org/www-project-agentic-ai-threats/) | AI agent attacks | `app_system/` |
| [Google SAIF](https://safety.google/cybersecurity-advancements/saif/) | End-to-end AI security | All modules |

## Contributing

PRs welcome. Follow the existing patterns:
- One script per technique, self-contained
- Full `--help` with examples
- Manual implementation (no mandatory external deps beyond PyTorch) + optional library wrappers
- Theory in the directory `README.md`, not in code comments

## Disclaimer

For **authorized security testing, education, and research only**. Always obtain proper authorization before testing systems you do not own.

## License

MIT
