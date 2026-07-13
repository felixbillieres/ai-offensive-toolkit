# Attacking the AI Application and System Layers

> **In one sentence:** Most real AI incidents do not break the neural network's math, they abuse the ordinary software, tools, agents, and infrastructure wrapped around the model.

## The three layers

When people say "AI security" they usually picture attacks on the model's weights or training data. In practice, a deployed AI system is a stack, and every layer above and below the model is an attack surface:

```
+-------------------------------------+
|          User Interface             |   XSS via LLM output, UI trust
+-------------------------------------+
|     Application Logic / API         |   SSRF, SQLi, IDOR, auth bypass
+----------+----------+---------------+
|  LLM /   |  Tools / |  External     |   tool poisoning, rogue actions,
|  Model   |  MCP     |  Data Sources |   excessive agency
+----------+----------+---------------+
|     Infrastructure / Deployment     |   supply chain, DoS, framework CVEs
+-------------------------------------+
```

This section of the toolkit splits into three families:

1. **Attacking the application** (the code and agents around the model): model reverse engineering, denial of ML service, insecure integrated components, rogue actions.
2. **Attacking the system** (the infrastructure and supply chain): excessive data handling, deployment tampering, vulnerable framework code.
3. **Attacking MCP** (the Model Context Protocol layer): vulnerable servers, malicious servers, tool poisoning.

The key mental shift: classic web, network, and configuration vulnerabilities apply directly here, plus a set of new risks that come specifically from wiring a language model into the loop.

## Application vs system vs MCP

| Layer | You attack | Typical primitives | Toolkit page |
|-------|-----------|--------------------|--------------|
| Application | The app logic, agents, plugins, public API | SSRF, SQLi, IDOR, prompt injection into tools | [model-stealing](model-stealing.md), [sponge-attack](sponge-attack.md), [rogue-actions-ssrf](rogue-actions-ssrf.md), [insecure-integrated-components](insecure-integrated-components.md) |
| System | The deployment pipeline, storage, ML framework, hardware | Exposed files, deserialization RCE, framework CVEs, weight tampering | [model-tampering-deployment](model-tampering-deployment.md), [excessive-data-handling](excessive-data-handling.md), [vulnerable-framework-code](vulnerable-framework-code.md) |
| MCP | The standardized tool bridge between LLM and the world | Tool poisoning, rug pull, tool shadowing, server-side SSRF/SQLi/RCE | [mcp-attacks](mcp-attacks.md) |

## Why the application and system layers matter so much

- **The model is often the hardest thing to break and the least useful to break.** A backdoor in the weights is expensive to build. An exposed `storage.db` or an unauthenticated management API hands you everything for free.
- **The LLM is a confused deputy.** It holds tools and permissions, and it will happily follow attacker-controlled text (a username, a document, an MCP tool description) as if it were a trusted instruction. Excessive agency turns a text injection into a real action.
- **The wrapper leaks the model.** Missing rate limiting lets an attacker clone the model by querying it; algorithmic quirks let an attacker exhaust it with tiny inputs.

## Mapping to the OWASP Agentic and LLM Top 10

The pages in this section line up with the OWASP frameworks that matter for agents and applications:

| Toolkit page | OWASP reference |
|--------------|-----------------|
| model-stealing | Model theft / extraction (LLM and ML supply chain risk) |
| sponge-attack | LLM10:2025 Unbounded Consumption (Denial of ML Service, Denial of Wallet) |
| rogue-actions-ssrf | Agentic: Excessive Agency, Tool Misuse; classic SSRF |
| mcp-attacks | Agentic: Tool Poisoning, Rogue Servers, Prompt Injection via tools |
| model-tampering-deployment | LLM03 Supply Chain, deployment/pipeline tampering |
| insecure-integrated-components | LLM05 Improper Output Handling, insecure plugin design |
| excessive-data-handling | Sensitive Information Disclosure, excessive agency at the data layer |
| vulnerable-framework-code | LLM03 Supply Chain, known-vulnerable dependencies |

## The toolkit scripts at a glance

| Script | Covers |
|--------|--------|
| `app_system.model_stealing` | Black-box model extraction via API queries, surrogate training |
| `app_system.sponge_attack` | Denial of ML service, tokenizer and genetic sponge discovery, latency benchmarking |
| `app_system.mcp_attack` | SSRF via agent, tool/function abuse, rogue action injection, basic DoS |
| `app_system.model_tampering` | Weight backdoor injection, file patching, integrity verification and diffing |

For attacks where no dedicated script exists (insecure integrated components, excessive data handling, vulnerable framework code), the relevant pages point you at the closest script and at standard tooling (`feroxbuster`, `curl`, the MCP client).

## How to read this section

Start here, then pick the page that matches your target. Every attack page follows the same shape: what it is, the problem it exploits, an intuition, how it works, the threat model, when to use it, real toolkit commands, detection and defense, a plain-English explanation, and references. A reader who finishes a page should be able to both explain the attack and run it in the right context.

## References

- OWASP (2025) - Top 10 for LLM Applications (LLM03 Supply Chain, LLM05 Improper Output Handling, LLM10 Unbounded Consumption)
- OWASP (2025) - Agentic AI Top 10 (Excessive Agency, Tool Misuse, Rogue Servers)
- Anthropic - Model Context Protocol Specification
- Course material: `07-attacking-ai-app-system/01_Theory`
