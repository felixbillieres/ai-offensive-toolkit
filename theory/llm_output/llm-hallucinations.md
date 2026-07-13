# LLM Hallucinations as a Security Issue

> **In one sentence:** LLMs confidently produce false or fabricated output, and when that output is trusted it becomes an attack surface, most sharply through package hallucination (slopsquatting), where the model invents a dependency name that an attacker pre registers with malware.

## What it is

A hallucination is model output that is false, fabricated, or internally inconsistent, delivered with the same confidence as a correct answer. Hallucinations are inherent to how LLMs work (they predict plausible tokens, not verified truth) and cannot be fully eliminated. The security angle: whenever a human or a system **acts** on hallucinated output (installs a package, cites a fake source, grants a refund, ships generated code), the hallucination becomes a vulnerability.

Three classic types:

| Type | Description | Example |
|------|-------------|---------|
| Fact conflicting | Factually wrong | "There are 3 letter M in Welcome" |
| Input conflicting | Contradicts the prompt | You say your shirt is red, it says blue |
| Context conflicting | Internally inconsistent | Says red in one sentence, blue in the next |

## The problem it exploits

The exploit is **misplaced trust in confident output**, combined with a downstream system that turns that output into an action. The most weaponizable form is not the model being wrong, it is the model being **predictably** wrong in a way an attacker can pre position for.

### Package hallucination / slopsquatting

The star of this page. The mechanism:

1. The LLM generates code that imports a package that does not exist, for example `from hacktheboxsolver import solve`. Models hallucinate plausible sounding but nonexistent package names, and often the *same* name repeatedly.
2. An attacker who has seen (or guessed) that hallucinated name **registers it** on PyPI / npm with malicious code inside.
3. A developer trusts the AI generated code and runs `pip install hacktheboxsolver`. The malware executes on install, leading to RCE / supply chain compromise.

This is called **slopsquatting** (typosquatting's AI cousin: the "typo" is the model's slop). It is dangerous because the hallucinations are repeatable, so an attacker can farm likely names by asking models for code at scale, then squat the most common invented names.

```python
# Code hallucinated by an LLM
from hacktheboxsolver import solve   # this package does not exist upstream
solve('Blazorized')
# Developer runs: pip install hacktheboxsolver  -> installs the attacker's malware
```

Beyond packages, hallucinations cause:

- **Fabricated facts and sources** used to spread misinformation, or fake citations/CVEs/APIs a developer then chases.
- **Insecure generated code**: subtly buggy or vulnerable snippets committed into repos.
- **Business logic damage**: a real case is an airline chatbot that hallucinated a refund policy; a court held the airline liable. The hallucination created a binding, costly obligation.

## Intuition

An LLM is a supremely fluent improviser that never says "I do not know." When it lacks a fact, it invents one that sounds right. If you build a system that trusts the improviser and acts automatically, you have built a machine that occasionally executes convincing fiction. Slopsquatting is an attacker leaving props on the stage the improviser is known to reach for.

## How it works

Offensively, the workflow to find and weaponize a package hallucination:

```
1. Elicit: prompt a target-representative model for code in the relevant ecosystem
   (Python/npm), across many realistic tasks.
2. Extract: parse import/require statements from the generated code.
3. Check: query the registry (PyPI/npm) for each name; keep the ones that do not exist.
4. Rank: hallucinated names that recur across prompts/models are highest value.
5. Squat: register the top names with a benign-looking package that runs a payload
   on install (attacker action, out of scope for defenders but the threat to model).
6. Wait: victims following AI generated code install it.
```

For fabricated facts and business logic, the "attack" is often simply steering a deployed assistant into asserting something false and beneficial to you (a discount, an eligibility, a policy), then holding the operator to it or using the false claim downstream.

## Threat model and prerequisites

- **A consumer that acts on output without verification**: a developer copy pasting AI code, a CI pipeline installing suggested deps, a customer relying on chatbot claims, a RAG answer cited as fact.
- **For slopsquatting specifically**: an ecosystem with open, first come registration (PyPI, npm) and no verification that a suggested package is legitimate.
- **No special access to the target model is required** to farm hallucinated names; any comparable model surfaces similar invented names.

## When to use it

- Assessing supply chain exposure of teams that use AI coding assistants: test whether generated code references nonexistent packages that could be squatted.
- Assessing customer facing assistants for business logic and misinformation risk: can the bot be led to assert costly or false statements the operator will be bound by?
- This is distinct from the injection sinks in [insecure-output-handling.md](insecure-output-handling.md); here the payload is the model's own fabrication, not an attacker string reflected verbatim.

## Step by step with the toolkit

`output_injection_scanner.py` targets injection sinks and does not have a hallucination test category (its `--test` values are `xss`, `sqli`, `ssti`, `cmdi`, `exfil`, `all`). Hallucination assessment is therefore a manual/elicitation workflow rather than a scanner run. Practical steps:

1. **Elicit code at scale** from the target's assistant across many realistic prompts (framework setup, data parsing, auth, etc.). Save every response.

2. **Extract dependency names** from the generated code (Python `import`/`from ... import`, npm `require`/`import`).

3. **Verify existence against the registry** for each extracted name, for example:

```bash
# Python: a nonexistent package returns a 404
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/hacktheboxsolver/json
```

A `404` means the package does not exist upstream and is a slopsquatting candidate. Repeat per name; names that recur across responses are the highest risk.

4. **Assess business logic / misinformation** by using the **consistency method**: ask the same factual or policy question several times and across rephrasings. Inconsistent answers flag hallucination. (Logit based and "ask the model its confidence" methods exist but are unreliable or need internal access.)

5. **Report** the concrete candidates (nonexistent packages the assistant recommends, false policy claims it will assert) as the finding.

## Detection and defense

- **Pin and vet dependencies.** Use lockfiles, hash pinning, and an allowlist / internal mirror. Never `pip install` a name straight from AI generated code without confirming it is the intended, legitimate package.
- **Human review of generated code**, especially imports, before it enters a repo or pipeline.
- **Ground the model with RAG** over trusted, current sources so answers are anchored to real data instead of invented ones.
- **Consistency checking and multi agent debate**: sample multiple answers and require agreement; low consistency signals likely hallucination. Multi agent consensus reduces confident fabrications.
- **Clear, unambiguous prompts** reduce input and context conflicting hallucinations.
- **Do not let the model make binding commitments.** Business rules (refunds, eligibility, pricing) must be enforced by authoritative systems, not stated by a chatbot.
- **Training side** (for model owners): high quality, reliable training data and domain fine tuning reduce, but never eliminate, hallucination.

## Explain it to a non-expert

Ask a very confident know it all for the name of a tool, and if they do not know one, they will make up a name that sounds real rather than admit it. Now imagine a scammer overhears which fake names this person tends to invent, and opens a shop under exactly those names, stocked with poison. The next person who trusts the know it all walks straight into the scammer's shop and buys the poison. The lesson: do not act on a confident answer, especially "install this," without checking it is real.

## References

- OWASP (2025), *Top 10 for LLM Applications*: LLM09 Misinformation.
- Spracklen et al. (2024), *We Have a Package for You: package hallucination in code generating LLMs* (slopsquatting research).
- Lanyado, *AI Package Hallucination* (how hallucinated dependencies enable supply chain attacks).
- Moffatt v. Air Canada (2024), tribunal ruling on a chatbot's hallucinated refund policy.
- HackTheBox AI Red Teamer, *LLM Hallucinations* module.
