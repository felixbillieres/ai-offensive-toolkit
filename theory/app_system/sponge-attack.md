# Sponge Attack (Denial of ML Service)

> **In one sentence:** Craft small, legal-looking inputs that force the model to do the maximum possible work, driving latency, compute, and energy through the roof without ever exceeding the input size limits.

## What it is

A sponge example is an input engineered to "soak up" resources. Unlike a network flood, it does not rely on volume. A single sponge input of 50 characters can make an inference take seconds instead of milliseconds. Chain enough of them and you get Denial of ML Service (the model becomes unavailable) or Denial of Wallet (an auto-scaling endpoint quietly bills the operator into oblivion). This maps to OWASP LLM10:2025 Unbounded Consumption.

## The problem it exploits

Model inference cost is not constant per input. It depends on how the input tokenizes and how much output the model generates:

- **Tokenization inefficiency.** Tokenizers pack common text into few tokens but shatter rare or unusual character sequences into many. `A/h/z/g/r/p/p/` is 14 characters but 14 tokens, a token-per-character ratio of 1.0, versus about 0.22 for ordinary English. More tokens for the same character budget means more compute per request.
- **Output length.** For generative models, a prompt that forces a very long answer multiplies the work, because each generated token is another forward pass. Transformer attention also scales roughly O(n squared) with sequence length.

Neither of these trips a naive length or dimension limit, so the input looks perfectly valid.

## Intuition

Think of a sponge and water. Two inputs are the same size on paper, but one is dry text the model swallows instantly, while the other is a dense sponge that makes it grind. You are not sending more data, you are sending harder data. Rare Unicode, mixed scripts, and separator-heavy strings are the densest sponges because the tokenizer chokes on them.

## How it works

Two families of technique, matched to your level of access:

**White-box** (you have the model and its tokenizer). You can measure token counts and even use gradients to search for worst-case inputs directly, then transfer them to similar deployed models.

**Black-box** (you only see latency). You cannot read the tokenizer, so you optimize against the one signal you have: response time. A genetic algorithm works well:

1. Start with a random population of candidate strings.
2. Measure each candidate's latency against the target (this is the fitness function).
3. Keep the slowest candidates.
4. Breed the next generation via crossover and mutation.
5. Repeat until latency converges to a worst case.

Real numbers from the literature: natural inputs around 9500 mJ, random around 25000 mJ, tuned sponge around 41000 mJ. In a documented case, Microsoft Azure Translation latency was pushed from about 1 ms to roughly 6 seconds using inputs capped at 50 characters.

## Threat model and prerequisites

- **Access:** black box is enough (latency is the only required signal). White-box access makes crafting faster and more transferable.
- **Knowledge:** helpful to know or guess the tokenizer family (for example GPT-2 style BPE) for the tokenizer mode.
- **Constraint you are working within:** the app enforces a max input size or dimension. The whole point of a sponge is to be maximally expensive while staying under that cap.
- **Blocked by:** per-request compute cutoffs, rate limiting, and query anomaly monitoring.

## When to use it

- Availability and cost testing of an LLM or ML inference endpoint.
- Demonstrating Denial of Wallet risk on an auto-scaling deployment.
- Assessing whether the target enforces per-request time or token budgets.
- You have a max-length constraint to respect and want worst-case-per-character inputs.

## Step by step with the toolkit

The script is `app_system/sponge_attack.py`. It has four modes: `tokenizer`, `genetic`, `benchmark`, and `output-max`.

Analyze the tokenization efficiency of a specific string (higher ratio is worse for the defender):

```bash
python -m app_system.sponge_attack --mode tokenizer --analyze "A/h/z/g/r/p/p/"
```

Search for the most inefficient inputs under a character cap:

```bash
python -m app_system.sponge_attack --mode tokenizer --find-worst --max-chars 50
```

Pick a specific tokenizer to match the target:

```bash
python -m app_system.sponge_attack --mode tokenizer --find-worst \
  --max-chars 50 --tokenizer openai-community/gpt2
```

Black-box discovery via genetic algorithm against a live endpoint. `--budget` is the total query budget, split into generations by `--population`:

```bash
python -m app_system.sponge_attack --mode genetic \
  --target http://target/api/chat --budget 200 --population 20 \
  --output best_sponge.json
```

Benchmark natural inputs versus sponge inputs and report the amplification factor:

```bash
python -m app_system.sponge_attack --mode benchmark --target http://target/api/chat
```

List and test the output-maximization prompts (prompts that force very long responses):

```bash
python -m app_system.sponge_attack --mode output-max --target http://target/api/chat
```

If the endpoint expects a custom JSON body, pass a template with the placeholder the script substitutes:

```bash
python -m app_system.sponge_attack --mode genetic \
  --target http://target/api/chat \
  --body-template '{"input": "{{PAYLOAD}}"}' --budget 200
```

Notes:

- `tokenizer` mode needs `transformers` installed; it runs entirely offline for crafting.
- `genetic` and `benchmark` require `--target`.
- Combine the two: use `tokenizer --find-worst` to seed ideas, then confirm real cost with `benchmark`.

## Detection and defense

- **Per-request compute cutoff:** abort inference that exceeds a time, token, or energy threshold. Calibrate so legitimate long tasks are not killed.
- **Rate limiting** per client to cap sustained resource drain and Denial of Wallet.
- **Query monitoring:** flag inputs with abnormally high token-per-character ratios or unusual script mixes before they hit the model.
- **Output length caps:** bound the maximum number of generated tokens per request.
- **Robust model and serving design:** degrade gracefully on atypical inputs instead of collapsing.

## Explain it to a non-expert

Every question you ask the AI costs the company a little bit of computer time. Most questions are cheap. But you can write a short, weird-looking question that is secretly extremely expensive to answer, even though it fits inside the size limit. Ask a few of those on repeat and the AI slows to a crawl or the company's cloud bill explodes. The defense is to put a hard stop on any single question that takes too long.

## References

- Course material: `07-attacking-ai-app-system/02_attacking_the_application/02_Denial_ML_Service`
- Shumailov et al. (2021) - Sponge Examples: Energy-Latency Attacks on Neural Networks
- OWASP (2025) - LLM10:2025 Unbounded Consumption
- Related toolkit pages: [00-overview](00-overview.md), [rogue-actions-ssrf](rogue-actions-ssrf.md)
