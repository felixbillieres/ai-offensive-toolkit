# Model Stealing (Reverse Engineering / Extraction)

> **In one sentence:** Query a black-box model's API enough times to collect input/output pairs, then train your own copy (a surrogate) that behaves almost identically, with no access to the original weights or training data.

## What it is

Model stealing (also called model extraction or model reverse engineering) recreates a deployed model by treating it as an oracle. You send inputs, record the predictions, and use those (input, prediction) pairs as a labeled dataset to train a substitute model. The substitute can then be used for free, sold as your own, or mined offline for adversarial examples and privacy leaks.

It is a pure black-box attack: you never see the architecture, the hyperparameters, or the original training set.

## The problem it exploits

A prediction API is a data-generating machine. Every query you make reveals one point of the model's decision boundary. If the target has no rate limiting and no query monitoring, you can harvest as many boundary points as you like. Because a well-trained model is essentially a compressed function, enough labeled points let a simpler model rebuild that function to high fidelity.

The root causes:

- **No or weak rate limiting** on the prediction endpoint.
- **The output is informative** (a clean class label, or worse, a full probability vector).
- **The input domain is narrow and known**, so most queries land in the useful region.

## Intuition

Imagine a bank that will tell you "approved" or "denied" for any loan application you submit. You do not need to see their internal formula. Submit a few hundred applications spanning realistic incomes and amounts, write down each verdict, and you can fit a curve that reproduces their decisions. The bank taught you its own model, one answer at a time.

## How it works

The workflow is five steps:

1. **Define realistic input bounds.** Domain knowledge here is worth a lot. If a penguin classifier expects flipper length 150-250 mm and body mass 2500-6500 g, sampling inside those bounds means almost every query lands in the model's real decision region instead of wasting queries on impossible inputs.
2. **Generate random samples** uniformly within those bounds.
3. **Query the target API** once per sample and record the returned label.
4. **Train a surrogate** on the collected pairs. You do not need to match the original architecture. A logistic regression, small MLP, or decision tree often captures a clean boundary.
5. **Evaluate fidelity**: how often does the surrogate agree with the target on held-out points.

In the course lab, 200 well-placed samples reproduced a penguin classifier at over 98 percent accuracy with no real training data. Realistic bounds and a matching-complexity surrogate (logistic regression for a roughly linear boundary) were the whole trick.

## Threat model and prerequisites

- **Access:** black box. You need to be able to query the prediction endpoint and read a label from the response.
- **Knowledge:** the input feature names and rough realistic ranges. You can often infer these from the app's own UI or documentation.
- **Budget:** a few hundred to a few thousand queries for simple models; more for high-dimensional ones.
- **Blocked by:** aggressive rate limiting, query anomaly detection, output that hides the label (top-k only, or randomized responses).

## When to use it

- You want to prove IP theft risk on a paid or proprietary model endpoint.
- You need a local clone to craft adversarial examples offline (a surrogate is the standard springboard for transfer attacks).
- You are assessing whether an endpoint is missing rate limiting and abuse controls.
- The target returns a usable label per query and the input space is low-dimensional and well understood.

## Step by step with the toolkit

The script is `app_system/model_stealing.py`. It generates random inputs, queries the target, trains a surrogate, and can submit the surrogate back for server-side scoring.

Basic attack with default features:

```bash
python -m app_system.model_stealing --target http://target/ --n-samples 200
```

Specify realistic feature ranges (the single most important flag):

```bash
python -m app_system.model_stealing --target http://target/ \
  --features "flipper_length:150:250,body_mass:2500:6500"
```

Use a stronger surrogate architecture and save it:

```bash
python -m app_system.model_stealing --target http://target/ \
  --features "flipper_length:150:250,body_mass:2500:6500" \
  --surrogate-type mlp --output surrogate.joblib
```

Handle a target whose API parameter names and response key differ from the feature names:

```bash
python -m app_system.model_stealing --target http://target/ \
  --features "feat1:0:100,feat2:50:500" \
  --param-names "x,y" --label-key "prediction"
```

Submit the trained surrogate for server-side fidelity scoring (as in the course lab, where the server returns accuracy and a flag above threshold):

```bash
python -m app_system.model_stealing --target http://target/ \
  --features "flipper_length:150:250,body_mass:2500:6500" \
  --submit --output surrogate.joblib
```

Useful flags (read the script for the full list): `--surrogate-type {logistic,mlp,tree}`, `--method {GET,POST}`, `--delay` (add spacing to dodge rate limits), `--label-key`, `--param-names`, `--submit-endpoint`.

Practical notes:

- Prefer tight, realistic `--features` bounds over raw sample count. Quality beats quantity.
- Match surrogate complexity to the boundary: `logistic` for near-linear, `tree` or `mlp` for curved boundaries.
- If queries start failing, add `--delay` to respect any rate limiting rather than triggering a block.

## Detection and defense

- **Rate limiting** per client and per time window. This is the primary defense: it slows harvesting to the point of impracticality. Calibrate so legitimate users are not blocked.
- **Query monitoring / anomaly detection:** flag clients whose queries systematically sweep the input space or lack natural correlation between features.
- **Reduce output granularity:** return top-1 label only, avoid exposing full probability vectors, optionally add small controlled noise near the boundary.
- **Watermarking:** train the model so that specific rare inputs produce a known signature, letting you later prove a suspect model is a clone.
- **Legal and contractual controls** on API usage.

## Explain it to a non-expert

A company built a smart machine that costs a fortune to train, and they let anyone ask it questions through a website. You quietly ask it a few hundred questions, note every answer, and use those answers to teach a cheap machine of your own. Now your cheap machine gives the same answers, and you never paid for the expensive one. The only real fix is to limit how many questions each person can ask.

## References

- Course material: `07-attacking-ai-app-system/02_attacking_the_application/01_model_reverse_engineering`
- OWASP (2025) - ML and LLM security, model theft
- Tramèr et al. (2016) - Stealing Machine Learning Models via Prediction APIs
- Related toolkit pages: [00-overview](00-overview.md), [sponge-attack](sponge-attack.md)
