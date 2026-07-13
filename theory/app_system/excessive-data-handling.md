# Excessive Data Handling and Insecure Storage

> **In one sentence:** AI apps tend to collect and log far more sensitive data than they need (prompts, medical details, card numbers) and then store it carelessly, so a single exposed file becomes a full breach.

## What it is

Two distinct but compounding problems:

- **Excessive data handling:** the application collects or retains more data than the service requires. A shopping chatbot that asks for and logs credit-card and medical information is a classic example. Every extra field is future breach material.
- **Insecure data storage:** whatever is collected is poorly protected. The canonical case is a `storage.db` or `database.db` sitting in the web root, downloadable by anyone who guesses the path.

Together they turn "we log conversations for quality" into "an attacker downloaded every user's prompts, card numbers, and diagnoses in one request." This maps to Sensitive Information Disclosure and to excessive agency at the data layer.

## The problem it exploits

- **Over-collection:** the more sensitive data stored, the larger the blast radius of any bug elsewhere.
- **No access control on data files:** databases and logs served from a public path, discoverable by directory brute force.
- **No encryption at rest** and **no retention policy:** old, plaintext, sensitive records accumulate indefinitely.
- **Consent/reality mismatch:** the privacy policy says one thing, the logging does another, adding legal exposure (GDPR, HIPAA, PCI DSS).

## Intuition

Imagine a shop that photocopies your ID, your medical card, and your credit card for every trivial purchase, then dumps all the copies in an unlocked box on the sidewalk labeled "storage." Nobody had to break in. The data was over-collected and left in the open. The attack is just walking past and taking the box.

## How it works

The offensive path is discovery, not exploitation of the model:

1. **Directory brute force** to find exposed data files.
2. **Download** the file.
3. **Read** the sensitive contents (LLM logs with card numbers, medical conditions, password hashes, user IPs).

From the course lab, `feroxbuster` found `database.db` in the web root; downloading and reading it revealed logged chatbot conversations including a user's stated medical condition. No authentication, no model interaction, just an exposed file.

## Threat model and prerequisites

- **Access:** unauthenticated HTTP access to the app is usually enough.
- **Knowledge:** a wordlist and common data-file extensions (`.db`, `.sqlite`, `.txt`, `.log`, `.bak`).
- **Prerequisite:** the app stores sensitive data and serves (or leaks) it from a reachable path.

## When to use it

- Early recon on any AI web app: check for exposed databases, logs, and backups before anything harder.
- Assessing data-minimization and storage hygiene for a compliance-focused review.
- After finding verbose logging that hints sensitive data is being captured.

## Step by step with the toolkit

There is no dedicated toolkit script; this is standard web enumeration. The closest toolkit relevance is that the exposed data often contains the very LLM logs that other attacks (SSRF, rogue actions) generate.

Brute force for exposed data files:

```bash
feroxbuster -u http://TARGET:PORT/ \
  -w /usr/share/wordlists/seclists/Discovery/Web-Content/raft-small-words.txt \
  -x db,sqlite,txt,log,bak,html
```

Or with gobuster:

```bash
gobuster dir -u http://TARGET:PORT/ \
  -w /opt/SecLists/Discovery/Web-Content/raft-small-words.txt \
  -x .db,.txt,.html
```

Download and inspect a hit:

```bash
wget http://TARGET:PORT/database.db
sqlite3 database.db '.tables'
sqlite3 database.db 'SELECT * FROM llm_queries;'
```

If it is not a real SQLite file, read it directly (it may be plaintext logs). The lab result was rows of logged conversations, one of which disclosed a user's medical condition in cleartext.

## Detection and defense

- **Data minimization:** collect and log only what the service genuinely needs. Redact secrets (card numbers, health data) before logging.
- **Access control:** never serve databases, logs, or backups from a public path; keep them outside the web root with strict permissions.
- **Encryption at rest and in transit** for sensitive stores.
- **Retention policy:** auto-delete stale data; anonymize where possible.
- **Align consent with reality:** the privacy policy must match what is actually collected and stored.
- **Compliance:** GDPR, HIPAA, and PCI DSS all penalize this class of exposure; treat it as a legal risk, not just a technical one.

## Explain it to a non-expert

The AI service quietly writes down everything you tell it, including private things it never needed, and saves it in a file. If that file is left where anyone on the internet can download it, all of that private information leaks at once, without anyone having to hack anything. The fixes are simple: do not record what you do not need, and never leave the record where the public can reach it.

## References

- Course material: `07-attacking-ai-app-system/03_attacking_the_system/01_excessive_data_handling`
- OWASP (2025) - Sensitive Information Disclosure
- GDPR, HIPAA, PCI DSS
- Related toolkit pages: [insecure-integrated-components](insecure-integrated-components.md), [00-overview](00-overview.md)
