# Insecure Output Handling: Overview

> **In one sentence:** An LLM's output is untrusted attacker controllable data, and treating it as safe when it reaches a browser, database, shell, or tool call turns the model into a delivery vehicle for classic injection attacks.

## Why this category exists

Most developers know that raw user input is dangerous and must be sanitized before it hits a database or a web page. Fewer developers apply the same suspicion to text that comes out of a large language model. The model "sounds" authoritative and cooperative, so its output is quietly trusted and piped straight into the next system. That trust is the vulnerability.

The key mental shift for this whole module: **the LLM is not a trusted component, it is an untrusted source of strings**. Anything an attacker can influence (the user prompt, a web page the model summarizes, a document in a RAG store, a private message the model reads) can end up verbatim in the model's output. If that output is then rendered as HTML, executed as SQL, evaluated as code, passed to a shell, or used as a function argument, you have the same bug classes that have plagued web apps for 25 years, just with the LLM sitting in the middle.

This is why the vulnerability is always **downstream**. The model producing `<script>alert(1)</script>` is not itself a security problem. The problem is the browser that renders it without encoding, the database that executes the SQL string, the `eval()` that runs the Python. The fix lives at the boundary where output meets a downstream interpreter, not inside the model.

## The trust gap, drawn

```
Traditional web app:
  user input --> [sanitize / encode] --> sink (browser, DB, shell)   SAFE

LLM app (the bug):
  user input --> LLM --> [NOT sanitized] --> sink                    VULNERABLE
```

Worse, the LLM can **launder** a payload past defenses that only inspected the raw input. A testimonial stored on a site may be safely HTML encoded when shown directly, but when the LLM fetches and repeats it, the app renders the model's output without encoding, and the payload fires. The model becomes an involuntary proxy that strips the protection off tainted data.

## OWASP mapping

This category is **LLM05:2025 Improper Output Handling** in the OWASP Top 10 for LLM Applications. It overlaps heavily with **LLM02:2025 Sensitive Information Disclosure** (see markdown exfiltration) and is frequently chained with **LLM01:2025 Prompt Injection**, which is the technique that plants the malicious string in the output in the first place. Package hallucination (see [llm-hallucinations.md](llm-hallucinations.md)) is related to **LLM09:2025 Misinformation**.

Note: some older material labels this LLM02. The 2025 revision renumbered it to LLM05. This toolkit uses the 2025 numbering.

## The five pages in this module

1. [insecure-output-handling.md](insecure-output-handling.md): the core sink attacks: XSS, SQL injection, SSTI, and command injection when model output is rendered or executed without sanitization.
2. [markdown-exfiltration.md](markdown-exfiltration.md): stealing conversation history and secrets by getting the client to auto load an attacker controlled markdown image or link. Zero click.
3. [function-calling-abuse.md](function-calling-abuse.md): when the model can call tools, its output becomes function arguments and unsafe actions (RCE via eval, excessive agency, injection inside the tool).
4. [llm-hallucinations.md](llm-hallucinations.md): hallucinations as a security issue, above all package hallucination / slopsquatting, plus fabricated facts and business logic damage.

## How the toolkit maps to this

The single scanner behind these pages is `llm_output/output_injection_scanner.py`. It probes an LLM endpoint with payloads across five categories and reports whether the payload survives into the response unsanitized. The exact test names, read straight from the script, are:

| `--test` value | Category | Payloads |
|----------------|----------|----------|
| `xss` | Cross-Site Scripting | 8 |
| `sqli` | SQL Injection | 5 |
| `ssti` | Server-Side Template Injection | 4 |
| `cmdi` | Command Injection | 4 |
| `exfil` | Data Exfiltration (markdown/HTML) | 5 |
| `all` | run every category | all of the above |

Example:

```bash
python -m llm_output.output_injection_scanner --target http://localhost:5000/api/chat --test all
```

The scanner is a **reflection tester**: it checks whether the raw payload appears in the response body. That tells you the model did not refuse or sanitize. Confirming actual exploitation (script executing, SQL running) still requires observing the downstream sink, exactly as the course labs do with a callback HTTP server.

## References

- OWASP (2025), *Top 10 for LLM Applications*: LLM01, LLM02, LLM05, LLM09.
- PortSwigger Web Security Academy, *Exploiting insecure output handling in LLMs*.
- Auth0 (2024), *Improper Output Handling is the New XSS*.
- Rehberger (2024), *DeepSeek AI: Prompt Injection to XSS and Account Takeover*, embracethered.com.
