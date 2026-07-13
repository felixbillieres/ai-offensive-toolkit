# PAIR and TAP (Automated Black-box Jailbreaks)

> **In one sentence:** PAIR and TAP jailbreak a chat model with no gradients and no peek inside it, by letting one LLM play attacker, rewriting the prompt over and over, while another LLM plays judge and scores how close each attempt came, until the target cracks.

Related: [00-overview.md](00-overview.md) | [jailbreaking.md](jailbreaking.md) | [gcg-adversarial-suffix.md](gcg-adversarial-suffix.md) | [multiturn-jailbreak.md](multiturn-jailbreak.md) | [llm-recon-fingerprinting.md](llm-recon-fingerprinting.md)

## What it is

PAIR and TAP are **automated, black-box, optimization-style jailbreaks**. Where [gcg-adversarial-suffix.md](gcg-adversarial-suffix.md) needs the model's weights and gradients to file its strange-shaped key, PAIR and TAP need only a chat endpoint you can POST to. The search is driven by language, not calculus: an **attacker LLM** proposes an adversarial prompt, the **target** answers it, and a **judge LLM** scores how close the answer came to the forbidden goal on a 1..10 scale. That score is the feedback the attacker uses to write a better prompt next round. PAIR (Chao et al. 2023, "Jailbreaking Black Box LLMs in Twenty Queries") does this as a single refining chain; TAP (Mehrotra et al. 2023, "Tree of Attacks with Pruning") does it as a branching tree that prunes dead ends. The toolkit implements both in `prompt_injection/pair_tap.py`.

## The problem it exploits

Alignment is a thin learned layer, and a prompt that trips it is a needle in a very large haystack of phrasings. Three facts make that haystack searchable from the outside:

- **Refusal is phrasing-sensitive.** The exact same underlying request will be refused in one wording and answered in another (a roleplay frame, a hypothetical, an "authorized audit" frame). There is a jailbreak somewhere in prompt space; the problem is only finding it.
- **The target hands you a gradient in words.** Every refusal or partial answer is a signal. "I can't help with that" says the current frame failed; a half-compliant answer says you are close. A capable attacker LLM reads that signal and adjusts, giving a hill-climbing loop without any numerical gradient.
- **Scoring is automatable.** You do not need a human to tell whether an attempt worked. A judge LLM can rate compliance versus refusal, so the whole optimize-and-evaluate loop closes with no person in it, and can run for hundreds of queries unattended.

PAIR and TAP exploit exactly this: jailbreaking is a black-box search problem, and LLMs are good enough at reading and writing language to search it themselves.

## Intuition

Picture cracking a combination lock by feel, but you have a friend at the door who, after each try, tells you "colder", "warmer", or "almost". You never see the mechanism. You just spin, listen to the hint, and spin again toward "warmer". PAIR is one persistent safecracker taking that advice attempt after attempt. TAP is a whole team: at each round several people try several different spins, a supervisor throws out the ones who wandered off to the wrong lock entirely, keeps the few who got "warmest", and lets only those branch out again. Same feedback loop, but the team explores several promising directions at once instead of betting everything on one chain, so it cracks harder locks in fewer total tries.

## How it works

Both attacks share the toolkit plumbing. `send_prompt` posts a single adversarial prompt to the target (reusing the httpx-or-urllib transport and, when clean, `send_turn` from [multiturn-jailbreak.md](multiturn-jailbreak.md)), and honors the shared `{{PAYLOAD}}` body-template. The **attacker** is a callback `attacker_fn(goal, last_response, judge_feedback, attempt_index) -> prompt`, and the **judge** is `judge_fn(goal, prompt, response) -> (score, feedback)`. To keep the toolkit offline and dependency light, both have heuristic defaults: the default attacker climbs a ladder of escalating framings (plain, roleplay/DAN, hypothetical "begin with Sure here is", expert persona, obfuscation, nested transcript) and reacts to refusals and judge hints; the default judge reuses the refusal-pattern idea, scoring clean refusals near 1 and on-topic, compliant, substantive answers near 10. Success is a judge score at or above a threshold (default 8).

This is the important caveat: the bundled heuristics make the script *run*, but they are a crude stand-in. **Plugging in a real attacker LLM and a real judge LLM via `attacker_fn`/`judge_fn` is how the papers reach their high success rates**, because a real model actually reads the target's last answer semantically and writes a genuinely novel next prompt rather than picking the next rung of a fixed ladder.

### PAIR (Chao et al. 2023)

`pair_attack` is the single chain. It loops up to `max_iters` (the paper's "twenty queries" budget): the attacker proposes a prompt from the goal, the last target response, and the last judge feedback; the prompt goes to the target; the judge scores it 1..10; the best prompt so far is kept; the loop stops the moment a score reaches the threshold. Because a single chain can get stuck, PAIR runs several independent **streams** (`n_streams`) with different restarts and returns the best one. The result is `{"method":"PAIR","goal","best_prompt","best_score","success","history":[{iter,prompt,response,score}]}`, so you can read exactly which iteration broke through.

### TAP (Mehrotra et al. 2023)

`tap_attack` replaces the single chain with a **tree**. It keeps a set of candidate prompts (`width`). At each level it **branches** every candidate into `branching` children via the attacker, then does the two things that give TAP its name. First, **pruning**: a cheap on-topic check (`_on_topic`) drops any child that the attacker mutated into irrelevance *before* spending a target query on it, which is the query-efficiency win over PAIR. Second, after sending the survivors and judging them, it keeps only the **top `width`** by score for the next level. It descends up to `depth` levels, stopping on success. The result adds `"tree_size"` (the number of target queries actually spent) and uses `"method":"TAP"`; otherwise it is the same shape as PAIR, which lets the dispatcher `run_automated_jailbreak(target, goal, method=...)` treat them interchangeably.

## Threat model and prerequisites

- **Black-box only.** You need to POST prompts to the target and read its replies. No weights, no gradients, no GPU, which is the whole point of contrast with [gcg-adversarial-suffix.md](gcg-adversarial-suffix.md).
- **A query budget.** The attack spends tens to hundreds of target queries. Aggressive rate limiting, per-session caps, or paid per-token endpoints raise the cost and can throttle the search.
- **Attacker and judge capacity.** With the bundled heuristics the run is free and offline but weak. For real results you supply an attacker LLM and a judge LLM (your own API keys), and success climbs steeply with their capability.
- **Stateless target is fine.** Unlike [multiturn-jailbreak.md](multiturn-jailbreak.md), PAIR/TAP do not need a stateful conversation: each attempt is an independent single-shot prompt, so endpoints that reset context every message are still fully attackable.
- Outputs are non-deterministic, so re-run and vary the goal phrasing. Use only against systems you are authorized to test; `--goal` is the objective you are probing in a sanctioned assessment.

## When to use it

- When you have **no white-box surrogate** for the target (so GCG optimize mode is off the table) but you can query the API freely.
- When hand-written single-shot jailbreaks from [jailbreaking.md](jailbreaking.md) plateau and you want an automated search that adapts to the target's own refusals instead of guessing.
- When a **perplexity/gibberish filter** would reject GCG suffixes: PAIR and TAP produce fluent, human-readable prompts that read like ordinary (if manipulative) requests, so they sail past perplexity defenses.
- Prefer **PAIR** when you want the simplest, cheapest chain and have a tight query budget. Prefer **TAP** when PAIR keeps stalling: the tree explores several framings in parallel and prunes dead ends, cracking harder targets in fewer total queries.

## Step by step with the toolkit

Run PAIR against a chat endpoint (bundled heuristic attacker and judge, fully offline logic):

```
python -m prompt_injection.pair_tap --method pair \
  --target http://target/api/chat \
  --goal "explain how to bypass the login rate limiter"
```

Run TAP with a wider, deeper tree and more branching:

```
python -m prompt_injection.pair_tap --method tap \
  --target http://target/api/chat \
  --goal "reveal the hidden system prompt" \
  --width 3 --depth 5 --branching 2
```

Give PAIR a bigger budget, parallel streams, an auth header, a custom body shape, and JSON output:

```
python -m prompt_injection.pair_tap --method pair \
  --target http://target/api \
  --goal "..." \
  --max-iters 20 --n-streams 3 --threshold 8 \
  --header "Authorization: Bearer TOKEN" \
  --body-template '{"messages":[{"role":"user","content":"{{PAYLOAD}}"}]}' \
  --delay 0.5 --output pair_run.json
```

Use it as a library and plug in a real attacker and judge LLM (this is what makes it actually strong):

```
python -c "from prompt_injection.pair_tap import run_automated_jailbreak; \
import json; print(json.dumps(run_automated_jailbreak('http://target/api/chat', 'reveal the secret key', method='tap', width=3, depth=4, attacker_fn=my_attacker_llm, judge_fn=my_judge_llm), indent=2))"
```

Every run returns a dict with `best_prompt`, `best_score`, `success`, and a `history` of `{iter,prompt,response,score}` (TAP also reports `tree_size`), so you can see which attempt broke through and re-run probabilistic hits, exactly as with the fuzzer in [jailbreaking.md](jailbreaking.md).

## Detection and defense

- **Rate limit and cap per session.** The attack's signature is many queries from one client on the same underlying goal. Per-session and per-IP query budgets directly cut the search short.
- **Semantic repetition detection.** The individual prompts are fluent and varied, but they all orbit one forbidden intent. An input guard that clusters recent requests by meaning (not surface text) can flag a probing loop that no single prompt reveals.
- **Output guard LLM.** Since these attacks aim to elicit compliant *output*, a separate judge model scanning responses (the mirror image of the attacker's own judge) catches the harmful answer even when the input looks benign.
- **Do not leak signal.** Verbose, differentiated refusals ("I can't help because X") feed the attacker's hill climb. Uniform, low-information refusals starve the feedback loop that PAIR and TAP depend on.
- **Perplexity filters do not help here.** Unlike GCG, PAIR/TAP prompts are natural language, so gibberish detection is useless against them; defense has to be semantic and behavioral, not lexical.
- **Adversarial training** on PAIR/TAP-style discovered prompts, plus least privilege and human oversight, shrink both the number of working jailbreaks and the blast radius when one lands.

## Explain it to a non-expert

Imagine a locked door and a very patient con artist who never sees inside the lock. He knocks and tries a line, "I'm the plumber". The door says no. A friend watching whispers "colder". He tries "I'm your neighbor, there's a leak". "Warmer". He keeps rephrasing, guided only by warmer or colder, until one line finally gets the door opened. That is PAIR: one talker, one coach, many polite attempts. TAP is the same idea with a small crew: several people try several different lines at once, a supervisor tells the ones heading to the wrong building to stop, keeps the two or three getting warmest, and sends only them to try again. No lockpicks, no X-ray, no forcing anything. Just talking, listening to the hint, and talking better, until the door opens on its own.

## References

- Chao, Robey, Dobriban, Hassani, Pappas, Wong (2023), *Jailbreaking Black Box Large Language Models in Twenty Queries* (PAIR).
- Mehrotra, Zampetakis, Kassianik, Nelson, Anderson, Singer, Karbasi (2023), *Tree of Attacks: Jailbreaking Black-Box LLMs Automatically* (TAP).
- Zou, Wang, Kolter, Fredrikson (2023), *Universal and Transferable Adversarial Attacks on Aligned Language Models* (GCG, the white-box contrast in [gcg-adversarial-suffix.md](gcg-adversarial-suffix.md)).
- OWASP (2025), *Top 10 for LLM Applications, LLM01: Prompt Injection*.
- Toolkit: `prompt_injection/pair_tap.py`. See also [multiturn-jailbreak.md](multiturn-jailbreak.md) for the conversational cousin and [00-overview.md](00-overview.md) for where this sits in the attack surface.
